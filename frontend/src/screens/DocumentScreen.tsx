import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Badge, Button, Tabs } from '../design-system';
import { ChatPanel } from '../components/ChatPanel';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorDetail } from '../components/ErrorDetail';
import { IngestProgress } from '../components/IngestProgress';
import { OutlinePanel } from '../components/OutlinePanel';
import { Toast } from '../components/Toast';
import { api, ApiError, isInFlight } from '../lib/api';
import { formatRelative } from '../lib/format';
import { STATUS_TONE, statusLabel } from '../lib/status';
import { useLang } from '../lib/i18n';

export function DocumentScreen({ docId }: { docId: string }) {
  const { t, lang } = useLang();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const documentQuery = useQuery({
    queryKey: ['document', docId],
    queryFn: () => api.getDocument(docId),
    refetchInterval: (query) => (query.state.data && isInFlight(query.state.data.status) ? 2000 : false),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteDocument(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      window.location.hash = '#/';
    },
    onError: (error: unknown) => {
      setToast(error instanceof ApiError ? error.detail : t.errorGeneric);
      setConfirmDelete(false);
    },
  });

  const doc = documentQuery.data;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', maxWidth: 'var(--container-max)', margin: '0 auto', height: '100%' }}>
      <div>
        <a href="#/" style={{ fontSize: 'var(--fs-ui-sm)', color: 'var(--text-link)', textDecoration: 'none' }}>
          {t.docBackToList}
        </a>
      </div>

      {documentQuery.isError && (
        <Alert tone="danger" title={t.errorGeneric}>
          {documentQuery.error instanceof Error ? documentQuery.error.message : ''}
        </Alert>
      )}

      {doc && (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
              <h1 style={{ margin: 0, fontSize: 'var(--fs-ui-xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-title)' }}>
                {doc.name}
              </h1>
              <Badge tone={STATUS_TONE[doc.status]}>{statusLabel(doc.status, t)}</Badge>
            </div>
            <div style={{ display: 'flex', gap: 'var(--space-3)', fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
              <span>{doc.mode === 'long' ? t.modeLong : doc.mode === 'short' ? t.modeShort : t.modeUnknown}</span>
              {doc.created_at && <span>{formatRelative(doc.created_at, lang, t.relativeJustNow)}</span>}
              {doc.chunks !== null && <span>{t.outlineChunkCount(doc.chunks)}</span>}
            </div>
          </div>

          {isInFlight(doc.status) && (
            <div style={{ background: 'var(--surface-card)', border: 'var(--stroke-hairline) solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: 'var(--space-6)' }}>
              <IngestProgress doc={doc} />
            </div>
          )}

          {doc.status === 'error' && (
            <Alert tone="danger" title={t.docErrorTitle}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                <span>{t.docErrorReupload}</span>
                {doc.error && <ErrorDetail message={doc.error} limit={160} />}
                <div>
                  <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)} style={{ color: 'var(--text-danger-soft)' }}>
                    {t.deleteAction}
                  </Button>
                </div>
              </div>
            </Alert>
          )}

          {doc.status === 'done' && doc.mode === 'long' && (
            <>
              <Tabs tabs={[t.tabChat, t.tabOutline]} activeIndex={tab} onChange={setTab} />
              {/* minHeight: 400 alone doesn't stop this box from growing past the viewport --
                  minHeight: 0 + overflow: hidden is what lets it actually shrink to the space
                  main has left, so ChatPanel's own internal scroll region (not the whole page)
                  is what scrolls and the composer stays pinned at the bottom. */}
              <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                {tab === 0 ? <ChatPanel docId={doc.id} /> : <OutlinePanel docId={doc.id} />}
              </div>
            </>
          )}

          {doc.status === 'done' && doc.mode !== 'long' && (
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <ChatPanel docId={doc.id} />
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmDelete}
        title={t.deleteConfirmTitle}
        body={doc ? t.deleteConfirmBody(doc.name) : ''}
        danger
        onConfirm={() => deleteMutation.mutate()}
        onCancel={() => setConfirmDelete(false)}
      />

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}
