import type { DocumentStatus } from '../lib/api';
import { stagesFor, statusLabel } from '../lib/status';
import { useLang } from '../lib/i18n';

interface StageTrackProps {
  status: DocumentStatus;
  mode: 'short' | 'long' | null;
}

export function StageTrack({ status, mode }: StageTrackProps) {
  const { t } = useLang();
  const stages = stagesFor(mode);
  const currentIndex = stages.indexOf(status);

  return (
    <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--space-1)' }}>
      {stages.map((stage, i) => {
        const state = i < currentIndex ? 'done' : i === currentIndex ? 'current' : 'upcoming';
        return (
          <span key={stage} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-1)' }}>
            <span
              style={{
                fontSize: 'var(--fs-ui-xs)',
                fontWeight: state === 'current' ? 'var(--fw-semibold)' : 'var(--fw-regular)',
                color:
                  state === 'current'
                    ? 'var(--brand-primary)'
                    : state === 'done'
                      ? 'var(--text-muted)'
                      : 'var(--border-strong)',
              }}
            >
              {statusLabel(stage, t)}
            </span>
            {i < stages.length - 1 && (
              <span style={{ color: 'var(--border-subtle)', fontSize: 'var(--fs-ui-xs)' }}>→</span>
            )}
          </span>
        );
      })}
    </div>
  );
}
