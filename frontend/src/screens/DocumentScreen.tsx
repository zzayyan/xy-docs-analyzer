import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Badge, Tabs } from '../design-system';
import { ChatPanel } from '../components/ChatPanel';
import { IngestProgress } from '../components/IngestProgress';
import { OutlinePanel } from '../components/OutlinePanel';
import { api, isInFlight } from '../lib/api';
import { STATUS_TONE, statusLabel } from '../lib/status';
import { useLang } from '../lib/i18n';

export function DocumentScreen({ docId }: { docId: string }) {
  const { t } = useLang();
  const [tab, setTab] = useState(0);

  const documentQuery = useQuery({
    queryKey: ['document', docId],
    queryFn: () => api.getDocument(docId),
    refetchInterval: (query) => (query.state.data && isInFlight(query.state.data.status) ? 2000 : false),
  });

  const doc = documentQuery.data;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)', maxWidth: 'var(--container-max)', height: '100%' }}>
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
            <h1 style={{ margin: 0, fontSize: 'var(--fs-ui-xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-title)' }}>
              {doc.name}
            </h1>
            <Badge tone={STATUS_TONE[doc.status]}>{statusLabel(doc.status, t)}</Badge>
          </div>

          {isInFlight(doc.status) && (
            <div style={{ background: 'var(--surface-card)', border: 'var(--stroke-hairline) solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: 'var(--space-6)' }}>
              <IngestProgress doc={doc} />
            </div>
          )}

          {doc.status === 'error' && (
            <Alert tone="danger" title={t.docErrorTitle}>
              {t.docErrorReupload}
              {doc.error && (
                <div style={{ marginTop: 'var(--space-2)', fontSize: 'var(--fs-ui-xs)', opacity: 0.85 }}>{doc.error}</div>
              )}
            </Alert>
          )}

          {doc.status === 'done' && doc.mode === 'long' && (
            <>
              <Tabs tabs={[t.tabChat, t.tabOutline]} activeIndex={tab} onChange={setTab} />
              <div style={{ flex: 1, minHeight: 400 }}>
                {tab === 0 ? <ChatPanel docId={doc.id} /> : <OutlinePanel docId={doc.id} />}
              </div>
            </>
          )}

          {doc.status === 'done' && doc.mode !== 'long' && (
            <div style={{ flex: 1, minHeight: 400 }}>
              <ChatPanel docId={doc.id} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
