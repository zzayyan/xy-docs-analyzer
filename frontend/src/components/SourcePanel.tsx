import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, type Citation, type Region } from '../lib/api';
import { useLang } from '../lib/i18n';
import { highlightStyle } from '../lib/citations';
import { BlockView, BlockViewer } from './BlockView';
import { DocumentViewer } from './DocumentViewer';

const SOURCE_LABEL_KEY = {
  vector: 'citationSourceVector',
  tree: 'citationSourceTree',
  kg: 'citationSourceKg',
  kg_facts: 'citationSourceKgFacts',
  table: 'citationSourceTable',
} as const;

/** Docked beside the conversation, not a modal, so the citing answer stays readable. */
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
  /** Opened by "follow sources": the highlight pulses and scrolls smoothly */
  pulse?: boolean;
  /** Citations to step through in the document viewer */
  citations?: Citation[];
}) {
  const { t } = useLang();
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

  // A PDF or a picture shows its page; any other format its converted text; a Document converted before
  // either was kept, or a citation with nothing to mark, the plain text
  const paged = !!doc?.page_count;
  const showPage = paged && citation.regions.length > 0;
  const view = useQuery({
    queryKey: ['view', docId],
    queryFn: () => api.view(docId),
    enabled: !!doc && !paged && citation.refs.length > 0,
    retry: false,
    staleTime: Infinity,
  }).data;
  const blockView = !paged && citation.refs.length > 0 ? view : undefined;
  const canView = showPage || !!blockView;
  const marked = citations.filter((c) => (paged ? c.regions.length > 0 : c.refs.length > 0));
  const startIndex = marked.findIndex((c) => c.chunk_id === citation.chunk_id && c.n === citation.n);
  const viewerCitations = startIndex >= 0 ? marked : [citation];

  return (
    // Delimited: chunk_id ends in digits, so "f:1"+"23" would collide with "f:12"+"3"
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
        ) : blockView ? (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: 'var(--stroke-hairline) solid var(--border-subtle)' }}>
            {/* A calculation shows what was computed, so a wrong column or filter is visible */}
            {citation.source === 'table' && <pre className="table-result">{citation.text}</pre>}
            <BlockView view={blockView} refs={citation.refs} pulse={pulse} />
          </div>
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

      {viewing && blockView && doc && (
        <BlockViewer
          name={doc.name}
          view={blockView}
          citations={viewerCitations}
          startIndex={Math.max(startIndex, 0)}
          onClose={() => setViewing(false)}
        />
      )}

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

/** The cited page with its Highlights. The parent's key resets this state on every new citation. */
function PageHighlightView({
  docId,
  regions,
  pulse,
  onOpen,
}: {
  docId: string;
  regions: Region[];
  pulse: boolean;
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
