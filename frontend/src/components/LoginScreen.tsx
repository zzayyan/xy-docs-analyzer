import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Logo } from '../design-system';
import { LanguageSwitch } from './LanguageSwitch';
import { api, ApiError } from '../lib/api';
import { useLang } from '../lib/i18n';

export function LoginScreen() {
  const { t } = useLang();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const login = useMutation({
    mutationFn: () => api.login(username, password),
    onSuccess: (user) => queryClient.setQueryData(['me'], user),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };

  const error = login.error
    ? login.error instanceof ApiError && login.error.status === 401
      ? t.loginWrong
      : t.errorGeneric
    : null;

  return (
    <div style={{ minHeight: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16, background: 'var(--surface-subtle)' }}>
      <form
        onSubmit={submit}
        style={{
          width: '100%',
          maxWidth: 340,
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)',
          padding: 'var(--space-6)',
          background: 'var(--surface-card)',
          border: 'var(--stroke-hairline) solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 'var(--space-2)' }}>
          <Logo variant="mark" height={22} basePath="/design-system/assets/" />
          <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>{t.appName}</span>
          <span style={{ marginLeft: 'auto' }}>
            <LanguageSwitch />
          </span>
        </div>
        <label className="login-label">
          {t.loginUsername}
          <input className="field" autoComplete="username" autoFocus required value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="login-label">
          {t.loginPassword}
          <input className="field" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && (
          <p role="alert" style={{ margin: 0, fontSize: 'var(--fs-ui-xs)', color: 'var(--status-danger)' }}>
            {error}
          </p>
        )}
        <Button type="submit" size="md" fullWidth disabled={login.isPending}>
          {t.loginSubmit}
        </Button>
      </form>
    </div>
  );
}
