import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Button, DataTable, ProgressBar } from '../design-system';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { Toast } from '../components/Toast';
import { api, ApiError, isInFlight, type Document, type DocumentStatus } from '../lib/api';
import { formatRelative } from '../lib/format';
import { useLang } from '../lib/i18n';
import type { Dict } from '../lib/i18n';

const STATUS_TONE: Record<DocumentStatus, 'brand' | 'accent' | 'secure' | 'neutral'> = {
  queued: 'neutral',
  converting: 'accent',
  embedding: 'accent',
  building_tree: 'accent',
  extracting_graph: 'accent',
  done: 'secure',
  error: 'brand',
};

function statusLabel(status: DocumentStatus, t: Dict): string {
  return {
    queued: t.statusQueued,
    converting: t.statusConverting,
    embedding: t.statusEmbedding,
    building_tree: t.statusBuildingTree,
    extracting_graph: t.statusExtractingGraph,
    done: t.statusDone,
    error: t.statusError,
  }[status];
}

export function DocumentsScreen() {
  const { t, lang } = useLang();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [pendingDelete, setPendingDelete] = useState<Document | null>(null);
  const [toast, setToast] = useState<string | null>(null);

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

  const documents = documentsQuery.data ?? [];

  const rows = documents.map((doc) => ({
    name: (
      <span style={{ fontWeight: 'var(--fw-medium)', color: 'var(--text-title)' }}>{doc.name}</span>
    ),
    status: (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)', minWidth: 140 }}>
        <Badge tone={STATUS_TONE[doc.status]}>{statusLabel(doc.status, t)}</Badge>
        {isInFlight(doc.status) && <ProgressBar value={doc.progress * 100} showValue={false} />}
        {doc.status === 'error' && doc.error && (
          <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--status-danger)' }}>{doc.error}</span>
        )}
      </div>
    ),
    mode: doc.mode === 'long' ? t.modeLong : doc.mode === 'short' ? t.modeShort : t.modeUnknown,
    uploaded: doc.created_at ? formatRelative(doc.created_at, lang, t.relativeJustNow) : t.modeUnknown,
    actions: (
      <Button variant="ghost" size="sm" onClick={() => setPendingDelete(doc)}>
        {t.deleteAction}
      </Button>
    ),
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', maxWidth: 'var(--container-max)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-4)' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 'var(--fs-ui-xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-title)' }}>
            {t.uploadTitle}
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
        <div>
          <input ref={fileInput} type="file" hidden onChange={handleFileChosen} />
          <Button onClick={() => fileInput.current?.click()} disabled={uploadMutation.isPending}>
            {uploadMutation.isPending ? t.uploadUploading : t.uploadButton}
          </Button>
        </div>
      </div>

      <div style={{ background: 'var(--surface-card)', border: 'var(--stroke-hairline) solid var(--border-subtle)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
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
          />
        ) : documentsQuery.isPending ? null : (
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
