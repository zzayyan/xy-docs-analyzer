import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Badge, Button, DataTable, ProgressBar } from '../design-system';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorDetail } from '../components/ErrorDetail';
import { Toast } from '../components/Toast';
import { api, ApiError, isInFlight, type Document } from '../lib/api';
import { formatRelative } from '../lib/format';
import { STATUS_TONE, statusLabel } from '../lib/status';
import { useLang } from '../lib/i18n';

export function DocumentsScreen() {
  const { t, lang } = useLang();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [pendingDelete, setPendingDelete] = useState<Document | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const limitsQuery = useQuery({ queryKey: ['limits'], queryFn: api.limits });

  const documentsQuery = useQuery({
    queryKey: ['documents'],
    queryFn: api.listDocuments,
    // Poll only while something is still ingesting; a fully-settled list needs no refetch.
    refetchInterval: (query) => (query.state.data?.some((d) => isInFlight(d.status)) ? 3000 : false),
  });

  const uploadMutation = useMutation({
    mutationFn: api.uploadDocument,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
    onError: (error: unknown) => {
      setToast(error instanceof ApiError ? error.detail : t.errorGeneric);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: api.deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      setPendingDelete(null);
    },
    onError: (error: unknown) => {
      setToast(error instanceof ApiError ? error.detail : t.errorGeneric);
      setPendingDelete(null);
    },
  });

  const handleFileChosen = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file after an error
    if (file) uploadMutation.mutate(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) uploadMutation.mutate(file);
  };

  const documents = documentsQuery.data ?? [];
  const failedCount = documents.filter((d) => d.status === 'error').length;

  const rows = documents.map((doc) => ({
    name: (
      <a href={`#/doc/${doc.id}`} className="doc-link" title={doc.id} style={{ fontWeight: 'var(--fw-medium)' }}>
        {doc.name}
      </a>
    ),
    status: (
      // align-items defaults to 'stretch' on a flex column, which was forcing the Badge (an
      // inline-flex span with no explicit width) to stretch to the full column width -- that's
      // the giant solid-color bar every status pill was rendering as.
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 'var(--space-1)', minWidth: 140 }}>
        <Badge tone={STATUS_TONE[doc.status]}>{statusLabel(doc.status, t)}</Badge>
        {isInFlight(doc.status) && <ProgressBar value={doc.progress * 100} showValue={false} style={{ width: '100%' }} />}
        {doc.status === 'error' && doc.error && (
          <div style={{ color: 'var(--status-danger)', width: 260 }}>
            <ErrorDetail message={doc.error} limit={70} />
          </div>
        )}
      </div>
    ),
    mode: doc.mode === 'long' ? t.modeLong : doc.mode === 'short' ? t.modeShort : t.modeUnknown,
    uploaded: doc.created_at ? formatRelative(doc.created_at, lang, t.relativeJustNow) : t.modeUnknown,
    actions: (
      <Button variant="ghost" size="sm" onClick={() => setPendingDelete(doc)} style={{ color: 'var(--text-muted)' }}>
        {t.deleteAction}
      </Button>
    ),
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', maxWidth: 'var(--container-max)', margin: '0 auto' }}>
      <div
        className="upload-dropzone"
        data-active={dragActive}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 'var(--space-4)',
          padding: 'var(--space-5)',
          borderRadius: 'var(--radius-md)',
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 'var(--fs-ui-xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-title)' }}>
            {documentsQuery.data ? t.docsCount(documents.length) : t.navDocuments}
          </h1>
          {limitsQuery.data ? (
            <p style={{ margin: '6px 0 0', fontSize: 'var(--fs-ui-sm)', color: 'var(--text-muted)' }}>
              {t.uploadLimitsCaption(limitsQuery.data.max_upload_mb, limitsQuery.data.max_pages)}
            </p>
          ) : limitsQuery.isError ? (
            <p style={{ margin: '6px 0 0', fontSize: 'var(--fs-ui-sm)', color: 'var(--status-danger)' }}>
              {t.uploadLimitsUnavailable}
            </p>
          ) : null}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>{t.uploadDropHint}</span>
          <input ref={fileInput} type="file" hidden onChange={handleFileChosen} />
          <Button onClick={() => fileInput.current?.click()} disabled={uploadMutation.isPending}>
            {uploadMutation.isPending ? t.uploadUploading : t.uploadButton}
          </Button>
        </div>
      </div>

      {failedCount > 0 && <Alert tone="danger" title={t.docsFailedSummary(failedCount)} />}

      <div
        style={{
          background: 'var(--surface-card)',
          border: 'var(--stroke-hairline) solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
          overflow: 'hidden',
          overflowX: 'auto',
        }}
      >
        {rows.length > 0 ? (
          <DataTable
            columns={[
              { key: 'name', label: t.tableName },
              { key: 'status', label: t.tableStatus },
              { key: 'mode', label: t.tableMode },
              { key: 'uploaded', label: t.tableUploaded },
              { key: 'actions', label: t.tableActions, align: 'right' },
            ]}
            rows={rows}
            style={{ minWidth: 640 }}
          />
        ) : documentsQuery.isPending ? (
          <div style={{ padding: 'var(--space-6)', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {[72, 58, 64, 46].map((width, i) => (
              <div key={i} className="skeleton-block" style={{ height: 18, width: `${width}%` }} />
            ))}
          </div>
        ) : (
          <p
            style={{
              margin: 0,
              padding: 'var(--space-8)',
              textAlign: 'center',
              fontSize: 'var(--fs-ui-sm)',
              color: documentsQuery.isError ? 'var(--status-danger)' : 'var(--text-muted)',
            }}
          >
            {documentsQuery.isError ? t.errorGeneric : t.tableEmpty}
          </p>
        )}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title={t.deleteConfirmTitle}
        body={pendingDelete ? t.deleteConfirmBody(pendingDelete.name) : ''}
        danger
        onConfirm={() => pendingDelete && deleteMutation.mutate(pendingDelete.id)}
        onCancel={() => setPendingDelete(null)}
      />

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}
