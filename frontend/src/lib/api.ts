// Types are hand-written to mirror backend/app/api.py's Pydantic models; codegen from /openapi.json if they drift.

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

/** Keys come back masked; sending null keeps the stored key. */
export interface ModelSettings {
  llm_provider: 'ollama' | 'openai';
  llm_base_url: string;
  llm_api_key: string | null;
  llm_model: string;
  llm_model_choices: string;
  llm_reasoning_effort: string | null;
}

export interface ModelSettingsView extends ModelSettings {
  saved: boolean;
}

export interface EmbeddingSettings {
  embed_provider: 'ollama' | 'openai';
  embed_base_url: string;
  embed_api_key: string | null;
  embed_model: string;
  embed_dim: number;
}

export interface Reindex {
  status: 'idle' | 'running' | 'done' | 'error';
  done: number;
  total: number;
  error: string | null;
}

export interface EmbeddingSettingsView extends EmbeddingSettings {
  saved: boolean;
  chunks: number;
  stored_model: string | null;
  stored_dim: number | null;
  reindex: Reindex;
}

export interface ModelTest {
  slot: 'chat' | 'embedding';
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
  dim: number | null;
  error: string | null;
}

export interface Limits {
  max_upload_mb: number;
  max_pages: number;
  /** Accepted extensions, e.g. ".pdf" */
  formats: string[];
}

// .htm and .jpeg are spellings of formats already listed
const FORMAT_NAMES: Record<string, string> = { '.htm': 'HTML', '.jpeg': 'JPG', '.md': 'Markdown' };

export function formatNames(formats: string[]): string {
  return [...new Set(formats.map((f) => FORMAT_NAMES[f] ?? f.slice(1).toUpperCase()))].join(', ');
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
  language: string | null;
  /** Pages without a text layer of their own, read by OCR */
  ocr_pages: number | null;
  /** The Short/Long cutoff in force when this Document was converted */
  long_doc_tokens: number | null;
  sections: number | null;
  entities: number | null;
  graph_skipped: number | null;
  /** Only getDocument sends it */
  page_count?: number | null;
  /** When each stage began, in order; empty for Documents ingested before it was recorded */
  timeline: { stage: DocumentStatus; started_at: number }[];
}

/** A Highlight box: top-left origin, PDF points, with its page's size for scaling. */
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
  source: 'vector' | 'tree' | 'kg' | 'kg_facts';
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
  const res = await fetch(`${API_URL}${path}`, { ...init, credentials: 'include' });
  if (!res.ok) {
    // {"detail": ...} from FastAPI, else the raw text (a proxy error page, say)
    const body = await res.text();
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
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

  embeddingSettings: () => request<EmbeddingSettingsView>('/settings/embedding'),

  saveEmbeddingSettings: (values: EmbeddingSettings, reindex: boolean) =>
    request<EmbeddingSettingsView>('/settings/embedding', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...values, reindex }),
    }),

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

  graph: (docId: string) => request<GraphData>(`/documents/${docId}/graph`),

  // A query parameter, not a path segment: entity names contain "/"
  entity: (docId: string, key: string) =>
    request<EntityDetail>(`/documents/${docId}/graph/entity?key=${encodeURIComponent(key)}`),
};

export function isInFlight(status: DocumentStatus): boolean {
  return status !== 'done' && status !== 'error';
}
