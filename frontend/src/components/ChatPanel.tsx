import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '../design-system';
import { ConfirmDialog } from './ConfirmDialog';
import { MessageBody } from './MessageBody';
import { SourcePanel } from './SourcePanel';
import { Toast } from './Toast';
import { api, ApiError, type Citation, type Turn } from '../lib/api';
import { useChatStream, type StreamState } from '../lib/useChatStream';
import { useLang } from '../lib/i18n';

const STATUS_NODE_KEY = {
  vector_retrieve: 'chatStatusVectorRetrieve',
  tree_search: 'chatStatusTreeSearch',
  kg_retrieve: 'chatStatusKgRetrieve',
} as const;

interface Selected {
  key: string;
  citation: Citation;
}

/** Short hint for a source chip: the deepest heading, else a page range. */
function citationShortLabel(c: Citation): string {
  if (c.headings.length > 0) return c.headings[c.headings.length - 1];
  if (c.pages.length > 0) return c.pages.length === 1 ? `p. ${c.pages[0]}` : `p. ${c.pages[0]}-${c.pages[c.pages.length - 1]}`;
  return '';
}

export function ChatPanel({ docId }: { docId: string }) {
  const { t } = useLang();
  const queryClient = useQueryClient();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState('');
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [selected, setSelected] = useState<Selected | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const turnsQuery = useQuery({ queryKey: ['turns', docId], queryFn: () => api.listTurns(docId) });
  // The backend persists a Turn on success, failure and mid-stream disconnect alike, so every
  // terminal path refetches history, then drops the optimistic question once the real one is in.
  const settle = async () => {
    await queryClient.invalidateQueries({ queryKey: ['turns', docId] });
    setPendingQuestion(null);
  };
  const stream = useChatStream(docId, {
    onDone: settle,
    onError: (message) => {
      setToast(message);
      settle();
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => api.clearTurns(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['turns', docId] });
      setSelected(null);
      setConfirmClear(false);
    },
    onError: (error: unknown) => {
      setToast(error instanceof ApiError ? error.detail : t.errorGeneric);
      setConfirmClear(false);
    },
  });

  const turns = turnsQuery.data ?? [];
  const streaming = stream.state.status === 'streaming';

  const send = (text: string) => {
    const question = text.trim();
    if (!question || streaming) return;
    setDraft('');
    setPendingQuestion(question);
    stream.send(question);
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns.length, pendingQuestion, stream.state.answer]);

  const select = (key: string, citation: Citation) =>
    setSelected((current) => (current?.key === key ? null : { key, citation }));

  const showEmpty = turnsQuery.isSuccess && turns.length === 0 && pendingQuestion === null;

  return (
    <div className="chat-layout" data-sources={selected !== null}>
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0 }}>
        <div ref={scrollRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
          <div className="chat-column" style={{ display: 'flex', flexDirection: 'column', gap: 28, padding: '24px 24px 16px' }}>
            {showEmpty && <EmptyChat onPick={send} />}

            {turns.map((turn) => (
              <TurnView key={turn.id} turn={turn} selectedKey={selected?.key ?? null} onSelect={select} />
            ))}

            {pendingQuestion !== null && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <Question text={pendingQuestion} />
                <LiveAnswer state={stream.state} selectedKey={selected?.key ?? null} onSelect={select} />
              </div>
            )}
          </div>
        </div>

        <div className="chat-column" style={{ flex: '0 0 auto', padding: '8px 24px 14px' }}>
          <div className="composer">
            <textarea
              rows={1}
              value={draft}
              placeholder={t.chatPlaceholder}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send(draft);
                }
              }}
            />
            <Button size="sm" onClick={() => send(draft)} disabled={streaming || !draft.trim()}>
              {t.chatSend}
            </Button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', minHeight: 26, marginTop: 4 }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.chatComposerHint}</span>
            {turns.length > 0 && (
              <button className="quiet-button" onClick={() => setConfirmClear(true)} disabled={streaming}>
                {t.chatClear}
              </button>
            )}
          </div>
        </div>
      </div>

      {selected && <SourcePanel citation={selected.citation} onClose={() => setSelected(null)} />}

      <ConfirmDialog
        open={confirmClear}
        title={t.chatClearConfirmTitle}
        body={t.chatClearConfirmBody}
        danger
        onConfirm={() => clearMutation.mutate()}
        onCancel={() => setConfirmClear(false)}
      />

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}

function EmptyChat({ onPick }: { onPick: (question: string) => void }) {
  const { t } = useLang();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', paddingTop: 24 }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 'var(--fs-ui-md)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>
          {t.chatEmptyTitle}
        </h2>
        <p style={{ margin: '4px 0 0', color: 'var(--text-muted)' }}>{t.chatEmpty}</p>
      </div>
      <div style={{ display: 'grid', gap: 8 }}>
        {t.chatSuggestions.map((question) => (
          <button key={question} className="suggestion" onClick={() => onPick(question)}>
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}

function Question({ text }: { text: string }) {
  return (
    <div
      style={{
        alignSelf: 'flex-end',
        maxWidth: '85%',
        padding: '8px 12px',
        borderRadius: 'var(--radius-md)',
        background: 'var(--surface-subtle)',
        color: 'var(--text-title)',
        lineHeight: 'var(--lh-body)',
        whiteSpace: 'pre-wrap',
      }}
    >
      {text}
    </div>
  );
}

interface SourceSelection {
  selectedKey: string | null;
  onSelect: (key: string, citation: Citation) => void;
}

function Sources({ scope, citations, selectedKey, onSelect }: SourceSelection & { scope: string; citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {citations.map((c) => {
        const key = `${scope}:${c.n}`;
        const label = citationShortLabel(c);
        return (
          <button key={key} className="chip" aria-pressed={selectedKey === key} onClick={() => onSelect(key, c)} title={label}>
            <span style={{ color: 'var(--brand-primary)', fontWeight: 'var(--fw-semibold)' }}>{c.n}</span>
            {label && <span className="truncate">{label}</span>}
          </button>
        );
      })}
    </div>
  );
}

function TurnView({ turn, selectedKey, onSelect }: SourceSelection & { turn: Turn }) {
  const { t } = useLang();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Question text={turn.question} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {!turn.complete && (
          <span style={{ fontSize: 'var(--fs-ui-xs)', fontWeight: 'var(--fw-medium)', color: 'var(--status-warning)' }}>
            {t.chatInterrupted}
          </span>
        )}
        <MessageBody text={turn.answer} citations={turn.citations} onCitationClick={(c) => onSelect(`${turn.id}:${c.n}`, c)} />
        <Sources scope={turn.id} citations={turn.citations} selectedKey={selectedKey} onSelect={onSelect} />
      </div>
    </div>
  );
}

function LiveAnswer({ state, selectedKey, onSelect }: SourceSelection & { state: StreamState }) {
  const { t } = useLang();
  // Between "done" and the refetched turn arriving, the stream is already idle: render nothing
  // rather than flashing the "thinking" line again.
  if (state.status === 'idle') return null;
  if (!state.answer) {
    const key = state.statusNode && state.statusNode in STATUS_NODE_KEY ? STATUS_NODE_KEY[state.statusNode as keyof typeof STATUS_NODE_KEY] : null;
    return (
      <span className="pulse" style={{ color: 'var(--text-muted)' }}>
        {key ? t[key] : t.chatSending}
      </span>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <MessageBody text={state.answer} citations={state.citations} onCitationClick={(c) => onSelect(`live:${c.n}`, c)} />
      <Sources scope="live" citations={state.citations} selectedKey={selectedKey} onSelect={onSelect} />
    </div>
  );
}
