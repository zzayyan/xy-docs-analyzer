import { useEffect, useRef, useState } from 'react';
import type { Block, Citation, DocumentView } from '../lib/api';
import { viewerDialogStyle, viewerHeaderStyle } from '../lib/citations';
import { useLang } from '../lib/i18n';

/** A document without pages, as text: the cited blocks and table rows marked, the first scrolled into view. */
export function BlockView({ view, refs, pulse = false }: { view: DocumentView; refs: string[]; pulse?: boolean }) {
  const { t } = useLang();
  const rootRef = useRef<HTMLDivElement>(null);
  const cited = new Set(refs);
  const markClass = (marked: boolean) => (marked ? `block-mark${pulse ? ' highlight-pulse' : ''}` : undefined);

  // Keyed by the refs' content: a new array with the same refs must not scroll the reader back
  const refsKey = refs.join('|');
  useEffect(() => {
    rootRef.current?.querySelector('.block-mark')?.scrollIntoView({ block: 'center', behavior: pulse ? 'smooth' : 'auto' });
  }, [refsKey, pulse]);

  const renderBlock = (b: Block) => {
    if (b.type === 'table') {
      return (
        <div key={b.ref} className={`block-table ${markClass(cited.has(b.ref)) ?? ''}`}>
          <table>
            <tbody>
              {b.rows.map((row, i) => (
                <tr key={i} className={markClass(cited.has(`${b.ref}/rows/${i}`))}>
                  {row.map((cell, j) => (i === 0 ? <th key={j}>{cell}</th> : <td key={j}>{cell}</td>))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    const className = [`block-${b.type}`, markClass(cited.has(b.ref))].filter(Boolean).join(' ');
    if (b.type === 'heading') {
      return (
        <div key={b.ref} role="heading" aria-level={b.level} data-level={Math.min(b.level, 3)} className={className}>
          {b.text}
        </div>
      );
    }
    return (
      <p key={b.ref} className={className}>
        {b.text}
      </p>
    );
  };

  if (view.kind !== 'slides') {
    return (
      <div ref={rootRef} className="block-view">
        {view.blocks.map(renderBlock)}
      </div>
    );
  }

  // A block without a slide number stays on the slide before it
  const slides: { page: number | null; blocks: Block[] }[] = [];
  for (const b of view.blocks) {
    const last = slides.at(-1);
    if (last && (b.page === null || b.page === last.page)) last.blocks.push(b);
    else slides.push({ page: b.page, blocks: [b] });
  }
  return (
    <div ref={rootRef} className="block-view">
      {slides.map((slide, i) => (
        <section key={i} className="slide-card">
          {slide.page !== null && <div className="slide-label">{t.viewerSlide(slide.page)}</div>}
          {slide.blocks.map(renderBlock)}
        </section>
      ))}
    </div>
  );
}

/** The whole converted document in a dialog, stepping through the citations the way DocumentViewer does. */
export function BlockViewer({
  name,
  view,
  citations,
  startIndex,
  onClose,
}: {
  name: string;
  view: DocumentView;
  /** Only citations with refs: one without has nowhere to point */
  citations: Citation[];
  startIndex: number;
  onClose: () => void;
}) {
  const { t } = useLang();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [index, setIndex] = useState(startIndex);

  useEffect(() => {
    dialogRef.current?.showModal();
  }, []);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      // Content fills the dialog, so a click on the dialog itself is the backdrop
      onClick={(e) => e.target === e.currentTarget && dialogRef.current?.close()}
      style={viewerDialogStyle}
    >
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={viewerHeaderStyle}>
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

          <button className="quiet-button" onClick={() => dialogRef.current?.close()}>
            {t.citationClose}
          </button>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflow: 'auto', background: 'var(--surface-subtle)' }}>
          <div
            style={{
              maxWidth: 820,
              margin: '16px auto 32px',
              padding: '28px 36px',
              background: 'var(--surface-card)',
              boxShadow: 'var(--shadow-sm)',
            }}
          >
            {/* Keyed by citation, so the pulse replays on every step */}
            <BlockView key={index} view={view} refs={citations[index].refs} pulse />
          </div>
        </div>
      </div>
    </dialog>
  );
}
