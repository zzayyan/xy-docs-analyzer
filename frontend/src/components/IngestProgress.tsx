import { ProgressBar } from '../design-system';
import { StageTrack } from './StageTrack';
import type { Document } from '../lib/api';
import { formatDuration, estimateRemaining } from '../lib/format';
import { statusLabel } from '../lib/status';
import { useLang } from '../lib/i18n';

const STEP_UNIT: Partial<Record<Document['status'], 'unitPages' | 'unitChunks' | 'unitSections'>> = {
  converting: 'unitPages',
  extracting_graph: 'unitChunks',
  building_tree: 'unitSections',
};

export function IngestProgress({ doc }: { doc: Document }) {
  const { t } = useLang();

  // ponytail: impure Date.now() in render; fine since polling re-renders every 2s, use a ticking clock if it must look live
  const startedAt = doc.created_at;
  const elapsedMs = startedAt ? Date.now() - startedAt : null;
  const remainingMs = elapsedMs !== null ? estimateRemaining(elapsedMs, doc.progress) : undefined;

  const unitKey = STEP_UNIT[doc.status];
  const stepLabel =
    unitKey && doc.step_total
      ? `${statusLabel(doc.status, t)}: ${t.docStepCount(doc.step_done ?? 0, doc.step_total)} ${t[unitKey]}`
      : statusLabel(doc.status, t);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <StageTrack status={doc.status} mode={doc.mode} />
      <ProgressBar value={doc.progress * 100} label={stepLabel} />
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
