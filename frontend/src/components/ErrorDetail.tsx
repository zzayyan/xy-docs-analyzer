import { useState } from 'react';
import { useLang } from '../lib/i18n';

/** Ingest errors are the raw str() of a caught exception (see backend/app/ingest/pipeline.py),
 * which for a provider error can be a several-hundred-character Python dict repr. Shown in full
 * it dominates whatever it's next to (a table row, an Alert) — collapse it behind a toggle. */
export function ErrorDetail({ message, limit = 120 }: { message: string; limit?: number }) {
  const { t } = useLang();
  const [expanded, setExpanded] = useState(false);
  const isLong = message.length > limit;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
      <span
        style={{
          fontSize: 'var(--fs-ui-xs)',
          fontFamily: expanded ? 'var(--font-mono)' : undefined,
          whiteSpace: expanded ? 'pre-wrap' : 'nowrap',
          overflow: expanded ? 'visible' : 'hidden',
          textOverflow: expanded ? 'clip' : 'ellipsis',
          maxWidth: expanded ? 'none' : '100%',
        }}
      >
        {expanded || !isLong ? message : `${message.slice(0, limit)}…`}
      </span>
      {isLong && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          style={{
            alignSelf: 'flex-start',
            background: 'none',
            border: 'none',
            padding: 0,
            font: 'inherit',
            fontSize: 'var(--fs-ui-xs)',
            color: 'var(--text-link)',
            textDecoration: 'underline',
            cursor: 'pointer',
          }}
        >
          {expanded ? t.errorDetailsHide : t.errorDetailsShow}
        </button>
      )}
    </div>
  );
}
