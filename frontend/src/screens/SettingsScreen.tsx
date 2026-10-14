import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Button, ProgressBar } from '../design-system';
import { ConfirmDialog } from '../components/ConfirmDialog';
import {
  api,
  ApiError,
  type EmbeddingSettings,
  type EmbeddingSettingsView,
  type ModelSettings,
  type ModelSettingsView,
  type ModelTest,
  type User,
  type UserRow,
} from '../lib/api';
import { formatRelative } from '../lib/format';
import { useLang } from '../lib/i18n';

type Page = 'account' | 'users' | 'models';

export function SettingsScreen({ user, page }: { user: User; page: string | undefined }) {
  const { t } = useLang();
  const pages: Page[] = user.role === 'admin' ? ['account', 'users', 'models'] : ['account'];
  const current: Page = pages.includes(page as Page) ? (page as Page) : 'account';
  const label: Record<Page, string> = { account: t.settingsAccount, users: t.settingsUsers, models: t.settingsModels };

  return (
    <>
      <header className="pane-header">
        <a href="#/" className="quiet-button mobile-only" style={{ textDecoration: 'none' }}>
          ← {t.railDocuments}
        </a>
        <h1 style={{ margin: 0, fontSize: 'var(--fs-ui-md)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>
          {t.settingsTitle}
        </h1>
      </header>
      <div className="settings">
        <nav className="settings-nav">
          {pages.map((p) => (
            <a key={p} href={`#/settings/${p}`} aria-current={p === current ? 'page' : undefined}>
              {label[p]}
            </a>
          ))}
        </nav>
        <div className="settings-page">
          {current === 'account' && <AccountPage user={user} />}
          {current === 'users' && <UsersPage self={user} />}
          {current === 'models' && <ModelsPage />}
        </div>
      </div>
    </>
  );
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

function Avatar({ name }: { name: string }) {
  return <span className="avatar" aria-hidden="true">{name.charAt(0).toUpperCase()}</span>;
}

function RoleBadge({ role }: { role: User['role'] }) {
  const { t } = useLang();
  return <Badge tone={role === 'admin' ? 'outline' : 'neutral'}>{role === 'admin' ? t.roleAdmin : t.roleUser}</Badge>;
}

function PageHead({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="settings-head">
      <div>
        <h2>{title}</h2>
        {hint && <p>{hint}</p>}
      </div>
      {action}
    </div>
  );
}

function AccountPage({ user }: { user: User }) {
  const { t } = useLang();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');

  const change = useMutation({
    mutationFn: () => api.changePassword(current, next),
    onSuccess: () => {
      setCurrent('');
      setNext('');
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    change.mutate();
  };

  return (
    <>
      <PageHead title={t.settingsAccount} />
      <div className="settings-card settings-profile">
        <Avatar name={user.username} />
        <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>{user.username}</span>
        <RoleBadge role={user.role} />
      </div>

      <form onSubmit={submit} className="settings-card">
        <h3>{t.passwordChange}</h3>
        <p className="settings-muted">{t.passwordHint}</p>
        <div className="settings-fields">
          <label className="login-label">
            {t.passwordCurrent}
            <input className="field" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
          </label>
          <label className="login-label">
            {t.passwordNew}
            <input className="field" type="password" autoComplete="new-password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} />
          </label>
        </div>
        <div className="settings-actions">
          {change.isSuccess && <span className="settings-muted">{t.passwordChanged}</span>}
          {change.isError && <span className="settings-error">{errorText(change.error, t.errorGeneric)}</span>}
          <Button type="submit" size="sm" disabled={change.isPending}>
            {t.passwordChange}
          </Button>
        </div>
      </form>
    </>
  );
}

function UsersPage({ self }: { self: User }) {
  const { t } = useLang();
  const queryClient = useQueryClient();
  const usersQuery = useQuery({ queryKey: ['users'], queryFn: api.listUsers });
  const [adding, setAdding] = useState(false);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['users'] });

  return (
    <>
      <PageHead
        title={t.settingsUsers}
        hint={usersQuery.data ? t.usersCount(usersQuery.data.length) : undefined}
        action={
          <Button size="sm" onClick={() => setAdding(true)}>
            + {t.userAdd}
          </Button>
        }
      />
      {usersQuery.isError && <p className="settings-error">{t.errorGeneric}</p>}
      <div className="settings-card" style={{ padding: 0, overflowX: 'auto' }}>
        <table className="settings-table">
          <thead>
            <tr>
              <th>{t.loginUsername}</th>
              <th>{t.userRole}</th>
              <th className="hide-narrow">{t.userCreated}</th>
              <th aria-label={t.userActions} />
            </tr>
          </thead>
          <tbody>
            {usersQuery.isPending &&
              [0, 1].map((i) => (
                <tr key={i}>
                  <td colSpan={4}>
                    <div className="skeleton-block" style={{ height: 14, width: '40%' }} />
                  </td>
                </tr>
              ))}
            {usersQuery.data?.map((u) => <UserRowView key={u.id} user={u} self={u.id === self.id} onChanged={refresh} />)}
          </tbody>
        </table>
      </div>
      <AddUserDialog open={adding} onClose={() => setAdding(false)} onAdded={refresh} />
    </>
  );
}

function UserRowView({ user, self, onChanged }: { user: UserRow; self: boolean; onChanged: () => void }) {
  const { t, lang } = useLang();
  const [resetting, setResetting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const setRole = useMutation({ mutationFn: (role: User['role']) => api.updateUser(user.id, { role }), onSuccess: onChanged });
  const remove = useMutation({ mutationFn: () => api.deleteUser(user.id), onSuccess: onChanged });
  const error = setRole.error ?? remove.error;

  return (
    <tr>
      <td>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <Avatar name={user.username} />
          <span style={{ color: 'var(--text-title)', fontWeight: 'var(--fw-medium)' }}>{user.username}</span>
          {self && <span className="settings-muted">({t.userYou})</span>}
        </span>
        {error && <p className="settings-error">{errorText(error, t.errorGeneric)}</p>}
      </td>
      <td>
        {/* An admin never demotes or deletes their own account: there is always one admin left */}
        {self ? (
          <RoleBadge role={user.role} />
        ) : (
          <select
            className="field"
            aria-label={t.userRole}
            value={user.role}
            disabled={setRole.isPending}
            onChange={(e) => setRole.mutate(e.target.value as User['role'])}
          >
            <option value="user">{t.roleUser}</option>
            <option value="admin">{t.roleAdmin}</option>
          </select>
        )}
      </td>
      <td className="hide-narrow settings-muted">{user.created_at ? formatRelative(user.created_at, lang, t.relativeJustNow) : '—'}</td>
      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
        {!self && (
          <>
            <button className="quiet-button" onClick={() => setResetting(true)}>
              {t.userResetPassword}
            </button>
            <button className="quiet-button" data-tone="danger" onClick={() => setConfirmDelete(true)}>
              {t.deleteAction}
            </button>
            <ResetPasswordDialog user={user} open={resetting} onClose={() => setResetting(false)} />
            <ConfirmDialog
              open={confirmDelete}
              title={t.userDeleteTitle}
              body={t.userDeleteBody(user.username)}
              confirmLabel={t.deleteConfirmConfirm}
              danger
              onConfirm={() => {
                setConfirmDelete(false);
                remove.mutate();
              }}
              onCancel={() => setConfirmDelete(false)}
            />
          </>
        )}
      </td>
    </tr>
  );
}

function FormDialog(props: {
  open: boolean;
  title: string;
  hint?: string;
  submitLabel: string;
  pending: boolean;
  error: unknown;
  onSubmit: () => void;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useLang();
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (props.open && !dialog.open) dialog.showModal();
    if (!props.open && dialog.open) dialog.close();
  }, [props.open]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    props.onSubmit();
  };

  return (
    <dialog ref={ref} className="form-dialog" onClose={props.onClose}>
      <form onSubmit={submit}>
        <h2>{props.title}</h2>
        {props.hint && <p className="settings-muted">{props.hint}</p>}
        {props.children}
        {props.error != null && <p className="settings-error">{errorText(props.error, t.errorGeneric)}</p>}
        <div className="settings-actions">
          <Button variant="ghost" size="sm" onClick={props.onClose}>
            {t.deleteConfirmCancel}
          </Button>
          <Button type="submit" size="sm" disabled={props.pending}>
            {props.submitLabel}
          </Button>
        </div>
      </form>
    </dialog>
  );
}

function AddUserDialog({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded: () => void }) {
  const { t } = useLang();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<User['role']>('user');

  const create = useMutation({ mutationFn: () => api.createUser(username, password, role) });
  const close = () => {
    setUsername('');
    setPassword('');
    setRole('user');
    create.reset();
    onClose();
  };

  return (
    <FormDialog
      open={open}
      title={t.userAdd}
      hint={t.userAddHint}
      submitLabel={t.userAdd}
      pending={create.isPending}
      error={create.error}
      onSubmit={() =>
        create.mutate(undefined, {
          onSuccess: () => {
            onAdded();
            close();
          },
        })
      }
      onClose={close}
    >
      <label className="login-label">
        {t.loginUsername}
        <input className="field" autoComplete="off" required value={username} onChange={(e) => setUsername(e.target.value)} />
      </label>
      <label className="login-label">
        {t.passwordNew}
        <input className="field" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
      <label className="login-label">
        {t.userRole}
        <select className="field" value={role} onChange={(e) => setRole(e.target.value as User['role'])}>
          <option value="user">{t.roleUser}</option>
          <option value="admin">{t.roleAdmin}</option>
        </select>
      </label>
    </FormDialog>
  );
}

function ResetPasswordDialog({ user, open, onClose }: { user: UserRow; open: boolean; onClose: () => void }) {
  const { t } = useLang();
  const [password, setPassword] = useState('');

  const reset = useMutation({ mutationFn: () => api.updateUser(user.id, { password }) });
  const close = () => {
    setPassword('');
    reset.reset();
    onClose();
  };

  return (
    <FormDialog
      open={open}
      title={t.userResetPasswordTitle(user.username)}
      hint={t.userResetPasswordHint}
      submitLabel={t.userResetPassword}
      pending={reset.isPending}
      error={reset.error}
      onSubmit={() => reset.mutate(undefined, { onSuccess: close })}
      onClose={close}
    >
      <label className="login-label">
        {t.passwordNew}
        <input className="field" type="password" autoComplete="new-password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
    </FormDialog>
  );
}

function ModelsPage() {
  const { t } = useLang();
  const settingsQuery = useQuery({ queryKey: ['model-settings'], queryFn: api.modelSettings });

  return (
    <>
      <PageHead
        title={t.settingsModels}
        hint={settingsQuery.data ? (settingsQuery.data.saved ? t.modelsSourceSaved : t.modelsSourceEnv) : undefined}
      />
      {settingsQuery.isError && <p className="settings-error">{t.errorGeneric}</p>}
      {settingsQuery.isPending && <div className="settings-card skeleton-block" style={{ height: 320 }} />}
      {/* Keyed on the loaded values, so a save or reset restarts the form */}
      {settingsQuery.data && <ModelsForm key={JSON.stringify(settingsQuery.data)} loaded={settingsQuery.data} />}
      <EmbeddingCard />
    </>
  );
}

function ModelsForm({ loaded }: { loaded: ModelSettingsView }) {
  const { t } = useLang();
  const queryClient = useQueryClient();
  // Keys start empty: empty means "keep the stored key", which the placeholder shows masked
  const [form, setForm] = useState<ModelSettings>({
    ...loaded,
    llm_api_key: '',
    table_llm_api_key: '',
    llm_reasoning_effort: loaded.llm_reasoning_effort ?? '',
  });
  const [ownTableModel, setOwnTableModel] = useState(loaded.table_llm_model !== '');
  const [confirmReset, setConfirmReset] = useState(false);
  const set = (changes: Partial<ModelSettings>) => setForm((f) => ({ ...f, ...changes }));

  const done = (view: ModelSettingsView) => {
    queryClient.setQueryData(['model-settings'], view);
    queryClient.invalidateQueries({ queryKey: ['models'] });
  };
  const save = useMutation({
    mutationFn: () =>
      api.saveModelSettings({
        ...form,
        llm_api_key: form.llm_api_key || null,
        table_llm_api_key: form.table_llm_api_key || null,
        table_llm_model: ownTableModel ? form.table_llm_model : '',
      }),
    onSuccess: done,
  });
  const reset = useMutation({ mutationFn: api.resetModelSettings, onSuccess: done });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  const openai = form.llm_provider === 'openai';

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div className="settings-card">
        <h3>{t.modelsChat}</h3>
        <p className="settings-muted">{t.modelsChatHint}</p>
        <div className="segmented" role="radiogroup" aria-label={t.modelsProvider} style={{ alignSelf: 'flex-start' }}>
          {(['ollama', 'openai'] as const).map((p) => (
            <button
              key={p}
              type="button"
              role="radio"
              aria-checked={form.llm_provider === p}
              aria-selected={form.llm_provider === p}
              onClick={() => set({ llm_provider: p })}
            >
              {p === 'ollama' ? t.modelsProviderOllama : t.modelsProviderOpenai}
            </button>
          ))}
        </div>
        <div className="settings-fields">
          <label className="login-label">
            {t.modelsBaseUrl}
            <input
              className="field"
              required
              placeholder={openai ? 'https://api.openai.com/v1' : 'http://localhost:11434'}
              value={form.llm_base_url}
              onChange={(e) => set({ llm_base_url: e.target.value })}
            />
          </label>
          <label className="login-label">
            {t.modelsModel}
            <input
              className="field"
              required
              placeholder={openai ? 'gpt-4.1-mini' : 'qwen3:14b'}
              value={form.llm_model}
              onChange={(e) => set({ llm_model: e.target.value })}
            />
          </label>
          {openai && <KeyField value={form.llm_api_key ?? ''} stored={loaded.llm_api_key} onChange={(v) => set({ llm_api_key: v })} />}
          {openai && (
            <label className="login-label">
              {t.modelsReasoning}
              <input
                className="field"
                placeholder="none / low / medium"
                value={form.llm_reasoning_effort ?? ''}
                onChange={(e) => set({ llm_reasoning_effort: e.target.value })}
              />
            </label>
          )}
        </div>
        <label className="login-label">
          {t.modelsChoices}
          <input
            className="field"
            placeholder="model-a, model-b"
            value={form.llm_model_choices}
            onChange={(e) => set({ llm_model_choices: e.target.value })}
          />
          <span className="settings-muted" style={{ fontWeight: 'var(--fw-regular)' }}>
            {t.modelsChoicesHint}
          </span>
        </label>
        <TestButton
          test={{
            slot: 'chat',
            provider: form.llm_provider,
            base_url: form.llm_base_url,
            api_key: form.llm_api_key || null,
            model: form.llm_model,
            reasoning_effort: form.llm_reasoning_effort || null,
          }}
        />
      </div>

      <div className="settings-card">
        <h3>{t.modelsTable}</h3>
        <label className="settings-check">
          <input type="checkbox" checked={ownTableModel} onChange={(e) => setOwnTableModel(e.target.checked)} />
          {t.modelsTableOwn}
        </label>
        <p className="settings-muted">{ownTableModel ? t.modelsTableHint : t.modelsTableOff}</p>
        {ownTableModel && (
          <>
            <div className="settings-fields">
              <label className="login-label">
                {t.modelsBaseUrl}
                <input
                  className="field"
                  required
                  placeholder="https://integrate.api.nvidia.com/v1"
                  value={form.table_llm_base_url}
                  onChange={(e) => set({ table_llm_base_url: e.target.value })}
                />
              </label>
              <label className="login-label">
                {t.modelsModel}
                <input className="field" required value={form.table_llm_model} onChange={(e) => set({ table_llm_model: e.target.value })} />
              </label>
              <KeyField
                value={form.table_llm_api_key ?? ''}
                stored={loaded.table_llm_api_key}
                onChange={(v) => set({ table_llm_api_key: v })}
              />
            </div>
            <TestButton
              test={{
                slot: 'table',
                provider: 'openai',
                base_url: form.table_llm_base_url,
                api_key: form.table_llm_api_key || null,
                model: form.table_llm_model,
                reasoning_effort: null,
              }}
            />
          </>
        )}
      </div>

      <div className="settings-actions">
        {save.isSuccess && <span className="settings-muted">{t.modelsSaved}</span>}
        {(save.isError || reset.isError) && (
          <span className="settings-error" style={{ margin: 0 }}>
            {errorText(save.error ?? reset.error, t.errorGeneric)}
          </span>
        )}
        {loaded.saved && (
          <Button variant="ghost" size="sm" onClick={() => setConfirmReset(true)}>
            {t.modelsReset}
          </Button>
        )}
        <Button type="submit" size="sm" disabled={save.isPending}>
          {t.modelsSave}
        </Button>
      </div>
      <ConfirmDialog
        open={confirmReset}
        title={t.modelsResetTitle}
        body={t.modelsResetBody}
        confirmLabel={t.modelsReset}
        onConfirm={() => {
          setConfirmReset(false);
          reset.mutate();
        }}
        onCancel={() => setConfirmReset(false)}
      />
    </form>
  );
}

function KeyField({ value, stored, onChange }: { value: string; stored: string | null; onChange: (value: string) => void }) {
  const { t } = useLang();
  return (
    <label className="login-label">
      {t.modelsApiKey}
      <input
        className="field"
        type="password"
        autoComplete="off"
        placeholder={stored ? t.modelsKeyKeep(stored) : ''}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function TestButton({ test, onDim }: { test: ModelTest; onDim?: (dim: number) => void }) {
  const { t } = useLang();
  const run = useMutation({ mutationFn: () => api.testModel(test) });
  const result = run.data;

  return (
    <div className="settings-test">
      <Button variant="secondary" size="sm" disabled={run.isPending || !test.base_url || !test.model} onClick={() => run.mutate()}>
        {run.isPending ? t.modelsTesting : t.modelsTest}
      </Button>
      {result?.ok && (
        <span className="settings-test-ok">
          {t.modelsTestOk(result.latency_ms)}
          {result.reply ? ` · "${result.reply}"` : ''}
          {result.dim ? ` · ${t.embedDims(result.dim)}` : ''}
        </span>
      )}
      {result?.dim && onDim && (
        <button type="button" className="quiet-button" onClick={() => onDim(result.dim!)}>
          {t.embedUseDim(result.dim)}
        </button>
      )}
      {result && !result.ok && <span className="settings-error">{result.error}</span>}
      {run.isError && <span className="settings-error">{errorText(run.error, t.errorGeneric)}</span>}
    </div>
  );
}

function EmbeddingCard() {
  const { t } = useLang();
  const embeddingQuery = useQuery({
    queryKey: ['embedding-settings'],
    queryFn: api.embeddingSettings,
    refetchInterval: (query) => (query.state.data?.reindex.status === 'running' ? 1500 : false),
  });
  const data = embeddingQuery.data;
  if (!data) return embeddingQuery.isError ? <p className="settings-error">{t.errorGeneric}</p> : null;
  // Keyed on server values minus progress, so a finished switch restarts the form
  const { reindex, ...loaded } = data;
  return <EmbeddingForm key={JSON.stringify(loaded)} loaded={data} reindex={reindex} />;
}

function EmbeddingForm({ loaded, reindex }: { loaded: EmbeddingSettingsView; reindex: EmbeddingSettingsView['reindex'] }) {
  const { t } = useLang();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<EmbeddingSettings>({ ...loaded, embed_api_key: '' });
  const [confirm, setConfirm] = useState(false);
  const set = (changes: Partial<EmbeddingSettings>) => setForm((f) => ({ ...f, ...changes }));

  const changesModel = form.embed_model.trim() !== loaded.stored_model || form.embed_dim !== loaded.stored_dim;
  const needsReindex = loaded.chunks > 0 && changesModel;
  const running = reindex.status === 'running';

  const save = useMutation({
    mutationFn: (withReindex: boolean) =>
      api.saveEmbeddingSettings({ ...form, embed_api_key: form.embed_api_key || null }, withReindex),
    onSuccess: (view) => queryClient.setQueryData(['embedding-settings'], view),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (needsReindex) setConfirm(true);
    else save.mutate(false);
  };

  return (
    <form onSubmit={submit} className="settings-card">
      <h3>{t.embedTitle}</h3>
      <p className="settings-muted">
        {loaded.chunks > 0 && loaded.stored_model
          ? t.embedStored(loaded.chunks, loaded.stored_model, loaded.stored_dim ?? 0)
          : t.embedEmpty}
      </p>
      <div className="segmented" role="radiogroup" aria-label={t.modelsProvider} style={{ alignSelf: 'flex-start' }}>
        {(['ollama', 'openai'] as const).map((p) => (
          <button
            key={p}
            type="button"
            role="radio"
            aria-checked={form.embed_provider === p}
            aria-selected={form.embed_provider === p}
            disabled={running}
            onClick={() => set({ embed_provider: p })}
          >
            {p === 'ollama' ? t.modelsProviderOllama : t.modelsProviderOpenai}
          </button>
        ))}
      </div>
      <fieldset className="settings-fields" disabled={running} style={{ border: 'none', margin: 0, padding: 0, minWidth: 0 }}>
        <label className="login-label">
          {t.modelsBaseUrl}
          <input className="field" required value={form.embed_base_url} onChange={(e) => set({ embed_base_url: e.target.value })} />
        </label>
        <label className="login-label">
          {t.modelsModel}
          <input className="field" required value={form.embed_model} onChange={(e) => set({ embed_model: e.target.value })} />
        </label>
        <label className="login-label">
          {t.embedDim}
          <input
            className="field"
            type="number"
            min={1}
            required
            value={form.embed_dim}
            onChange={(e) => set({ embed_dim: Number(e.target.value) })}
          />
        </label>
        {form.embed_provider === 'openai' && (
          <KeyField value={form.embed_api_key ?? ''} stored={loaded.embed_api_key} onChange={(v) => set({ embed_api_key: v })} />
        )}
      </fieldset>
      {needsReindex && !running && <p className="settings-warn">{t.embedNeedsReindex(loaded.chunks)}</p>}

      {reindex.status !== 'idle' && (
        <div className="settings-reindex">
          {running && (
            <ProgressBar
              value={reindex.total ? (reindex.done / reindex.total) * 100 : 0}
              label={t.embedProgress(reindex.done, reindex.total)}
            />
          )}
          {reindex.status === 'done' && <span className="settings-test-ok">{t.embedDone}</span>}
          {reindex.status === 'error' && <span className="settings-error">{t.embedFailed(reindex.error ?? '')}</span>}
        </div>
      )}

      <TestButton
        test={{
          slot: 'embedding',
          provider: form.embed_provider,
          base_url: form.embed_base_url,
          api_key: form.embed_api_key || null,
          model: form.embed_model,
          reasoning_effort: null,
        }}
        onDim={(dim) => set({ embed_dim: dim })}
      />
      <div className="settings-actions">
        {save.isSuccess && !needsReindex && !running && <span className="settings-muted">{t.modelsSaved}</span>}
        {save.isError && <span className="settings-error" style={{ margin: 0 }}>{errorText(save.error, t.errorGeneric)}</span>}
        <Button type="submit" size="sm" disabled={save.isPending || running}>
          {needsReindex ? t.embedSaveReindex : t.modelsSave}
        </Button>
      </div>
      <ConfirmDialog
        open={confirm}
        title={t.embedConfirmTitle}
        body={t.embedConfirmBody(loaded.chunks)}
        confirmLabel={t.embedSaveReindex}
        onConfirm={() => {
          setConfirm(false);
          save.mutate(true);
        }}
        onCancel={() => setConfirm(false)}
      />
    </form>
  );
}
