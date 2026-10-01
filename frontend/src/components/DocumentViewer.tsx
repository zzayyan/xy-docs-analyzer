import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { api, type Citation } from '../lib/api';
import { highlightStyle } from '../lib/citations';
import { useLang } from '../lib/i18n';

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;
// Width of every page at 100%; past the dialog's own width, the pages scroll sideways
const PAGE_WIDTH = 820;

const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(z / ZOOM_STEP) * ZOOM_STEP));

/** The whole Original, page after page, opened at a citation with its Highlights drawn, and stepping
 * through the citations it came with. Pages are the same rendered PNGs the source panel shows, loaded
 * lazily as they scroll near, so a long document costs only the pages actually looked at. Built on
 * native <dialog> like ConfirmDialog: focus trap and Escape come free. */
export function DocumentViewer({
  docId,
  name,
  pageCount,
  citations,
  startIndex,
  onClose,
}: {
  docId: string;
  name: string;
  pageCount: number;
  /** Only citations with regions: one without has nowhere in the document to point at */
  citations: Citation[];
  startIndex: number;
  onClose: () => void;
}) {
  const { t } = useLang();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);
  const highlightRef = useRef<HTMLDivElement>(null);
  const zoomAnchor = useRef<number | null>(null);
  const [index, setIndex] = useState(startIndex);
  const [zoom, setZoom] = useState(1);
  const citation = citations[index];
  const [page, setPage] = useState(citation.regions[0].page);

  // ponytail: every page placeholder takes the cited page's size; a document mixing page sizes shifts a
  // little as its pages load
  const { page_width: pageW, page_height: pageH } = citation.regions[0];

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  // Open at the citation, and move to each one stepped to
  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: 'center' });
  }, [index]);

  // Zooming keeps the same spot of the document in the middle of the view
  const changeZoom = (update: (z: number) => number) => {
    const el = scrollRef.current;
    if (el) zoomAnchor.current = (el.scrollTop + el.clientHeight / 2) / el.scrollHeight;
    setZoom((z) => clampZoom(update(z)));
  };
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || zoomAnchor.current === null) return;
    el.scrollTop = zoomAnchor.current * el.scrollHeight - el.clientHeight / 2;
    zoomAnchor.current = null;
  }, [zoom]);

  // Ctrl/⌘ + wheel zooms the pages, not the whole app. React's onWheel is passive and can't stop that.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      changeZoom((z) => z + (e.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  // The current page is the one under the middle of the view
  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const middle = el.scrollTop + el.clientHeight / 2;
    const i = pageRefs.current.findIndex((p) => p && p.offsetTop + p.offsetHeight > middle);
    if (i >= 0) setPage(i + 1);
  };

  const goToPage = (p: number) => {
    if (p >= 1 && p <= pageCount) pageRefs.current[p - 1]?.scrollIntoView({ block: 'start' });
  };

  const pages = Array.from({ length: pageCount }, (_, i) => i + 1);
  let firstHighlight = true;

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      // The dialog box is filled edge to edge by its content, so a click on the dialog itself is the backdrop
      onClick={(e) => e.target === e.currentTarget && dialogRef.current?.close()}
      style={{
        border: 'var(--stroke-hairline) solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: 0,
        width: 'min(1100px, 94vw)',
        height: '90vh',
        maxWidth: 'none',
        maxHeight: 'none',
        background: 'var(--surface-card)',
        color: 'var(--text-body)',
        boxShadow: 'var(--shadow-lg)',
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div
          style={{
            flex: '0 0 auto',
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: '6px 16px',
            padding: '8px 12px 8px 20px',
            borderBottom: 'var(--stroke-hairline) solid var(--border-subtle)',
            fontSize: 'var(--fs-ui-xs)',
          }}
        >
          <span className="truncate" style={{ flex: '1 1 160px', fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>
            {name}
          </span>

          {citations.length > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <button className="quiet-button" aria-label={t.viewerPrevCitation} disabled={index === 0} onClick={() => setIndex(index - 1)}>
                ‹
              </button>
              <span style={{ color: 'var(--text-muted)' }}>{t.viewerCitationOf(index + 1, citations.length)}</span>
              <button
                className="quiet-button"
                aria-label={t.viewerNextCitation}
                disabled={index === citations.length - 1}
                onClick={() => setIndex(index + 1)}
              >
                ›
              </button>
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <button className="quiet-button" aria-label={t.citationPrevPage} disabled={page <= 1} onClick={() => goToPage(page - 1)}>
              ‹
            </button>
            <span style={{ color: 'var(--text-muted)' }}>{t.citationPageOf(page, pageCount)}</span>
            <button className="quiet-button" aria-label={t.citationNextPage} disabled={page >= pageCount} onClick={() => goToPage(page + 1)}>
              ›
            </button>
            <input
              type="number"
              min={1}
              max={pageCount}
              placeholder={t.viewerGoToPage}
              aria-label={t.viewerGoToPage}
              onKeyDown={(e) => {
                if (e.key === 'Enter') goToPage(Number(e.currentTarget.value));
              }}
              style={{
                width: 96,
                padding: '3px 6px',
                font: 'inherit',
                color: 'var(--text-title)',
                background: 'var(--surface-subtle)',
                border: 'var(--stroke-hairline) solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
              }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <button className="quiet-button" aria-label={t.viewerZoomOut} disabled={zoom <= MIN_ZOOM} onClick={() => changeZoom((z) => z - ZOOM_STEP)}>
              −
            </button>
            <button className="quiet-button" onClick={() => changeZoom(() => 1)} style={{ minWidth: 48 }}>
              {Math.round(zoom * 100)}%
            </button>
            <button className="quiet-button" aria-label={t.viewerZoomIn} disabled={zoom >= MAX_ZOOM} onClick={() => changeZoom((z) => z + ZOOM_STEP)}>
              +
            </button>
          </div>

          <button className="quiet-button" onClick={() => dialogRef.current?.close()}>
            {t.citationClose}
          </button>
        </div>

        <div ref={scrollRef} onScroll={onScroll} style={{ flex: 1, minHeight: 0, overflow: 'auto', background: 'var(--surface-subtle)' }}>
          <div
            style={{
              width: `min(${PAGE_WIDTH * zoom}px, ${100 * zoom}%)`,
              margin: '0 auto',
              padding: '16px 16px 32px',
              boxSizing: 'border-box',
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
            }}
          >
            {pages.map((p) => (
              <div key={p} ref={(el) => void (pageRefs.current[p - 1] = el)}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{p}</div>
                <div style={{ position: 'relative', boxShadow: 'var(--shadow-sm)' }}>
                  <img
                    src={api.pageImageUrl(docId, p)}
                    alt=""
                    loading="lazy"
                    // Width and height only give the not-yet-loaded page its shape, so scrolling to a
                    // far page lands where it will be
                    width={pageW}
                    height={pageH}
                    style={{ display: 'block', width: '100%', height: 'auto', background: 'var(--surface-card)' }}
                  />
                  {citation.regions
                    .filter((r) => r.page === p)
                    .map((r, i) => {
                      const first = firstHighlight;
                      firstHighlight = false;
                      return (
                        <div
                          // Keyed by the citation too, so the pulse replays on every step to a citation
                          key={`${index}:${i}`}
                          ref={first ? highlightRef : undefined}
                          className="highlight-pulse"
                          style={highlightStyle(r)}
                        />
                      );
                    })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </dialog>
  );
}
