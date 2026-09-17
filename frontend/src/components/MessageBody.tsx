import Markdown, { type Components } from 'react-markdown';
import type { Citation } from '../lib/api';

interface MessageBodyProps {
  text: string;
  citations: Citation[];
  onCitationClick: (citation: Citation) => void;
}

const CITE_PREFIX = 'cite:';

const headingStyle = {
  margin: 0,
  fontSize: 'var(--fs-ui-md)',
  fontWeight: 'var(--fw-semibold)',
  color: 'var(--text-title)',
} as const;

const listStyle = {
  margin: 0,
  paddingLeft: '1.25em',
  display: 'flex',
  flexDirection: 'column',
  gap: 4,
} as const;

/** LLM answers are markdown (headings, bold, numbered lists) with [n] citation markers inline
 * -- rendering them as plain text left every ** and * visible verbatim. Turning [n] into a real
 * markdown link (cite:n) lets react-markdown's own parser carry the marker through unharmed
 * (it's a standalone token, never inside a bold span in practice), then the `a` override below
 * intercepts that one URL scheme to render a clickable citation pill instead of a normal link;
 * anything else falls through to a real external link. */
export function MessageBody({ text, citations, onCitationClick }: MessageBodyProps) {
  const withCitationLinks = text.replace(/\[(\d+)\]/g, (_match, n) => `[${n}](${CITE_PREFIX}${n})`);

  const components: Components = {
    p: ({ children }) => <p style={{ margin: 0, lineHeight: 'var(--lh-body)' }}>{children}</p>,
    ul: ({ children }) => <ul style={listStyle}>{children}</ul>,
    ol: ({ children }) => <ol style={listStyle}>{children}</ol>,
    li: ({ children }) => <li style={{ lineHeight: 'var(--lh-body)' }}>{children}</li>,
    strong: ({ children }) => <strong style={{ fontWeight: 'var(--fw-semibold)' }}>{children}</strong>,
    h1: ({ children }) => <h3 style={headingStyle}>{children}</h3>,
    h2: ({ children }) => <h3 style={headingStyle}>{children}</h3>,
    h3: ({ children }) => <h4 style={headingStyle}>{children}</h4>,
    h4: ({ children }) => <h4 style={headingStyle}>{children}</h4>,
    code: ({ children }) => (
      <code
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.9em',
          background: 'var(--surface-subtle)',
          borderRadius: 'var(--radius-sm)',
          padding: '2px 5px',
        }}
      >
        {children}
      </code>
    ),
    pre: ({ children }) => (
      <pre
        style={{
          margin: 0,
          padding: 'var(--space-3)',
          background: 'var(--surface-subtle)',
          borderRadius: 'var(--radius-sm)',
          overflowX: 'auto',
          fontSize: 'var(--fs-ui-sm)',
        }}
      >
        {children}
      </pre>
    ),
    a: ({ href, children }) => {
      if (href?.startsWith(CITE_PREFIX)) {
        const n = Number(href.slice(CITE_PREFIX.length));
        const citation = citations.find((c) => c.n === n);
        if (!citation) return <>{children}</>;
        return (
          <button
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
            {children}
          </button>
        );
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--text-link)' }}>
          {children}
        </a>
      );
    },
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)', maxWidth: 'var(--measure)' }}>
      <Markdown components={components}>{withCitationLinks}</Markdown>
    </div>
  );
}
