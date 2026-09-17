import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Button, Pill, Textarea } from '../design-system';
import { ConfirmDialog } from './ConfirmDialog';
import { Drawer } from './Drawer';
import { MessageBody } from './MessageBody';
import { Toast } from './Toast';
import { api, ApiError, type Citation, type Turn } from '../lib/api';
import { useChatStream } from '../lib/useChatStream';
import { useLang } from '../lib/i18n';

const SOURCE_LABEL_KEY = {
  vector: 'citationSourceVector',
  tree: 'citationSourceTree',
  kg: 'citationSourceKg',
  kg_facts: 'citationSourceKgFacts',
} as const;

/** Short human hint for a citation pill -- "[1]" alone told you nothing about what it pointed
 * to. Prefer the deepest heading (what section), fall back to a page range, else nothing. */
function citationShortLabel(c: Citation): string {
  if (c.headings.length > 0) {
    const heading = c.headings[c.headings.length - 1];
    return heading.length > 28 ? `${heading.slice(0, 28)}…` : heading;
  }
  if (c.pages.length > 0) {
    return c.pages.length === 1 ? `p. ${c.pages[0]}` : `p. ${c.pages[0]}–${c.pages[c.pages.length - 1]}`;
  }
  return '';
}

const STATUS_NODE_KEY = {
  vector_retrieve: 'chatStatusVectorRetrieve',
  tree_search: 'chatStatusTreeSearch',
  kg_retrieve: 'chatStatusKgRetrieve',
} as const;

export function ChatPanel({ docId }: { docId: string }) {
  const { t } = useLang();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState('');
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const turnsQuery = useQuery({ queryKey: ['turns', docId], queryFn: () => api.listTurns(docId) });
  // The backend persists a Turn in every case -- success, application failure, or a disconnect
  // mid-stream (complete: false) -- so both callbacks refetch history the same way; only a
  // failure additionally surfaces a toast.
  const refetchTurns = () => queryClient.invalidateQueries({ queryKey: ['turns', docId] });
  const stream = useChatStream(docId, {
    onDone: refetchTurns,
    onError: (message) => {
      setToast(message);
      refetchTurns();
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => api.clearTurns(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['turns', docId] });
      setConfirmClear(false);
    },
    onError: (error: unknown) => {
      setToast(error instanceof ApiError ? error.detail : t.errorGeneric);
      setConfirmClear(false);
    },
  });

  const send = () => {
    const question = draft.trim();
    if (!question || stream.state.status === 'streaming') return;
    setDraft('');
    stream.send(question);
  };

  const turns = turnsQuery.data ?? [];
  const streaming = stream.state.status === 'streaming';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', height: '100%' }}>
      {turns.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
          <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
            {t.chatTurnCount(turns.length)}
          </span>
          <Button variant="ghost" size="sm" onClick={() => setConfirmClear(true)} style={{ color: 'var(--text-muted)' }}>
            {t.chatClear}
          </Button>
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {turns.length === 0 && !turnsQuery.isPending && !streaming ? (
          <p style={{ margin: 'var(--space-8) 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--fs-ui-sm)' }}>
            {t.chatEmpty}
          </p>
        ) : (
          turns.map((turn) => <TurnBubbles key={turn.id} turn={turn} onCitationClick={setSelectedCitation} />)
        )}
        {streaming && <LiveBubble state={stream.state} onCitationClick={setSelectedCitation} />}
      </div>

      <div style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <Textarea placeholder={t.chatPlaceholder} value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} disabled={streaming} />
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button onClick={send} disabled={streaming || !draft.trim()}>
            {streaming ? t.chatSending : t.chatSend}
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmClear}
        title={t.chatClearConfirmTitle}
        body={t.chatClearConfirmBody}
        danger
        onConfirm={() => clearMutation.mutate()}
        onCancel={() => setConfirmClear(false)}
      />

      <Drawer open={selectedCitation !== null} onClose={() => setSelectedCitation(null)} title={selectedCitation ? t.citationTitle(selectedCitation.n) : ''}>
        {selectedCitation && <CitationDetail citation={selectedCitation} />}
      </Drawer>

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}

const bubbleBase = {
  alignSelf: 'flex-start' as const,
  maxWidth: '90%',
  background: 'var(--surface-card)',
  border: 'var(--stroke-hairline) solid var(--border-subtle)',
  borderRadius: 'var(--radius-md)',
  padding: '14px 18px',
  fontSize: 'var(--fs-ui-md)',
  lineHeight: 'var(--lh-body)',
  color: 'var(--text-body)',
  display: 'flex' as const,
  flexDirection: 'column' as const,
  gap: 'var(--space-2)',
};

function LiveBubble({ state, onCitationClick }: { state: ReturnType<typeof useChatStream>['state']; onCitationClick: (c: Citation) => void }) {
  const { t } = useLang();
  const statusKey = state.statusNode && state.statusNode in STATUS_NODE_KEY ? STATUS_NODE_KEY[state.statusNode as keyof typeof STATUS_NODE_KEY] : null;

  return (
    <div style={bubbleBase}>
      {state.answer ? (
        <MessageBody text={state.answer} citations={state.citations} onCitationClick={onCitationClick} />
      ) : (
        <span className="chat-status-pulse" style={{ color: 'var(--text-muted)' }}>{statusKey ? t[statusKey] : t.chatSending}</span>
      )}
    </div>
  );
}

function TurnBubbles({ turn, onCitationClick }: { turn: Turn; onCitationClick: (c: Citation) => void }) {
  const { t } = useLang();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div
        style={{
          alignSelf: 'flex-end',
          maxWidth: '78%',
          background: 'var(--xy-red-700)',
          color: '#fff',
          borderRadius: 'var(--radius-md)',
          padding: '14px 18px',
          fontSize: 'var(--fs-ui-md)',
          whiteSpace: 'pre-wrap',
        }}
      >
        {turn.question}
      </div>
      <div style={bubbleBase}>
        {!turn.complete && <Badge tone="brand">{t.chatInterrupted}</Badge>}
        <MessageBody text={turn.answer} citations={turn.citations} onCitationClick={onCitationClick} />
        {turn.citations.length > 0 && (
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginTop: 'var(--space-2)' }}>
            {turn.citations.map((c) => {
              const label = citationShortLabel(c);
              return (
                <Pill key={c.n} size="sm" tone="soft" style={{ cursor: 'pointer' }}>
                  <span onClick={() => onCitationClick(c)}>
                    [{c.n}]{label && ` ${label}`}
                  </span>
                </Pill>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function CitationDetail({ citation }: { citation: Citation }) {
  const { t } = useLang();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <Badge tone="neutral">{t[SOURCE_LABEL_KEY[citation.source]]}</Badge>
      <div>
        <div style={{ fontSize: 'var(--fs-ui-xs)', letterSpacing: 'var(--ls-caps)', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>
          {t.citationPages}
        </div>
        <div style={{ fontSize: 'var(--fs-ui-sm)', color: 'var(--text-body)' }}>
          {citation.pages.length > 0 ? citation.pages.join(', ') : t.citationNone}
        </div>
      </div>
      {citation.headings.length > 0 && (
        <div>
          <div style={{ fontSize: 'var(--fs-ui-xs)', letterSpacing: 'var(--ls-caps)', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>
            {t.citationHeadings}
          </div>
          <div style={{ fontSize: 'var(--fs-ui-sm)', color: 'var(--text-body)' }}>{citation.headings.join(' › ')}</div>
        </div>
      )}
      <div
        style={{
          fontSize: 'var(--fs-ui-sm)',
          lineHeight: 'var(--lh-body)',
          color: 'var(--text-body)',
          whiteSpace: 'pre-wrap',
          background: 'var(--surface-subtle)',
          border: 'var(--stroke-hairline) solid var(--border-subtle)',
          borderRadius: 'var(--radius-sm)',
          padding: 'var(--space-4)',
        }}
      >
        {citation.text}
      </div>
    </div>
  );
}
