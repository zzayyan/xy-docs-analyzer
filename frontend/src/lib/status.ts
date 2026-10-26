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
