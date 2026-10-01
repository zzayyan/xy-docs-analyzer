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
