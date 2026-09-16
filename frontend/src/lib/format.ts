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

/** Plain "2m 30s" / "1h 5m" duration, no locale needed — this is a bare interval, not a point in
 * time, so Intl.RelativeTimeFormat (which always says "ago"/"in") doesn't fit. */
export function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

/** Naive linear ETA from elapsed time and fraction complete. Undefined when progress hasn't
 * moved yet (nothing to extrapolate from) or is already at/past 1 (nothing left to wait for). */
export function estimateRemaining(elapsedMs: number, progress: number): number | undefined {
  if (progress <= 0 || progress >= 1) return undefined;
  return elapsedMs * (1 - progress) / progress;
}
