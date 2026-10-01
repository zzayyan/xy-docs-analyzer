import type { Region } from './api';

/** Every form a model writes a citation marker in: "[3]", "[4, 5]", "[4,5,6]", "[4; 5]", "[4-6]". Matching
 * only "[n]" left grouped markers as plain text, unclickable and invisible to "follow sources". */
export const CITE_GROUP = /\[(\d+(?:\s*[,;–-]\s*\d+)*)\]/g;

// A range wider than this is not a citation (a year span, a page range) and is left as written
const MAX_RANGE = 20;

/** The citation numbers in one marker's inside: "4, 5" -> [4, 5], "4-6" -> [4, 5, 6]. */
export function citeNumbers(group: string): number[] {
  const numbers: number[] = [];
  for (const part of group.split(/\s*[,;]\s*/)) {
    const [from, to] = part.split(/\s*[–-]\s*/).map(Number);
    if (to === undefined) numbers.push(from);
    else if (to >= from && to - from < MAX_RANGE) for (let n = from; n <= to; n++) numbers.push(n);
  }
  return numbers;
}

/** A Highlight over its page, in percent of the page so it stays in place at any zoom */
export const highlightStyle = (r: Region) =>
  ({
    position: 'absolute',
    pointerEvents: 'none',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--brand-accent)',
    background: 'color-mix(in srgb, var(--brand-accent) 28%, transparent)',
    left: `${(100 * r.l) / r.page_width}%`,
    top: `${(100 * r.t) / r.page_height}%`,
    width: `${(100 * (r.r - r.l)) / r.page_width}%`,
    height: `${(100 * (r.b - r.t)) / r.page_height}%`,
  }) as const;
