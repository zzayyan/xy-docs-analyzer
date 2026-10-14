import type { Lang } from './i18n';

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 1000 * 60 * 60 * 24 * 365],
  ['month', 1000 * 60 * 60 * 24 * 30],
  ['day', 1000 * 60 * 60 * 24],
  ['hour', 1000 * 60 * 60],
  ['minute', 1000 * 60],
];

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

export function formatDuration(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

/** Linear ETA; undefined before progress moves or once it is done. */
export function estimateRemaining(elapsedMs: number, progress: number): number | undefined {
  if (progress <= 0 || progress >= 1) return undefined;
  return elapsedMs * (1 - progress) / progress;
}
