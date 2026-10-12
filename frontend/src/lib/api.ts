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

export interface User {
  id: string;
  username: string;
  role: 'admin' | 'user';
}

export interface UserRow extends User {
  created_at: number | null;
}

/** Keys come back masked ("••••a1b2"); sending null keeps the stored key. */
export interface ModelSettings {
  llm_provider: 'ollama' | 'openai';
  llm_base_url: string;
  llm_api_key: string | null;
  llm_model: string;
  llm_model_choices: string;
  llm_reasoning_effort: string | null;
  table_llm_base_url: string;
  table_llm_api_key: string | null;
  table_llm_model: string;
}

export interface ModelSettingsView extends ModelSettings {
  saved: boolean;
}

export interface ModelTest {
  slot: 'chat' | 'table';
  provider: 'ollama' | 'openai';
  base_url: string;
  api_key: string | null;
  model: string;
  reasoning_effort: string | null;
}

export interface ModelTestResult {
  ok: boolean;
  latency_ms: number;
  reply: string | null;
  error: string | null;
}

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
  /** Pages in a PDF Original; only getDocument sends it */
  page_count?: number | null;
}

/** One bounding box on one page of the Original -- what gets drawn as a Highlight. Top-left origin,
 * PDF points; page_width/page_height are the page's own size, so no separate lookup is needed to scale. */
export interface Region {
  page: number;
  l: number;
  t: number;
  r: number;
  b: number;
  page_width: number;
  page_height: number;
}

export interface Citation {
  n: number;
  chunk_id: string;
  pages: number[];
  headings: string[];
  source: 'vector' | 'tree' | 'kg' | 'kg_facts' | 'table';
  text: string;
  regions: Region[];
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
  id: string;
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
  /** Headings of the parts the run read, out of document_chunks: fewer when it was scoped (docs/adr/0004) */
  read_parts: string[] | null;
  document_chunks: number | null;
  read_all: boolean;
  created_at: number;
  updated_at: number;
}

export interface GraphNode {
  key: string;
  name: string;
  type: string | null;
  mentions: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total: number;
}

export interface EntityDetail {
  entity: GraphNode;
  nodes: GraphNode[];
  edges: GraphEdge[];
  citations: Citation[];
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
  // The session is an HttpOnly cookie on the API's origin, so every call has to send it
  const res = await fetch(`${API_URL}${path}`, { ...init, credentials: 'include' });
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
  login: (username: string, password: string) =>
    request<User>('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),

  logout: () => request<void>('/auth/logout', { method: 'POST' }),

  me: () => request<User>('/auth/me'),

  changePassword: (current: string, next: string) =>
    request<void>('/auth/password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current, new: next }),
    }),

  listUsers: () => request<UserRow[]>('/users'),

  createUser: (username: string, password: string, role: User['role']) =>
    request<User>('/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, role }),
    }),

  updateUser: (id: string, changes: { password?: string; role?: User['role'] }) =>
    request<void>(`/users/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    }),

  deleteUser: (id: string) => request<void>(`/users/${id}`, { method: 'DELETE' }),

  modelSettings: () => request<ModelSettingsView>('/settings/models'),

  saveModelSettings: (values: ModelSettings) =>
    request<ModelSettingsView>('/settings/models', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    }),

  resetModelSettings: () => request<ModelSettingsView>('/settings/models', { method: 'DELETE' }),

  testModel: (test: ModelTest) =>
    request<ModelTestResult>('/settings/models/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(test),
    }),

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

  pageImageUrl: (id: string, page: number) => `${API_URL}/documents/${id}/original/pages/${page}`,

  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),

  retryDocument: (id: string) => request<Document>(`/documents/${id}/retry`, { method: 'POST' }),

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

  createTable: (docId: string, tableRequest: string, columns: Column[], readAll = false) =>
    request<TableExtraction>(`/documents/${docId}/tables`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request: tableRequest, columns, read_all: readAll }),
    }),

  cancelTable: (docId: string, tableId: string) =>
    request<TableExtraction>(`/documents/${docId}/tables/${tableId}/cancel`, { method: 'POST' }),

  deleteTable: (docId: string, tableId: string) =>
    request<void>(`/documents/${docId}/tables/${tableId}`, { method: 'DELETE' }),

  deleteTableRow: (docId: string, tableId: string, rowId: string) =>
    request<void>(`/documents/${docId}/tables/${tableId}/rows/${encodeURIComponent(rowId)}`, { method: 'DELETE' }),

  tableExportUrl: (docId: string, tableId: string) => `${API_URL}/documents/${docId}/tables/${tableId}/export.xlsx`,

  listTables: (docId: string) => request<TableExtraction[]>(`/documents/${docId}/tables`),

  getTable: (docId: string, tableId: string) => request<TableExtraction>(`/documents/${docId}/tables/${tableId}`),

  graph: (docId: string) => request<GraphData>(`/documents/${docId}/graph`),

  // A query parameter, not a path segment: entity names contain "/"
  entity: (docId: string, key: string) =>
    request<EntityDetail>(`/documents/${docId}/graph/entity?key=${encodeURIComponent(key)}`),
};

/** Statuses that mean ingest is still running — used to decide whether to keep polling. */
export function isInFlight(status: DocumentStatus): boolean {
  return status !== 'done' && status !== 'error';
}
