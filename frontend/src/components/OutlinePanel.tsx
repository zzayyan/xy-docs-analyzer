import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, type Section } from '../lib/api';
import { useLang } from '../lib/i18n';

/** Section tree for a long-mode document, built client-side from the flat list app/store.py
 * returns (each row carries parent_id). Selecting a section loads its own chunks on the right. */
export function OutlinePanel({ docId }: { docId: string }) {
  const { t } = useLang();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const sectionsQuery = useQuery({ queryKey: ['sections', docId], queryFn: () => api.listSections(docId) });
  const sections = sectionsQuery.data ?? [];
  const selected = sections.find((s) => s.id === selectedId) ?? null;

  if (sectionsQuery.isPending) return null;
  if (sections.length === 0) {
    return <p style={{ margin: 0, padding: 'var(--space-6)', color: 'var(--text-muted)' }}>{t.outlineEmpty}</p>;
  }

  const byParent = new Map<string | null, Section[]>();
  for (const s of sections) {
    const siblings = byParent.get(s.parent_id) ?? [];
    siblings.push(s);
    byParent.set(s.parent_id, siblings);
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 300px) minmax(0, 1fr)', height: '100%' }}>
      <nav
        style={{
          overflowY: 'auto',
          padding: '12px 10px',
          borderRight: 'var(--stroke-hairline) solid var(--border-subtle)',
          background: 'var(--surface-page)',
        }}
      >
        <SectionList parentId={null} depth={0} byParent={byParent} selectedId={selectedId} onSelect={setSelectedId} />
      </nav>
      <div style={{ overflowY: 'auto', minWidth: 0 }}>
        {selected ? (
          <SectionDetail docId={docId} section={selected} />
        ) : (
          <p style={{ margin: 0, padding: 'var(--space-6)', color: 'var(--text-muted)' }}>{t.outlineSelectSection}</p>
        )}
      </div>
    </div>
  );
}

interface SectionListProps {
  parentId: string | null;
  depth: number;
  byParent: Map<string | null, Section[]>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function SectionList({ parentId, depth, byParent, selectedId, onSelect }: SectionListProps) {
  const { t } = useLang();
  return (
    <>
      {(byParent.get(parentId) ?? []).map((section) => (
        <div key={section.id}>
          <button
            className="outline-node"
            aria-current={section.id === selectedId}
            onClick={() => onSelect(section.id)}
            style={{ paddingLeft: 8 + depth * 14 }}
          >
            <span className="truncate">{section.title}</span>
            {section.start_page !== null && section.end_page !== null && (
              <span style={{ flex: '0 0 auto', fontSize: 11, color: 'var(--text-muted)', fontWeight: 'var(--fw-regular)' }}>
                {t.outlinePageRange(section.start_page, section.end_page)}
              </span>
            )}
          </button>
          <SectionList parentId={section.id} depth={depth + 1} byParent={byParent} selectedId={selectedId} onSelect={onSelect} />
        </div>
      ))}
    </>
  );
}

function SectionDetail({ docId, section }: { docId: string; section: Section }) {
  const { t } = useLang();
  const chunksQuery = useQuery({
    queryKey: ['sectionChunks', docId, section.id],
    queryFn: () => api.listSectionChunks(docId, section.id),
  });
  const chunks = chunksQuery.data ?? [];
  const meta = [
    section.start_page !== null && section.end_page !== null ? t.outlinePageRange(section.start_page, section.end_page) : null,
    t.outlineChunkCount(section.chunks),
  ].filter(Boolean);

  return (
    <article style={{ maxWidth: 760, padding: '24px 28px 40px', display: 'flex', flexDirection: 'column', gap: 20 }}>
      <header style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <h2
          style={{
            margin: 0,
            fontSize: 'var(--fs-ui-lg)',
            fontWeight: 'var(--fw-semibold)',
            letterSpacing: 'var(--ls-title)',
            color: 'var(--text-title)',
            textWrap: 'balance',
          }}
        >
          {section.title}
        </h2>
        <span style={{ display: 'flex', gap: 10, fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
          {meta.map((m) => (
            <span key={m}>{m}</span>
          ))}
        </span>
        {/* app/ingest/tree.py summarizes a heading with no body text as "Contains: <children>";
            a childless one leaves a bare "Contains:", which isn't worth showing. */}
        {section.summary && section.summary.trim() !== 'Contains:' && (
          <p style={{ margin: '4px 0 0', lineHeight: 'var(--lh-body)', color: 'var(--text-card-body)' }}>{section.summary}</p>
        )}
      </header>

      {chunksQuery.isPending &&
        [90, 76, 84].map((w) => <div key={w} className="skeleton-block" style={{ height: 12, width: `${w}%` }} />)}

      {chunksQuery.isSuccess && chunks.length === 0 && (
        <p style={{ margin: 0, color: 'var(--text-muted)' }}>{t.outlineChunksEmpty}</p>
      )}

      {chunks.map((chunk) => (
        <section key={chunk.id} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {chunk.pages.length > 0 && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              {t.outlinePageRange(chunk.pages[0], chunk.pages[chunk.pages.length - 1])}
            </span>
          )}
          <p style={{ margin: 0, lineHeight: 1.65, color: 'var(--text-title)', whiteSpace: 'pre-wrap' }}>{chunk.text}</p>
        </section>
      ))}
    </article>
  );
}
