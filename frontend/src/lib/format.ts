import type { Lang } from './i18n';

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 1000 * 60 * 60 * 24 * 365],
  ['month', 1000 * 60 * 60 * 24 * 30],
  ['day', 1000 * 60 * 60 * 24],
  ['hour', 1000 * 60 * 60],
  ['minute', 1000 * 60],
];

/** "3 hours ago" / "3 jam lalu" via the platform's own locale data — no date library needed. */
export function formatRelative(epochMs: number, lang: Lang, justNow: string): string {
  const diffMs = epochMs - Date.now();
  for (const [unit, ms] of UNITS) {
    const value = diffMs / ms;
    if (Math.abs(value) >= 1) {
      return new Intl.RelativeTimeFormat(lang, { numeric: 'auto' }).format(Math.round(value), unit);
    }
  }
  return justNow;
}
