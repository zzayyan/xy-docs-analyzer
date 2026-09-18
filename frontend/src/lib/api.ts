// Thin fetch wrapper over the FastAPI backend (backend/app/api.py). Types are hand-written to
// mirror its Pydantic response models rather than generated — see that file's models if this
// drifts; codegen from /openapi.json is worth it once the API grows past ~20 endpoints.

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export type DocumentStatus =
  | 'queued'
  | 'converting'
  | 'embedding'
  | 'building_tree'
  | 'extracting_graph'
  | 'done'
  | 'error';

export interface Limits {
  max_upload_mb: number;
  max_pages: number;
}

export interface ModelsInfo {
  models: string[];
  default: string;
}

export interface Document {
  id: string;
  name: string;
  status: DocumentStatus;
  progress: number;
  created_at: number | null;
  updated_at: number | null;
  mode: 'short' | 'long' | null;
  tokens: number | null;
  chunks: number | null;
  error: string | null;
  step_done: number | null;
  step_total: number | null;
  llm_model: string | null;
  has_original: boolean;
}

export interface Citation {
  n: number;
  chunk_id: string;
  pages: number[];
  headings: string[];
  source: 'vector' | 'tree' | 'kg' | 'kg_facts' | 'table';
  text: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  mode: 'short' | 'long';
  turn_id: string;
}

export interface Section {
  id: string;
  title: string;
  level: number;
  order: number;
  summary: string | null;
  start_page: number | null;
  end_page: number | null;
  parent_id: string | null;
  chunks: number;
}

export interface Chunk {
  id: string;
  idx: number;
  text: string;
  pages: number[];
  headings: string[];
}

export interface Turn {
  id: string;
  question: string;
  answer: string;
  citations: Citation[];
  mode: 'short' | 'long';
  complete: boolean;
  created_at: number;
}

export interface Column {
  name: string;
  description: string;
}

export interface Row {
  values: Record<string, string>;
  citations: Citation[];
}

export interface SuggestedTable {
  title: string;
  request: string;
  columns: Column[];
}

export type TableStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled';

export interface TableExtraction {
  id: string;
  request: string;
  columns: Column[];
  rows: Row[];
  status: TableStatus;
  progress: number;
  error: string | null;
  chunks_done: number | null;
  chunks_total: number | null;
  created_at: number;
  updated_at: number;
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) {
    // FastAPI's HTTPException body is {"detail": "..."}; fall back to the raw text
    // for anything that didn't go through that path (e.g. a proxy error page).
    const body = await res.text();
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
      // not JSON, use the raw text as-is
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  limits: () => request<Limits>('/limits'),

  models: () => request<ModelsInfo>('/models'),

  listDocuments: () => request<Document[]>('/documents'),

  getDocument: (id: string) => request<Document>(`/documents/${id}`),

  uploadDocument: async (file: File): Promise<{ doc_id: string }> => {
    const form = new FormData();
    form.append('file', file);
    return request('/documents', { method: 'POST', body: form });
  },

  originalUrl: (id: string) => `${API_URL}/documents/${id}/original`,

  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),

  listSections: (id: string) => request<Section[]>(`/documents/${id}/sections`),

  listSectionChunks: (id: string, sectionId: string) =>
    request<Chunk[]>(`/documents/${id}/sections/${encodeURIComponent(sectionId)}/chunks`),

  listTurns: (id: string) => request<Turn[]>(`/documents/${id}/turns`),

  clearTurns: (id: string) => request<void>(`/documents/${id}/turns`, { method: 'DELETE' }),

  proposeColumns: (docId: string, prompt: string) =>
    request<{ columns: Column[] }>(`/documents/${docId}/tables/propose`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request: prompt }),
    }),

  suggestTables: (docId: string) =>
    request<{ tables: SuggestedTable[] }>(`/documents/${docId}/tables/suggest`, { method: 'POST' }),

  createTable: (docId: string, tableRequest: string, columns: Column[]) =>
    request<TableExtraction>(`/documents/${docId}/tables`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request: tableRequest, columns }),
    }),

  cancelTable: (docId: string, tableId: string) =>
    request<TableExtraction>(`/documents/${docId}/tables/${tableId}/cancel`, { method: 'POST' }),

  listTables: (docId: string) => request<TableExtraction[]>(`/documents/${docId}/tables`),

  getTable: (docId: string, tableId: string) => request<TableExtraction>(`/documents/${docId}/tables/${tableId}`),

  chat: (docId: string, question: string) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_id: docId, question }),
    }),
};

/** Statuses that mean ingest is still running — used to decide whether to keep polling. */
export function isInFlight(status: DocumentStatus): boolean {
  return status !== 'done' && status !== 'error';
}
