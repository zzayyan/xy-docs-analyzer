import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Pill } from '../design-system';
import { api, type Chunk, type Section } from '../lib/api';
import { useLang } from '../lib/i18n';

/** Section tree for a long-mode document, built client-side from the flat list app/store.py
 * returns (each row already carries parent_id, resolved server-side from the HAS_CHILD edges --
 * see app/store.py's LIST_SECTIONS). Clicking a section loads its own chunks on the right; a
 * container heading with no direct text (tree.py's "Contains: ..." fallback) shows that instead. */
export function OutlinePanel({ docId }: { docId: string }) {
  const { t } = useLang();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const sectionsQuery = useQuery({ queryKey: ['sections', docId], queryFn: () => api.listSections(docId) });
  const sections = sectionsQuery.data ?? [];
  const selected = sections.find((s) => s.id === selectedId) ?? null;

  if (sectionsQuery.isPending) return null;
  if (sections.length === 0) {
    return (
      <p style={{ margin: 'var(--space-8) 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--fs-ui-sm)' }}>
        {t.outlineEmpty}
      </p>
    );
  }

  const byParent = new Map<string | null, Section[]>();
  for (const s of sections) {
    const key = s.parent_id;
    (byParent.get(key) ?? byParent.set(key, []).get(key)!).push(s);
  }

  return (
    <div style={{ display: 'flex', gap: 'var(--space-6)', height: '100%' }}>
      <nav style={{ flex: '0 0 320px', overflow: 'auto', borderRight: 'var(--stroke-hairline) solid var(--border-subtle)', paddingRight: 'var(--space-4)' }}>
        {(byParent.get(null) ?? []).map((section) => (
          <SectionNode key={section.id} section={section} byParent={byParent} selectedId={selectedId} onSelect={setSelectedId} />
        ))}
      </nav>
      <div style={{ flex: 1, minWidth: 0, overflow: 'auto' }}>
        {selected ? (
          <SectionDetail docId={docId} section={selected} />
        ) : (
          <p style={{ margin: 'var(--space-8) 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--fs-ui-sm)' }}>
            {t.outlineSelectSection}
          </p>
        )}
      </div>
    </div>
  );
}

function SectionNode({
  section,
  byParent,
  selectedId,
  onSelect,
}: {
  section: Section;
  byParent: Map<string | null, Section[]>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useLang();
  const children = byParent.get(section.id) ?? [];
  const active = section.id === selectedId;

  return (
    <details open style={{ marginLeft: section.level > 1 ? 'var(--space-4)' : 0 }}>
      <summary
        onClick={(e) => {
          // <summary>'s default click both toggles disclosure and would otherwise require a
          // second click to just select the section it labels -- selecting on every click (not
          // only the label) matches how a table-of-contents entry is expected to behave.
          e.preventDefault();
          onSelect(section.id);
        }}
        style={{
          cursor: 'pointer',
          listStyle: 'none',
          padding: '6px 8px',
          borderRadius: 'var(--radius-sm)',
          background: active ? 'var(--surface-brand-tint)' : 'transparent',
          color: active ? 'var(--brand-primary)' : 'var(--text-body)',
          fontWeight: active ? 'var(--fw-semibold)' : 'var(--fw-regular)',
          fontSize: 'var(--fs-ui-sm)',
        }}
      >
        {section.title}
        {section.start_page !== null && section.end_page !== null && (
          <span style={{ marginLeft: 8, fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
            {t.outlinePageRange(section.start_page, section.end_page)}
          </span>
        )}
      </summary>
      {children.map((child) => (
        <SectionNode key={child.id} section={child} byParent={byParent} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </details>
  );
}

function SectionDetail({ docId, section }: { docId: string; section: Section }) {
  const { t } = useLang();
  const chunksQuery = useQuery({
    queryKey: ['sectionChunks', docId, section.id],
    queryFn: () => api.listSectionChunks(docId, section.id),
  });
  const chunks = chunksQuery.data ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div>
        <h2 style={{ margin: 0, fontSize: 'var(--fs-ui-lg)', fontWeight: 'var(--fw-bold)', color: 'var(--text-title)' }}>
          {section.title}
        </h2>
        {/* app/ingest/tree.py falls back to "Contains: <child titles>" for a heading with no body
            text; when it also has no children (an empty-heading edge case its own ponytail:
            comment documents), that leaves a bare "Contains: " with nothing after the colon --
            skip rendering that rather than show a broken-looking sentence. */}
        {section.summary && section.summary.trim() !== 'Contains:' && (
          <p style={{ margin: '8px 0 0', fontSize: 'var(--fs-ui-sm)', color: 'var(--text-card-body)', lineHeight: 'var(--lh-body)' }}>
            {section.summary}
          </p>
        )}
        <div style={{ marginTop: 8, display: 'flex', gap: 'var(--space-2)' }}>
          {section.start_page !== null && section.end_page !== null && (
            <Pill size="sm" tone="neutral">
              {t.outlinePageRange(section.start_page, section.end_page)}
            </Pill>
          )}
          <Pill size="sm" tone="neutral">{t.outlineChunkCount(section.chunks)}</Pill>
        </div>
      </div>

      {!chunksQuery.isPending && chunks.length === 0 && (
        <p style={{ margin: 0, fontSize: 'var(--fs-ui-sm)', color: 'var(--text-muted)', fontStyle: 'italic' }}>
          {t.outlineChunksEmpty}
        </p>
      )}

      {chunks.map((chunk) => (
        <ChunkCard key={chunk.id} chunk={chunk} />
      ))}
    </div>
  );
}

function ChunkCard({ chunk }: { chunk: Chunk }) {
  const { t } = useLang();
  return (
    <div
      style={{
        background: 'var(--surface-card)',
        border: 'var(--stroke-hairline) solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-4)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
      }}
    >
      {chunk.pages.length > 0 && (
        <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
          {t.outlinePageRange(chunk.pages[0], chunk.pages[chunk.pages.length - 1])}
        </span>
      )}
      <p style={{ margin: 0, fontSize: 'var(--fs-ui-sm)', lineHeight: 'var(--lh-body)', color: 'var(--text-body)', whiteSpace: 'pre-wrap' }}>
        {chunk.text}
      </p>
    </div>
  );
}
