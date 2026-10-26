import { ProgressBar } from '../design-system';
import { isInFlight, type Document, type DocumentStatus } from '../lib/api';
import { formatDuration, estimateRemaining } from '../lib/format';
import { statusLabel } from '../lib/status';
import { useLang, type Dict } from '../lib/i18n';

const STAGES: DocumentStatus[] = ['queued', 'converting', 'embedding', 'building_tree', 'extracting_graph', 'done'];
const LONG_ONLY: DocumentStatus[] = ['building_tree', 'extracting_graph'];

const STEP_UNIT: Partial<Record<DocumentStatus, 'unitPages' | 'unitChunks' | 'unitSections'>> = {
  converting: 'unitPages',
  embedding: 'unitChunks',
  building_tree: 'unitSections',
  extracting_graph: 'unitChunks',
};

type StageState = 'done' | 'current' | 'failed' | 'upcoming' | 'skipped';

const joined = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' · ');

/** What a stage produced or decided, as far as the Document knows yet. */
function findings(stage: DocumentStatus, state: StageState, doc: Document, t: Dict, compact: (n: number) => string): string[] {
  if (state === 'skipped') return [t.stageSkipped];
  if (state === 'failed') return [t.stageFailed];
  const done = state === 'done';
  switch (stage) {
    case 'queued':
      return state === 'current' ? [t.stageQueuedHint] : [];
    case 'converting':
      return [
        // page_count is only sent for PDFs, the only format OCR applies to
        doc.page_count
          ? joined(
              `${doc.page_count} ${t.unitPages}`,
              doc.ocr_pages !== null && (doc.ocr_pages ? t.ocrPages(doc.ocr_pages, doc.page_count) : t.ocrOff),
            )
          : '',
        joined(
          doc.tokens !== null && doc.chunks !== null && t.stageTokensChunks(compact(doc.tokens), doc.chunks),
          doc.language && t.stageLanguage(doc.language),
        ),
        doc.mode && doc.tokens !== null && doc.long_doc_tokens !== null
          ? t.stageMode(doc.mode === 'long', compact(doc.tokens), compact(doc.long_doc_tokens))
          : '',
      ];
    case 'embedding':
      return [done && doc.chunks !== null ? t.stageEmbedded(doc.chunks) : ''];
    case 'building_tree':
      return [done && doc.sections !== null ? t.stageSummarized(doc.sections) : ''];
    case 'extracting_graph':
      return [
        joined(
          done && doc.entities !== null && doc.chunks !== null && t.stageEntities(doc.entities, doc.chunks),
          done && !!doc.graph_skipped && t.stageGraphSkipped(doc.graph_skipped),
        ),
      ];
    case 'done': {
      const first = doc.timeline[0];
      const finished = doc.timeline.find((s) => s.stage === 'done');
      return [first && finished ? t.stageTotal(formatDuration(finished.started_at - first.started_at)) : ''];
    }
    default:
      return [];
  }
}

export function IngestProgress({ doc }: { doc: Document }) {
  const { t, lang } = useLang();
  const compact = (n: number) => new Intl.NumberFormat(lang, { notation: 'compact', maximumFractionDigits: 1 }).format(n);
  const inFlight = isInFlight(doc.status);
  const { timeline } = doc;

  // ponytail: impure Date.now() in render; fine since polling re-renders every 2s, use a ticking clock if it must look live
  const now = Date.now();
  const startedAt = timeline[0]?.started_at ?? doc.created_at;
  const elapsedMs = inFlight && startedAt ? now - startedAt : null;
  const remainingMs = elapsedMs !== null ? estimateRemaining(elapsedMs, doc.progress) : undefined;

  // A failed Document sits on the stage it last entered; the startup sweep fails it without an 'error' entry
  const reached = doc.status === 'error' ? timeline.filter((s) => s.stage !== 'error').at(-1)?.stage : doc.status;
  const reachedIndex = reached ? STAGES.indexOf(reached) : -1;

  const stateOf = (stage: DocumentStatus, i: number): StageState => {
    if (doc.mode === 'short' && LONG_ONLY.includes(stage)) return 'skipped';
    if (doc.status === 'done' || i < reachedIndex) return 'done';
    if (i === reachedIndex) return doc.status === 'error' ? 'failed' : 'current';
    return 'upcoming';
  };

  const durationOf = (stage: DocumentStatus): number | undefined => {
    const i = timeline.findIndex((s) => s.stage === stage);
    const end = timeline[i + 1]?.started_at ?? (inFlight ? now : undefined);
    return i < 0 || end === undefined ? undefined : end - timeline[i].started_at;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {STAGES.map((stage, i) => {
          const state = stateOf(stage, i);
          const duration = stage === 'done' ? undefined : durationOf(stage);
          const lines = findings(stage, state, doc, t, compact).filter(Boolean);
          const unit = STEP_UNIT[stage];
          const last = i === STAGES.length - 1;
          return (
            <li key={stage} style={{ display: 'grid', gridTemplateColumns: '20px minmax(0, 1fr)', columnGap: 'var(--space-3)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <StageMarker state={state} />
                {!last && (
                  <span
                    style={{
                      flex: 1,
                      width: 2,
                      minHeight: 'var(--space-3)',
                      background: state === 'done' ? 'var(--status-secure)' : 'var(--border-subtle)',
                    }}
                  />
                )}
              </div>
              <div style={{ minWidth: 0, paddingBottom: last ? 0 : 'var(--space-4)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-3)', minHeight: 20 }}>
                  <span
                    style={{
                      fontSize: 'var(--fs-ui-sm)',
                      fontWeight: state === 'current' ? 'var(--fw-semibold)' : 'var(--fw-medium)',
                      color: LABEL_COLOR[state],
                    }}
                  >
                    {statusLabel(stage, t)}
                  </span>
                  {duration !== undefined && (
                    <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>
                      {formatDuration(duration)}
                    </span>
                  )}
                </div>
                {lines.map((line) => (
                  <div key={line} style={{ marginTop: 2, fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
                    {line}
                  </div>
                ))}
                {state === 'current' && unit && !!doc.step_total && (
                  <ProgressBar
                    style={{ marginTop: 'var(--space-2)' }}
                    value={((doc.step_done ?? 0) / doc.step_total) * 100}
                    label={`${t.docStepCount(doc.step_done ?? 0, doc.step_total)} ${t[unit]}`}
                  />
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {elapsedMs !== null && (
        <div style={{ display: 'flex', gap: 'var(--space-4)', fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
          <span>
            {t.docElapsedLabel}: {formatDuration(elapsedMs)}
          </span>
          {remainingMs !== undefined && <span>{t.docEtaLabel(formatDuration(remainingMs))}</span>}
        </div>
      )}
    </div>
  );
}

const LABEL_COLOR: Record<StageState, string> = {
  done: 'var(--text-title)',
  current: 'var(--brand-primary)',
  failed: 'var(--status-danger)',
  upcoming: 'var(--text-muted)',
  skipped: 'var(--text-muted)',
};

function StageMarker({ state }: { state: StageState }) {
  const base = {
    width: 20,
    height: 20,
    flexShrink: 0,
    boxSizing: 'border-box',
    borderRadius: '50%',
    display: 'grid',
    placeItems: 'center',
    fontSize: 11,
    fontWeight: 'var(--fw-bold)',
    color: 'var(--text-on-brand)',
  } as const;
  if (state === 'done') return <span style={{ ...base, background: 'var(--status-secure)' }}>✓</span>;
  if (state === 'failed') return <span style={{ ...base, background: 'var(--status-danger)' }}>✕</span>;
  if (state === 'current')
    return (
      <span style={{ ...base, border: '2px solid var(--brand-primary)' }}>
        <span className="pulse" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--brand-primary)' }} />
      </span>
    );
  return <span style={{ ...base, border: `2px ${state === 'skipped' ? 'dashed' : 'solid'} var(--border-strong)` }} />;
}
