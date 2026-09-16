import type { Citation } from '../lib/api';

const MARKER = /(\[\d+\])/g;

interface MessageBodyProps {
  text: string;
  citations: Citation[];
  onCitationClick: (citation: Citation) => void;
}

/** Plain text with [n] markers turned into clickable buttons, not markdown — splitting a string
 * on a regex is trivial; injecting interactive elements into parsed markdown needs a rehype
 * plugin, not worth it unless answers start actually containing markdown formatting. */
export function MessageBody({ text, citations, onCitationClick }: MessageBodyProps) {
  const segments = text.split(MARKER);

  return (
    <span style={{ whiteSpace: 'pre-wrap' }}>
      {segments.map((segment, i) => {
        const match = segment.match(/^\[(\d+)\]$/);
        const citation = match ? citations.find((c) => c.n === Number(match[1])) : undefined;
        if (!citation) return <span key={i}>{segment}</span>;
        return (
          <button
            key={i}
            onClick={() => onCitationClick(citation)}
            style={{
              display: 'inline',
              background: 'var(--surface-brand-tint)',
              color: 'var(--brand-primary)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              padding: '0 4px',
              margin: '0 1px',
              font: 'inherit',
              fontWeight: 'var(--fw-semibold)',
              cursor: 'pointer',
            }}
          >
            {segment}
          </button>
        );
      })}
    </span>
  );
}
