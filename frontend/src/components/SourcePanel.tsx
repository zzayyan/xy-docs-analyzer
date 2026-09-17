import { useEffect } from 'react';
import type { Citation } from '../lib/api';
import { useLang } from '../lib/i18n';

const SOURCE_LABEL_KEY = {
  vector: 'citationSourceVector',
  tree: 'citationSourceTree',
  kg: 'citationSourceKg',
  kg_facts: 'citationSourceKgFacts',
  table: 'citationSourceTable',
} as const;

/** Docked beside the conversation instead of a modal overlay, so the answer that cites it stays
 * readable while the source is open. */
export function SourcePanel({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const { t } = useLang();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const rows: [string, string][] = [
    [t.citationSource, t[SOURCE_LABEL_KEY[citation.source]]],
    [t.citationPages, citation.pages.length > 0 ? citation.pages.join(', ') : '-'],
  ];
  if (citation.headings.length > 0) rows.push([t.citationHeadings, citation.headings.join(' / ')]);

  return (
    <aside className="source-panel" key={citation.chunk_id + citation.n}>
      <div
        style={{
          flex: '0 0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: 44,
          padding: '0 12px 0 20px',
          borderBottom: 'var(--stroke-hairline) solid var(--border-subtle)',
        }}
      >
        <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>{t.citationTitle(citation.n)}</span>
        <button className="quiet-button" onClick={onClose}>
          {t.citationClose}
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 20px 24px' }}>
        <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', columnGap: 16, rowGap: 6, fontSize: 'var(--fs-ui-xs)' }}>
          {rows.map(([label, value]) => (
            <div key={label} style={{ display: 'contents' }}>
              <dt style={{ color: 'var(--text-muted)' }}>{label}</dt>
              <dd style={{ margin: 0, color: 'var(--text-title)' }}>{value}</dd>
            </div>
          ))}
        </dl>
        <p
          style={{
            margin: '16px 0 0',
            paddingTop: 16,
            borderTop: 'var(--stroke-hairline) solid var(--border-subtle)',
            lineHeight: 'var(--lh-loose)',
            color: 'var(--text-body)',
            whiteSpace: 'pre-wrap',
          }}
        >
          {citation.text}
        </p>
      </div>
    </aside>
  );
}
