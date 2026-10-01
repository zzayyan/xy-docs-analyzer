import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, type Citation, type Region } from '../lib/api';
import { useLang } from '../lib/i18n';
import { highlightStyle } from '../lib/citations';
import { DocumentViewer } from './DocumentViewer';

const SOURCE_LABEL_KEY = {
  vector: 'citationSourceVector',
  tree: 'citationSourceTree',
  kg: 'citationSourceKg',
  kg_facts: 'citationSourceKgFacts',
  table: 'citationSourceTable',
} as const;

/** Docked beside the conversation instead of a modal overlay, so the answer that cites it stays
 * readable while the source is open. */
export function SourcePanel({
  docId,
  citation,
  onClose,
  pulse = false,
  citations = [],
}: {
  docId: string;
  citation: Citation;
  onClose: () => void;
  /** Opened by "follow sources" during a streaming answer: the highlight pulses and scrolls in smoothly */
  pulse?: boolean;
  /** The citations this one came with (one answer's, one row's, one entity's), to step through in the
   * document viewer */
  citations?: Citation[];
}) {
  const { t } = useLang();
  // Same query key ChatPanel already uses for its own reasons, so this reads from cache there instead
  // of firing a second request; TablePanel, which fetches no document today, gets this one for free.
  const doc = useQuery({ queryKey: ['document', docId], queryFn: () => api.getDocument(docId) }).data;

  const [viewing, setViewing] = useState(false);

  useEffect(() => {
    // Escape in the document viewer closes only the viewer
    if (viewing) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, viewing]);

  const rows: [string, string][] = [
    [t.citationSource, t[SOURCE_LABEL_KEY[citation.source]]],
    [t.citationPages, citation.pages.length > 0 ? citation.pages.join(', ') : '-'],
  ];
  if (citation.headings.length > 0) rows.push([t.citationHeadings, citation.headings.join(' / ')]);

  // Non-PDF Documents, Documents without a kept Original, and a citation whose chunk predates
  // Highlights (no regions) all keep the plain text view -- unconditionally, no migration needed.
  const showPage = !!doc?.has_original && doc.name.toLowerCase().endsWith('.pdf') && citation.regions.length > 0;
  const canView = showPage && !!doc.page_count;
  // The viewer steps through the siblings that point somewhere in the document, this one included
  const withRegions = citations.filter((c) => c.regions.length > 0);
  const startIndex = withRegions.findIndex((c) => c.chunk_id === citation.chunk_id && c.n === citation.n);
  const viewerCitations = startIndex >= 0 ? withRegions : [citation];

  return (
    // Delimited, not concatenated: chunk_id ends in digits, so "f:1"+"23" and "f:12"+"3" would collide,
    // and PageHighlightView's page state relies on this key changing for every new citation.
    <aside className="source-panel" key={`${citation.chunk_id}#${citation.n}`}>
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
        <div style={{ display: 'flex', gap: 4 }}>
          {canView && (
            <button className="quiet-button" onClick={() => setViewing(true)}>
              {t.viewerOpen}
            </button>
          )}
          <button className="quiet-button" onClick={onClose}>
            {t.citationClose}
          </button>
        </div>
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

        {showPage ? (
          <PageHighlightView
            docId={docId}
            regions={citation.regions}
            pulse={pulse}
            onOpen={canView ? () => setViewing(true) : undefined}
          />
        ) : (
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
        )}
      </div>

      {viewing && doc?.page_count && (
        <DocumentViewer
          docId={docId}
          name={doc.name}
          pageCount={doc.page_count}
          citations={viewerCitations}
          startIndex={Math.max(startIndex, 0)}
          onClose={() => setViewing(false)}
        />
      )}
    </aside>
  );
}

/** The Original's page with every region of the cited Chunk marked as a Highlight, and page
 * navigation when the Chunk spans several. A child of SourcePanel's keyed <aside>: that key resets
 * this component's state whenever the citation changes, so "current page" needs no effect to reset. */
function PageHighlightView({
  docId,
  regions,
  pulse,
  onOpen,
}: {
  docId: string;
  regions: Region[];
  pulse: boolean;
  /** Opens the whole document; the page becomes a button for it */
  onOpen?: () => void;
}) {
  const { t } = useLang();
  const pages = [...new Set(regions.map((r) => r.page))].sort((a, b) => a - b);
  const [page, setPage] = useState(pages[0]);
  const index = pages.indexOf(page);
  const firstHighlightRef = useRef<HTMLDivElement>(null);

  const onPage = regions.filter((r) => r.page === page);

  return (
    <div style={{ marginTop: 16, paddingTop: 16, borderTop: 'var(--stroke-hairline) solid var(--border-subtle)' }}>
      {pages.length > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <button
            className="quiet-button"
            aria-label={t.citationPrevPage}
            disabled={index === 0}
            onClick={() => setPage(pages[index - 1])}
          >
            ‹
          </button>
          <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>{t.citationPageOf(index + 1, pages.length)}</span>
          <button
            className="quiet-button"
            aria-label={t.citationNextPage}
            disabled={index === pages.length - 1}
            onClick={() => setPage(pages[index + 1])}
          >
            ›
          </button>
        </div>
      )}

      <div
        style={{ position: 'relative', cursor: onOpen ? 'zoom-in' : undefined }}
        role={onOpen ? 'button' : undefined}
        tabIndex={onOpen ? 0 : undefined}
        aria-label={onOpen ? t.viewerOpen : undefined}
        title={onOpen ? t.viewerOpen : undefined}
        onClick={onOpen}
        onKeyDown={(e) => {
          if (onOpen && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            onOpen();
          }
        }}
      >
        <img
          src={api.pageImageUrl(docId, page)}
          alt=""
          style={{ display: 'block', width: '100%', height: 'auto', borderRadius: 'var(--radius-sm)' }}
          // "opens at the first marked region": scroll it into view once the page has a real size
          onLoad={() => firstHighlightRef.current?.scrollIntoView({ block: 'center', behavior: pulse ? 'smooth' : 'auto' })}
        />
        {onPage.map((r, i) => (
          <div
            key={i}
            ref={i === 0 ? firstHighlightRef : undefined}
            className={pulse ? 'highlight-pulse' : undefined}
            style={highlightStyle(r)}
          />
        ))}
      </div>
    </div>
  );
}
