import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '../design-system';
import { ConfirmDialog } from './ConfirmDialog';
import { MessageBody } from './MessageBody';
import { ModelSwitch } from './ModelSwitch';
import { SourcePanel } from './SourcePanel';
import { Toast } from './Toast';
import { api, ApiError, type Citation, type Turn } from '../lib/api';
import { useChatStream, type StreamState } from '../lib/useChatStream';
import { CITE_GROUP, citeNumbers } from '../lib/citations';
import { useLang } from '../lib/i18n';

const STATUS_NODE_KEY = {
  contextualize: 'chatStatusContextualize',
  vector_retrieve: 'chatStatusVectorRetrieve',
  tree_search: 'chatStatusTreeSearch',
  kg_retrieve: 'chatStatusKgRetrieve',
} as const;

interface Selected {
  key: string;
  citation: Citation;
  /** The answer's other citations, to step through in the document viewer */
  citations: Citation[];
  /** Opened by "follow sources" while the answer streams, not by the user: its highlight pulses */
  auto?: boolean;
}

// Each followed source stays up at least this long, so "[1][2][3]" streamed in half a second does not flicker
const FOLLOW_DWELL_MS = 1200;

/** The citations a streaming answer has used so far, in the order it first cited them. Graph facts have
 * no page to show, so they are not followed. */
function citedOrder(answer: string, citations: Citation[]): Citation[] {
  const byN = new Map(citations.filter((c) => c.source !== 'kg_facts').map((c) => [c.n, c]));
  const order: Citation[] = [];
  for (const match of answer.matchAll(CITE_GROUP)) {
    for (const n of citeNumbers(match[1])) {
      const citation = byN.get(n);
      if (citation && !order.includes(citation)) order.push(citation);
    }
  }
  return order;
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
  // "Follow sources": while an answer streams, the source panel moves to each source the moment the
  // answer first cites it. followPref is the user's switch; following is whether this answer still
  // follows -- any click on a source or the panel's close hands control back to the user.
  const [followPref, setFollowPref] = useState(true);
  const [following, setFollowing] = useState(false);
  const [shownCount, setShownCount] = useState(0);
  // The finished answer's citation order: an answer often streams in a few seconds while following it
  // takes FOLLOW_DWELL_MS per source, so the follow carries on through it after the stream has ended
  const [finishedCited, setFinishedCited] = useState<Citation[]>([]);
  // ...and all its citations, for the document viewer to step through once the stream state is gone
  const [finishedCitations, setFinishedCitations] = useState<Citation[]>([]);
  const lastShownAt = useRef(0);

  const [modelOverride, setModelOverride] = useState<string | null>(null);
  // Shares DocumentScreen.tsx's exact query key, so this reads from cache instead of firing a
  // second request for the same document.
  const documentQuery = useQuery({ queryKey: ['document', docId], queryFn: () => api.getDocument(docId) });
  const modelsQuery = useQuery({ queryKey: ['models'], queryFn: api.models });
  const model = modelOverride ?? documentQuery.data?.llm_model ?? modelsQuery.data?.default ?? null;

  const turnsQuery = useQuery({ queryKey: ['turns', docId], queryFn: () => api.listTurns(docId) });
  // The backend persists a Turn on success, failure and mid-stream disconnect alike, so every
  // terminal path refetches history, then drops the optimistic question once the real one is in.
  // Also refetches the document: a switched model is persisted server-side on the same request,
  // so this is what picks that up into documentQuery.data.llm_model (and DocumentScreen's header).
  const settle = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['turns', docId] }),
      queryClient.invalidateQueries({ queryKey: ['document', docId] }),
    ]);
    setPendingQuestion(null);
  };
  const stream = useChatStream(docId, {
    onDone: () => {
      setFinishedCited(cited);
      setFinishedCitations(stream.state.citations);
      settle();
    },
    onError: (message) => {
      setFinishedCited(cited);
      setFinishedCitations(stream.state.citations);
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
    // Not on a narrow screen, where the source panel covers the conversation it would be following
    const follow = followPref && !window.matchMedia('(max-width: 767px)').matches;
    setFollowing(follow);
    setShownCount(0);
    setFinishedCited([]);
    if (follow) setSelected(null);
    stream.send(question, model);
  };

  const cited = citedOrder(stream.state.answer, stream.state.citations);
  const next = following ? (streaming ? cited : finishedCited)[shownCount] : undefined;
  const nextSiblings = streaming ? stream.state.citations : finishedCitations;
  useEffect(() => {
    if (!next) return;
    const wait = shownCount === 0 ? 0 : Math.max(0, lastShownAt.current + FOLLOW_DWELL_MS - Date.now());
    const timer = setTimeout(() => {
      lastShownAt.current = Date.now();
      setShownCount((count) => count + 1);
      setSelected({ key: `live:${next.n}`, citation: next, citations: nextSiblings, auto: true });
    }, wait);
    return () => clearTimeout(timer);
  }, [next, shownCount, nextSiblings]);

  // A followed source should appear at once, so every cited page is fetched as soon as the sources are
  // known; page images are cached immutable, so the jump later is served from cache.
  const doc = documentQuery.data;
  const isPdf = !!doc?.has_original && doc.name.toLowerCase().endsWith('.pdf');
  useEffect(() => {
    if (!isPdf) return;
    for (const c of stream.state.citations) {
      if (c.regions.length > 0) new Image().src = api.pageImageUrl(docId, c.regions[0].page);
    }
  }, [stream.state.citations, isPdf, docId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns.length, pendingQuestion, stream.state.answer]);

  const select = (key: string, citation: Citation) => {
    setFollowing(false);
    const scope = key.slice(0, key.lastIndexOf(':'));
    const citations = turns.find((turn) => turn.id === scope)?.citations ?? stream.state.citations;
    setSelected((current) => (current?.key === key ? null : { key, citation, citations }));
  };

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
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', minHeight: 26, marginTop: 4, gap: 'var(--space-3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <ModelSwitch value={model} onChange={setModelOverride} choices={modelsQuery.data?.models ?? []} />
              <button
                type="button"
                className="chip"
                aria-pressed={followPref}
                onClick={() => {
                  setFollowPref((on) => !on);
                  setFollowing(false);
                }}
              >
                {t.chatFollowSources}
              </button>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.chatComposerHint}</span>
            </div>
            {turns.length > 0 && (
              <button className="quiet-button" onClick={() => setConfirmClear(true)} disabled={streaming}>
                {t.chatClear}
              </button>
            )}
          </div>
        </div>
      </div>

      {selected && (
        <SourcePanel
          docId={docId}
          citation={selected.citation}
          citations={selected.citations}
          pulse={selected.auto}
          onClose={() => {
            setFollowing(false);
            setSelected(null);
          }}
        />
      )}

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

function Sources({
  scope,
  citations,
  selectedKey,
  onSelect,
  stagger = false,
}: SourceSelection & { scope: string; citations: Citation[]; stagger?: boolean }) {
  if (citations.length === 0) return null;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {citations.map((c, i) => {
        const key = `${scope}:${c.n}`;
        const label = citationShortLabel(c);
        return (
          <button
            key={key}
            className={stagger ? 'chip chip-in' : 'chip'}
            style={stagger ? { animationDelay: `${i * 80}ms` } : undefined}
            aria-pressed={selectedKey === key}
            onClick={() => onSelect(key, c)}
            title={label}
          >
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
  if (!state.answer && state.citations.length > 0) {
    // Retrieval is done and the answer has not started: show what was found, as it was found
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <span className="pulse" style={{ color: 'var(--text-muted)' }}>
          {t.chatFoundSources(state.citations.length)}
        </span>
        <Sources scope="live" citations={state.citations} selectedKey={selectedKey} onSelect={onSelect} stagger />
      </div>
    );
  }
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
