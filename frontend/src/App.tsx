import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { DocumentRail } from './components/DocumentRail';
import { EmptyWorkspace } from './components/EmptyWorkspace';
import { Toast } from './components/Toast';
import { DocumentScreen } from './screens/DocumentScreen';
import { api, ApiError } from './lib/api';
import { useLang } from './lib/i18n';
import { navigate, useHashRoute } from './lib/useHashRoute';

// One workspace instead of a list page and a detail page: the rail keeps every document one
// click away while a document is open. Routes are unchanged (#/ and #/doc/{id}).
function App() {
  const { t } = useLang();
  const queryClient = useQueryClient();
  const route = useHashRoute();
  const docId = route.match(/^\/doc\/(.+)$/)?.[1] ?? null;
  const [toast, setToast] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: api.uploadDocument,
    onSuccess: ({ doc_id }) => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      navigate(`/doc/${doc_id}`);
    },
    onError: (error: unknown) => setToast(error instanceof ApiError ? error.detail : t.errorGeneric),
  });

  return (
    <div className="shell" data-doc={docId !== null}>
      <DocumentRail activeId={docId} onUpload={upload.mutate} uploading={upload.isPending} />
      <main className="workspace">
        {docId ? (
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
