import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DocumentRail } from './components/DocumentRail';
import { EmptyWorkspace } from './components/EmptyWorkspace';
import { LoginScreen } from './components/LoginScreen';
import { Toast } from './components/Toast';
import { DocumentScreen } from './screens/DocumentScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { api, ApiError } from './lib/api';
import { useLang } from './lib/i18n';
import { navigate, useHashRoute } from './lib/useHashRoute';

const RAIL_KEY = 'docs-analyzer:rail-collapsed';

function initialRailCollapsed(): boolean {
  try {
    return localStorage.getItem(RAIL_KEY) === '1';
  } catch {
    return false;
  }
}

// One workspace instead of a list page and a detail page: the rail keeps every document one
// click away while a document is open. Routes are unchanged (#/ and #/doc/{id}).
function App() {
  const { t } = useLang();
  const queryClient = useQueryClient();
  const route = useHashRoute();
  const docId = route.match(/^\/doc\/(.+)$/)?.[1] ?? null;
  const settingsPage = route.match(/^\/settings(?:\/(\w+))?$/);
  const [toast, setToast] = useState<string | null>(null);
  const [railCollapsed, setRailCollapsed] = useState(initialRailCollapsed);
  // null: signed out. Set by LoginScreen on success and by main.tsx on any 401.
  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: () => api.me().catch((e) => (e instanceof ApiError && e.status === 401 ? null : Promise.reject(e))),
    retry: false,
    staleTime: Infinity,
  });

  const toggleRail = () => {
    const next = !railCollapsed;
    setRailCollapsed(next);
    try {
      localStorage.setItem(RAIL_KEY, next ? '1' : '0');
    } catch {
      // best-effort persistence only
    }
  };

  const upload = useMutation({
    mutationFn: api.uploadDocument,
    onSuccess: ({ doc_id }) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      navigate(`/doc/${doc_id}`);
    },
    onError: (error: unknown) => setToast(error instanceof ApiError ? error.detail : t.errorGeneric),
  });

  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      // Nothing cached for one user is shown to the next
      queryClient.clear();
      queryClient.setQueryData(['me'], null);
    },
  });

  if (meQuery.isPending) return null;
  if (!meQuery.data) return <LoginScreen />;

  return (
    <div className="shell" data-doc={docId !== null || settingsPage !== null} data-rail={railCollapsed ? 'collapsed' : 'open'}>
      <DocumentRail
        activeId={docId}
        onUpload={upload.mutate}
        uploading={upload.isPending}
        onToggle={toggleRail}
        user={meQuery.data}
        onLogout={() => logout.mutate()}
      />
      <main className="workspace">
        {settingsPage ? (
          <SettingsScreen user={meQuery.data} page={settingsPage[1]} />
        ) : docId ? (
          <DocumentScreen key={docId} docId={docId} />
        ) : (
          <EmptyWorkspace onUpload={upload.mutate} uploading={upload.isPending} />
        )}
      </main>
      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}

export default App;
