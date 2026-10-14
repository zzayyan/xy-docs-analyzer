import Markdown, { defaultUrlTransform, type Components } from 'react-markdown';
import type { Citation } from '../lib/api';
import { CITE_GROUP, citeNumbers } from '../lib/citations';

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

/** Markdown with [n] markers turned into cite:n links, which the `a` override renders as citation pills. */
export function MessageBody({ text, citations, onCitationClick }: MessageBodyProps) {
  // "[4, 5]" becomes two pills, but only when every number is a real citation: "[2021-2023]" stays text
  const known = new Set(citations.map((c) => c.n));
  const withCitationLinks = text.replace(CITE_GROUP, (match, group: string) => {
    const numbers = citeNumbers(group);
    return numbers.length > 0 && numbers.every((n) => known.has(n))
      ? numbers.map((n) => `[${n}](${CITE_PREFIX}${n})`).join('')
      : match;
  });

  const components: Components = {
    p: ({ children }) => <p style={{ margin: 0 }}>{children}</p>,
    ul: ({ children }) => <ul style={listStyle}>{children}</ul>,
    ol: ({ children }) => <ol style={listStyle}>{children}</ol>,
    li: ({ children }) => <li>{children}</li>,
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
              display: 'inline-block',
              minWidth: 16,
              padding: '0 4px',
              margin: '0 1px',
              position: 'relative',
              top: -1,
              border: 'none',
              borderRadius: 4,
              background: 'var(--surface-brand-tint)',
              color: 'var(--brand-primary)',
              fontSize: 10.5,
              lineHeight: '16px',
              fontWeight: 'var(--fw-semibold)',
              textAlign: 'center',
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, color: 'var(--text-title)', lineHeight: 1.65 }}>
      {/* defaultUrlTransform blanks unknown schemes, cite: included */}
      <Markdown components={components} urlTransform={(url) => (url.startsWith(CITE_PREFIX) ? url : defaultUrlTransform(url))}>
        {withCitationLinks}
      </Markdown>
    </div>
  );
}
