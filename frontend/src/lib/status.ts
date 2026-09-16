import type { DocumentStatus } from './api';
import type { Dict } from './i18n';

export const STATUS_TONE: Record<DocumentStatus, 'brand' | 'accent' | 'secure' | 'neutral'> = {
  queued: 'neutral',
  converting: 'accent',
  embedding: 'accent',
  building_tree: 'accent',
  extracting_graph: 'accent',
  done: 'secure',
  error: 'brand',
};

export function statusLabel(status: DocumentStatus, t: Dict): string {
  return {
    queued: t.statusQueued,
    converting: t.statusConverting,
    embedding: t.statusEmbedding,
    building_tree: t.statusBuildingTree,
    extracting_graph: t.statusExtractingGraph,
    done: t.statusDone,
    error: t.statusError,
  }[status];
}

/** The stage sequence a document actually goes through, per app/ingest/pipeline.py: short-mode
 * documents skip straight from embedding to done. mode is null until conversion finishes (it's
 * set in the same write that moves status to "embedding"), so before that we show the short path
 * as a best guess — never wrong, since both paths share this prefix. */
export function stagesFor(mode: 'short' | 'long' | null): DocumentStatus[] {
  const base: DocumentStatus[] = ['queued', 'converting', 'embedding'];
  return mode === 'long' ? [...base, 'building_tree', 'extracting_graph', 'done'] : [...base, 'done'];
}
