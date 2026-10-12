import { useState, type FormEvent, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '../design-system';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { api, ApiError, type User, type UserRow } from '../lib/api';
import { useLang } from '../lib/i18n';

/** Everyone gets their own account here; admins also manage the other users. */
export function SettingsScreen({ user }: { user: User }) {
  const { t } = useLang();

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
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        <div className="settings">
          <AccountSection user={user} />
          {user.role === 'admin' && <UsersSection self={user} />}
        </div>
      </div>
    </>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="settings-section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

function AccountSection({ user }: { user: User }) {
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
    <Section title={t.settingsAccount}>
      <p className="settings-muted">
        {user.username} · {user.role === 'admin' ? t.roleAdmin : t.roleUser}
      </p>
      <form onSubmit={submit} className="settings-form">
        <label className="login-label">
          {t.passwordCurrent}
          <input className="field" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label className="login-label">
          {t.passwordNew}
          <input className="field" type="password" autoComplete="new-password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} />
        </label>
        <div className="settings-actions">
          <Button type="submit" size="sm" disabled={change.isPending}>
            {t.passwordChange}
          </Button>
          {change.isSuccess && <span className="settings-muted">{t.passwordChanged}</span>}
          {change.isError && <span className="settings-error">{errorText(change.error, t.errorGeneric)}</span>}
        </div>
      </form>
    </Section>
  );
}

function UsersSection({ self }: { self: User }) {
  const { t } = useLang();
  const queryClient = useQueryClient();
  const usersQuery = useQuery({ queryKey: ['users'], queryFn: api.listUsers });
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<User['role']>('user');
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['users'] });

  const create = useMutation({
    mutationFn: () => api.createUser(username, password, role),
    onSuccess: () => {
      setUsername('');
      setPassword('');
      setRole('user');
      refresh();
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };

  return (
    <Section title={t.settingsUsers}>
      {usersQuery.isError && <p className="settings-error">{t.errorGeneric}</p>}
      <ul className="settings-list">
        {usersQuery.data?.map((u) => <UserItem key={u.id} user={u} self={u.id === self.id} onChanged={refresh} />)}
      </ul>
      <form onSubmit={submit} className="settings-form settings-inline">
        <input
          className="field"
          aria-label={t.loginUsername}
          placeholder={t.loginUsername}
          autoComplete="off"
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          className="field"
          type="password"
          aria-label={t.loginPassword}
          placeholder={t.loginPassword}
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <RoleSelect value={role} onChange={setRole} />
        <Button type="submit" size="sm" disabled={create.isPending}>
          {t.userAdd}
        </Button>
      </form>
      {create.isError && <p className="settings-error">{errorText(create.error, t.errorGeneric)}</p>}
    </Section>
  );
}

function RoleSelect({ value, onChange, disabled }: { value: User['role']; onChange: (role: User['role']) => void; disabled?: boolean }) {
  const { t } = useLang();
  return (
    <select className="field" aria-label={t.userRole} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value as User['role'])}>
      <option value="user">{t.roleUser}</option>
      <option value="admin">{t.roleAdmin}</option>
    </select>
  );
}

function UserItem({ user, self, onChanged }: { user: UserRow; self: boolean; onChanged: () => void }) {
  const { t } = useLang();
  const [resetting, setResetting] = useState(false);
  const [password, setPassword] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(false);

  const update = useMutation({
    mutationFn: (changes: { password?: string; role?: User['role'] }) => api.updateUser(user.id, changes),
    onSuccess: () => {
      setResetting(false);
      setPassword('');
      onChanged();
    },
  });
  const remove = useMutation({ mutationFn: () => api.deleteUser(user.id), onSuccess: onChanged });
  const error = update.error ?? remove.error;

  const submitReset = (e: FormEvent) => {
    e.preventDefault();
    update.mutate({ password });
  };

  return (
    <li>
      <div className="settings-row">
        <span className="truncate" style={{ flex: 1, minWidth: 0, color: 'var(--text-title)' }}>
          {user.username}
          {self && <span className="settings-muted"> · {t.userYou}</span>}
        </span>
        {/* An admin never demotes or deletes their own account: there is always one admin left */}
        <RoleSelect value={user.role} disabled={self || update.isPending} onChange={(role) => update.mutate({ role })} />
        {!self && (
          <>
            <button className="quiet-button" onClick={() => setResetting(!resetting)}>
              {t.userResetPassword}
            </button>
            <button className="quiet-button" data-tone="danger" onClick={() => setConfirmDelete(true)}>
              {t.deleteAction}
            </button>
          </>
        )}
      </div>
      {resetting && (
        <form onSubmit={submitReset} className="settings-inline" style={{ marginTop: 8 }}>
          <input
            className="field"
            type="password"
            aria-label={t.passwordNew}
            placeholder={t.passwordNew}
            autoComplete="new-password"
            autoFocus
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button type="submit" size="sm" disabled={update.isPending}>
            {t.passwordChange}
          </Button>
        </form>
      )}
      {error && <p className="settings-error">{errorText(error, t.errorGeneric)}</p>}
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
    </li>
  );
}
