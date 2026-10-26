import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Badge } from '../design-system';
import { ChatPanel } from '../components/ChatPanel';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorDetail } from '../components/ErrorDetail';
import { IngestProgress } from '../components/IngestProgress';
import { GraphPanel } from '../components/GraphPanel';
import { OutlinePanel } from '../components/OutlinePanel';
import { Toast } from '../components/Toast';
import { api, ApiError, isInFlight } from '../lib/api';
import { formatRelative } from '../lib/format';
import { STATUS_TONE, statusLabel } from '../lib/status';
import { useLang } from '../lib/i18n';
import { navigate } from '../lib/useHashRoute';

type Tab = 'chat' | 'outline' | 'graph' | 'process';

const TAB_LABEL = { chat: 'tabChat', outline: 'tabOutline', graph: 'tabGraph', process: 'tabProcess' } as const;

const PROCESS_PANE = { height: '100%', overflowY: 'auto', boxSizing: 'border-box', padding: '32px var(--space-6)' } as const;

export function DocumentScreen({ docId }: { docId: string }) {
  const { t, lang } = useLang();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('chat');
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
      queryClient.removeQueries({ queryKey: ['document', docId] });
      navigate('/');
    },
    onError: (error: unknown) => {
      setToast(error instanceof ApiError ? error.detail : t.errorGeneric);
      setConfirmDelete(false);
    },
  });

  const retryMutation = useMutation({
    mutationFn: () => api.retryDocument(docId),
    onSuccess: (document) => {
      queryClient.setQueryData(['document', docId], document);
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
    onError: (error: unknown) => setToast(error instanceof ApiError ? error.detail : t.errorGeneric),
  });

  const doc = documentQuery.data;

  return (
    <>
      <header className="pane-header">
        <a href="#/" className="quiet-button mobile-only" style={{ textDecoration: 'none' }}>
          ← {t.railDocuments}
        </a>

        {doc ? (
          <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <h1
              className="truncate"
              style={{ margin: 0, fontSize: 'var(--fs-ui-md)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}
            >
              {doc.name}
            </h1>
            {doc.status !== 'done' && <Badge tone={STATUS_TONE[doc.status]}>{statusLabel(doc.status, t)}</Badge>}
            <span className="truncate" style={{ display: 'flex', gap: 10, fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
              {doc.mode && <span>{doc.mode === 'long' ? t.modeLong : t.modeShort}</span>}
              {doc.chunks !== null && <span>{t.outlineChunkCount(doc.chunks)}</span>}
              {doc.created_at && <span>{formatRelative(doc.created_at, lang, t.relativeJustNow)}</span>}
              {doc.llm_model && <span>{doc.llm_model}</span>}
            </span>
          </div>
        ) : (
          <div style={{ flex: 1 }}>
            {documentQuery.isPending && <div className="skeleton-block" style={{ height: 14, width: 220 }} />}
          </div>
        )}

        {doc?.status === 'done' && (
          <div className="segmented" role="tablist">
            {(doc.mode === 'long' ? (['chat', 'outline', 'graph', 'process'] as const) : (['chat', 'process'] as const)).map((key) => (
              <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
                {t[TAB_LABEL[key]]}
              </button>
            ))}
          </div>
        )}

        {doc?.has_original && (
          <a href={api.originalUrl(doc.id)} target="_blank" rel="noreferrer" className="quiet-button" style={{ textDecoration: 'none' }}>
            {t.originalLink}
          </a>
        )}

        {doc && (
          <button className="quiet-button" data-tone="danger" onClick={() => setConfirmDelete(true)}>
            {t.deleteAction}
          </button>
        )}
      </header>

      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {documentQuery.isError && (
          <div style={{ padding: 'var(--space-6)', maxWidth: 720 }}>
            <Alert tone="danger" title={t.errorGeneric}>
              {documentQuery.error instanceof Error ? documentQuery.error.message : ''}
            </Alert>
          </div>
        )}

        {doc && (doc.status !== 'done' || tab === 'process') && (
          <div style={PROCESS_PANE}>
            <div style={{ maxWidth: 720, display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
              {doc.status === 'error' && (
                <Alert tone="danger" title={t.docErrorTitle}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                    <span>{t.docErrorReupload}</span>
                    {doc.error && <ErrorDetail message={doc.error} limit={160} />}
                    {doc.has_original && (
                      <button
                        className="quiet-button"
                        style={{ alignSelf: 'flex-start' }}
                        onClick={() => retryMutation.mutate()}
                        disabled={retryMutation.isPending}
                      >
                        {retryMutation.isPending ? t.docRetrying : t.docRetry}
                      </button>
                    )}
                  </div>
                </Alert>
              )}
              {(doc.status !== 'error' || doc.timeline.length > 0) && <IngestProgress doc={doc} />}
            </div>
          </div>
        )}

        {doc?.status === 'done' &&
          tab !== 'process' &&
          (tab === 'outline' && doc.mode === 'long' ? (
            <OutlinePanel docId={doc.id} />
          ) : tab === 'graph' && doc.mode === 'long' ? (
            <GraphPanel docId={doc.id} />
          ) : (
            <ChatPanel docId={doc.id} />
          ))}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title={t.deleteConfirmTitle}
        body={doc ? t.deleteConfirmBody(doc.name) : ''}
        danger
        onConfirm={() => deleteMutation.mutate()}
        onCancel={() => setConfirmDelete(false)}
      />

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </>
  );
}
