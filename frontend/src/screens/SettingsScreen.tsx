import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Button } from '../design-system';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { api, ApiError, type User, type UserRow } from '../lib/api';
import { formatRelative } from '../lib/format';
import { useLang } from '../lib/i18n';

type Page = 'account' | 'users';

/** #/settings/{page}: a sub-nav on the left, one page on the right. Users is for admins only. */
export function SettingsScreen({ user, page }: { user: User; page: string | undefined }) {
  const { t } = useLang();
  const pages: Page[] = user.role === 'admin' ? ['account', 'users'] : ['account'];
  const current: Page = pages.includes(page as Page) ? (page as Page) : 'account';
  const label: Record<Page, string> = { account: t.settingsAccount, users: t.settingsUsers };

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
          {current === 'account' ? <AccountPage user={user} /> : <UsersPage self={user} />}
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

/** A native <dialog> holding a form, styled like ConfirmDialog. */
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
