import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Button, DataTable, ProgressBar } from '../design-system';
import { ConfirmDialog } from './ConfirmDialog';
import { ErrorDetail } from './ErrorDetail';
import { SourcePanel } from './SourcePanel';
import { Toast } from './Toast';
import { api, ApiError, type Citation, type Column, type SuggestedTable, type TableExtraction } from '../lib/api';
import { estimateRemaining, formatDuration, formatRelative } from '../lib/format';
import { useLang, type Lang } from '../lib/i18n';

const STATUS_KEY = {
  queued: 'tableStatusQueued',
  running: 'tableStatusRunning',
  done: 'tableStatusDone',
  error: 'tableStatusError',
  cancelled: 'tableStatusCancelled',
} as const;

function isRunning(extraction: TableExtraction): boolean {
  return extraction.status === 'queued' || extraction.status === 'running';
}

/** Table Extraction for one document: describe the table, edit the proposed columns, run it over
 * every chunk, then read the rows with their citations. Earlier extractions stay openable. */
export function TablePanel({ docId }: { docId: string }) {
  const { t, lang } = useLang();
  const queryClient = useQueryClient();
  const [request, setRequest] = useState('');
  const [columns, setColumns] = useState<Column[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ key: string; citation: Citation } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const listQuery = useQuery({ queryKey: ['tables', docId], queryFn: () => api.listTables(docId) });
  // A run outlives this tab, so the open extraction is polled from the server rather than kept in
  // component state; the interval stops as soon as it reaches a terminal status.
  const openQuery = useQuery({
    queryKey: ['table', docId, openId],
    queryFn: () => api.getTable(docId, openId as string),
    enabled: openId !== null,
    refetchInterval: (query) => (query.state.data && isRunning(query.state.data) ? 1500 : false),
  });

  const fail = (error: unknown) => setToast(error instanceof ApiError ? error.detail : t.errorGeneric);

  const suggestMutation = useMutation({
    mutationFn: () => api.suggestTables(docId),
    onError: fail,
  });

  const proposeMutation = useMutation({
    mutationFn: () => api.proposeColumns(docId, request.trim()),
    onSuccess: ({ columns: proposed }) => setColumns(proposed),
    onError: fail,
  });

  const runMutation = useMutation({
    mutationFn: (ready: Column[]) => api.createTable(docId, request.trim(), ready),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['tables', docId] });
      setOpenId(created.id);
      setColumns(null);
    },
    onError: fail,
  });

  // The same table again over every chunk, for a scoped run that read too little (docs/adr/0004)
  const readAllMutation = useMutation({
    mutationFn: (extraction: TableExtraction) => api.createTable(docId, extraction.request, extraction.columns, true),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['tables', docId] });
      setOpenId(created.id);
      setSelected(null);
    },
    onError: fail,
  });

  const cancelMutation = useMutation({
    mutationFn: (tableId: string) => api.cancelTable(docId, tableId),
    onSuccess: (cancelled) => queryClient.setQueryData(['table', docId, cancelled.id], cancelled),
    onError: fail,
  });

  const deleteMutation = useMutation({
    mutationFn: (tableId: string) => api.deleteTable(docId, tableId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tables', docId] });
      setConfirmDelete(false);
      reset();
    },
    onError: (error: unknown) => {
      setConfirmDelete(false);
      fail(error);
    },
  });

  const deleteRowMutation = useMutation({
    mutationFn: ({ tableId, rowId }: { tableId: string; rowId: string }) => api.deleteTableRow(docId, tableId, rowId),
    // Refetch rather than patch the cache: the server's list is the one that persists
    onSuccess: (_, { tableId }) => queryClient.invalidateQueries({ queryKey: ['table', docId, tableId] }),
    onError: fail,
  });

  const open = openId !== null ? openQuery.data ?? null : null;
  // The history list carries each run's status and is fetched once, so when the polled run reaches a
  // terminal status, refresh the list that still shows it as running.
  const openStatus = open?.status ?? null;
  useEffect(() => {
    if (openStatus === 'done' || openStatus === 'error' || openStatus === 'cancelled') {
      queryClient.invalidateQueries({ queryKey: ['tables', docId] });
    }
  }, [openStatus, docId, queryClient]);
  const editing = columns !== null;

  const reset = () => {
    setColumns(null);
    setOpenId(null);
    setSelected(null);
  };

  const startOver = (extraction: TableExtraction) => {
    setRequest(extraction.request);
    setColumns(extraction.columns);
    setOpenId(null);
    setSelected(null);
  };

  const select = (key: string, citation: Citation) =>
    setSelected((current) => (current?.key === key ? null : { key, citation }));

  return (
    <div className="chat-layout" data-sources={selected !== null}>
      <div style={{ minHeight: 0, overflowY: 'auto' }}>
        <div className="chat-column" style={{ display: 'flex', flexDirection: 'column', gap: 20, padding: '24px 24px 32px' }}>
          {open ? (
            <ExtractionView
              extraction={open}
              selectedKey={selected?.key ?? null}
              onSelect={select}
              onStartOver={() => startOver(open)}
              onNew={reset}
              onCancel={() => cancelMutation.mutate(open.id)}
              cancelling={cancelMutation.isPending}
              onDelete={() => setConfirmDelete(true)}
              onDeleteRow={(rowId) => deleteRowMutation.mutate({ tableId: open.id, rowId })}
              onReadAll={() => readAllMutation.mutate(open)}
              readingAll={readAllMutation.isPending}
              exportUrl={api.tableExportUrl(docId, open.id)}
            />
          ) : (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <p style={{ margin: 0, color: 'var(--text-muted)' }}>{t.tableIntro}</p>
                <div className="composer">
                  <textarea
                    rows={1}
                    value={request}
                    placeholder={t.tablePlaceholder}
                    onChange={(e) => setRequest(e.target.value)}
                  />
                  <Button
                    size="sm"
                    onClick={() => proposeMutation.mutate()}
                    disabled={!request.trim() || proposeMutation.isPending}
                  >
                    {proposeMutation.isPending ? t.tableProposing : t.tableProposeAction}
                  </Button>
                </div>
              </div>

              {!editing && !suggestMutation.data && (
                <div>
                  <button
                    className="quiet-button"
                    onClick={() => suggestMutation.mutate()}
                    disabled={suggestMutation.isPending}
                  >
                    {suggestMutation.isPending ? t.tableSuggesting : t.tableSuggestAction}
                  </button>
                </div>
              )}

              {!editing && suggestMutation.data?.tables.length === 0 && (
                <p style={{ margin: 0, color: 'var(--text-muted)' }}>{t.tableSuggestionsEmpty}</p>
              )}

              {!editing && suggestMutation.data && suggestMutation.data.tables.length > 0 && (
                <Suggestions
                  tables={suggestMutation.data.tables}
                  onPick={(suggestion) => {
                    setRequest(suggestion.request);
                    setColumns(suggestion.columns);
                    suggestMutation.reset();
                  }}
                />
              )}

              {editing && (
                <ColumnEditor
                  columns={columns}
                  onChange={setColumns}
                  onRun={() => runMutation.mutate(columns.filter((c) => c.name.trim()))}
                  running={runMutation.isPending}
                />
              )}
            </>
          )}

          <History
            extractions={listQuery.data ?? []}
            openId={openId}
            lang={lang}
            onOpen={(id) => {
              setColumns(null);
              setSelected(null);
              setOpenId(id);
            }}
          />
        </div>
      </div>

      {selected && <SourcePanel docId={docId} citation={selected.citation} onClose={() => setSelected(null)} />}

      <ConfirmDialog
        open={confirmDelete}
        title={t.tableDeleteConfirmTitle}
        body={open ? t.tableDeleteConfirmBody(open.request) : ''}
        danger
        onConfirm={() => open && deleteMutation.mutate(open.id)}
        onCancel={() => setConfirmDelete(false)}
      />

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}

function Suggestions({ tables, onPick }: { tables: SuggestedTable[]; onPick: (table: SuggestedTable) => void }) {
  const { t } = useLang();
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <h3 style={{ margin: 0, fontSize: 'var(--fs-ui-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-muted)' }}>
        {t.tableSuggestionsTitle}
      </h3>
      {tables.map((table, index) => (
        <button
          key={index}
          className="suggestion"
          style={{ display: 'flex', flexDirection: 'column', gap: 4 }}
          onClick={() => onPick(table)}
        >
          <span style={{ fontWeight: 'var(--fw-medium)', color: 'var(--text-title)' }}>{table.title}</span>
          <span style={{ color: 'var(--text-muted)' }}>{table.columns.map((c) => c.name).join(' · ')}</span>
        </button>
      ))}
    </section>
  );
}

interface ColumnEditorProps {
  columns: Column[];
  onChange: (columns: Column[]) => void;
  onRun: () => void;
  running: boolean;
}

function ColumnEditor({ columns, onChange, onRun, running }: ColumnEditorProps) {
  const { t } = useLang();
  const update = (index: number, patch: Partial<Column>) =>
    onChange(columns.map((c, i) => (i === index ? { ...c, ...patch } : c)));

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <h3 style={{ margin: 0, fontSize: 'var(--fs-ui-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>
        {t.tableColumnsTitle}
      </h3>

      {columns.map((column, index) => (
        <div key={index} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            className="field"
            style={{ flex: '0 0 200px' }}
            value={column.name}
            aria-label={t.tableColumnName}
            placeholder={t.tableColumnName}
            onChange={(e) => update(index, { name: e.target.value })}
          />
          <input
            className="field"
            style={{ flex: 1, minWidth: 0 }}
            value={column.description}
            aria-label={t.tableColumnDescription}
            placeholder={t.tableColumnDescription}
            onChange={(e) => update(index, { description: e.target.value })}
          />
          <button className="quiet-button" onClick={() => onChange(columns.filter((_, i) => i !== index))}>
            {t.tableColumnRemove}
          </button>
        </div>
      ))}

      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <button className="quiet-button" onClick={() => onChange([...columns, { name: '', description: '' }])}>
          {t.tableColumnAdd}
        </button>
        <Button size="sm" onClick={onRun} disabled={running || columns.every((c) => !c.name.trim())}>
          {t.tableRunAction}
        </Button>
      </div>
    </section>
  );
}

/** How far a run has got: the chunk count it reads, plus elapsed and estimated remaining time, the
 * same shape ingest shows — a run is minutes long, so a bare percentage says too little. */
function RunProgress({
  extraction,
  onCancel,
  cancelling,
}: {
  extraction: TableExtraction;
  onCancel: () => void;
  cancelling: boolean;
}) {
  const { t } = useLang();
  const elapsedMs = Date.now() - extraction.created_at;
  const remainingMs = estimateRemaining(elapsedMs, extraction.progress);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <span style={{ color: 'var(--text-title)' }}>{t.tableRunningTitle}</span>
        <button className="quiet-button" data-tone="danger" onClick={onCancel} disabled={cancelling}>
          {t.tableCancelAction}
        </button>
      </div>
      <ProgressBar value={extraction.progress * 100} />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-4)', fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
        {extraction.chunks_total !== null && (
          <span>
            {t.docStepCount(extraction.chunks_done ?? 0, extraction.chunks_total)} {t.unitChunks}
          </span>
        )}
        <span>
          {t.docElapsedLabel}: {formatDuration(elapsedMs)}
        </span>
        {remainingMs !== undefined && <span>{t.docEtaLabel(formatDuration(remainingMs))}</span>}
      </div>
      <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>{t.tableRunningHint}</span>
    </div>
  );
}

interface ExtractionViewProps {
  extraction: TableExtraction;
  selectedKey: string | null;
  onSelect: (key: string, citation: Citation) => void;
  onStartOver: () => void;
  onNew: () => void;
  onCancel: () => void;
  cancelling: boolean;
  onDelete: () => void;
  onDeleteRow: (rowId: string) => void;
  onReadAll: () => void;
  readingAll: boolean;
  exportUrl: string;
}

function ExtractionView({
  extraction,
  selectedKey,
  onSelect,
  onStartOver,
  onNew,
  onCancel,
  cancelling,
  onDelete,
  onDeleteRow,
  onReadAll,
  readingAll,
  exportUrl,
}: ExtractionViewProps) {
  const { t } = useLang();
  const names = extraction.columns.map((c) => c.name);
  const parts = extraction.read_parts ?? [];
  const scoped =
    extraction.status === 'done' &&
    !extraction.read_all &&
    extraction.document_chunks !== null &&
    extraction.chunks_total !== null &&
    extraction.chunks_total < extraction.document_chunks;

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <h3 style={{ margin: 0, fontSize: 'var(--fs-ui-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>
          {extraction.request}
        </h3>
        <div style={{ display: 'flex', flex: '0 0 auto', alignItems: 'center', gap: 4 }}>
          {extraction.status === 'done' && extraction.rows.length > 0 && (
            <a className="quiet-button" style={{ textDecoration: 'none' }} href={exportUrl} download>
              {t.tableExportAction}
            </a>
          )}
          <button className="quiet-button" data-tone="danger" onClick={onDelete}>
            {t.tableDeleteAction}
          </button>
          <button className="quiet-button" onClick={onNew}>
            {t.tableNewAction}
          </button>
        </div>
      </div>

      {isRunning(extraction) && <RunProgress extraction={extraction} onCancel={onCancel} cancelling={cancelling} />}

      {extraction.status === 'cancelled' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', alignItems: 'flex-start' }}>
          <p style={{ margin: 0, color: 'var(--text-muted)' }}>{t.tableCancelledNotice}</p>
          <button className="quiet-button" onClick={onStartOver}>
            {t.tableRetry}
          </button>
        </div>
      )}

      {extraction.status === 'error' && (
        <Alert tone="danger" title={t.tableErrorTitle}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', alignItems: 'flex-start' }}>
            {extraction.error && <ErrorDetail message={extraction.error} limit={160} />}
            <button className="quiet-button" onClick={onStartOver}>
              {t.tableRetry}
            </button>
          </div>
        </Alert>
      )}

      {scoped && (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            gap: 6,
            padding: '10px 12px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface-subtle)',
            fontSize: 'var(--fs-ui-xs)',
            color: 'var(--text-muted)',
          }}
        >
          <span>{t.tableReadScope(parts.length, extraction.chunks_total ?? 0, extraction.document_chunks ?? 0)}</span>
          <span style={{ color: 'var(--text-title)' }}>{parts.join(' · ')}</span>
          <button className="quiet-button" onClick={onReadAll} disabled={readingAll}>
            {t.tableReadAll}
          </button>
        </div>
      )}

      {extraction.status === 'done' &&
        (extraction.rows.length === 0 ? (
          <p style={{ margin: 0, color: 'var(--text-muted)' }}>{t.tableNothingFound}</p>
        ) : (
          <>
            <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
              {t.tableRowCount(extraction.rows.length)}
            </span>
            <DataTable
              columns={[
                ...names.map((name, index) => ({ key: `c${index}`, label: name })),
                { key: 'sources', label: t.tableCitationsLabel },
              ]}
              rows={extraction.rows.map((row, rowIndex) => ({
                // Keyed by position, not by column name: a column the user named "sources" would
                // otherwise collide with the citations column.
                ...Object.fromEntries(names.map((name, index) => [`c${index}`, row.values[name] ?? ''])),
                sources: (
                  <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
                    {row.citations.map((citation) => {
                      const key = `${extraction.id}:${rowIndex}:${citation.chunk_id}`;
                      return (
                        <button
                          key={key}
                          className="chip"
                          aria-pressed={selectedKey === key}
                          onClick={() => onSelect(key, citation)}
                        >
                          <span style={{ color: 'var(--brand-primary)', fontWeight: 'var(--fw-semibold)' }}>
                            {citation.pages.length > 0 ? `p. ${citation.pages[0]}` : citation.n}
                          </span>
                        </button>
                      );
                    })}
                    <button
                      className="quiet-button"
                      data-tone="danger"
                      aria-label={t.tableRowDelete}
                      title={t.tableRowDelete}
                      onClick={() => onDeleteRow(row.id)}
                    >
                      ×
                    </button>
                  </div>
                ),
              }))}
            />
          </>
        ))}
    </section>
  );
}

interface HistoryProps {
  extractions: TableExtraction[];
  openId: string | null;
  lang: Lang;
  onOpen: (id: string) => void;
}

function History({ extractions, openId, lang, onOpen }: HistoryProps) {
  const { t } = useLang();
  if (extractions.length === 0) return null;

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 8, borderTop: 'var(--stroke-hairline) solid var(--border-subtle)' }}>
      <h3 style={{ margin: 0, fontSize: 'var(--fs-ui-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-muted)' }}>
        {t.tableHistoryTitle}
      </h3>
      {extractions.map((extraction) => (
        <button
          key={extraction.id}
          className="chip"
          aria-pressed={openId === extraction.id}
          style={{ maxWidth: '100%', justifyContent: 'space-between' }}
          onClick={() => onOpen(extraction.id)}
        >
          <span className="truncate">{extraction.request}</span>
          <span style={{ flex: '0 0 auto', color: 'var(--text-muted)' }}>
            {t[STATUS_KEY[extraction.status]]} · {formatRelative(extraction.created_at, lang, t.relativeJustNow)}
          </span>
        </button>
      ))}
    </section>
  );
}
