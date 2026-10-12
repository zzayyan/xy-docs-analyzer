import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from './lib/api';
import './design-system/styles.css';
import './index.css';
import { LangProvider } from './lib/i18n';
import App from './App.tsx';

// No data-theme attribute set: colors.css's :root already holds the design system's light
// palette (the deck-derived default), so this is the light theme without any override. The
// dark product-console palette lives behind [data-theme="dark"] in the same file if a toggle
// is ever added back.

// Any call answered 401 means the session expired or was ended elsewhere: back to the login screen
function signedOutOn401(error: unknown) {
  if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(['me'], null);
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: signedOutOn401 }),
  mutationCache: new MutationCache({ onError: signedOutOn401 }),
  defaultOptions: {
    queries: {
      // Ingest status and the document list are polled on their own schedule per-query
      // (see lib/api.ts callers); a global refetch-on-focus would fight that.
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <LangProvider>
        <App />
      </LangProvider>
    </QueryClientProvider>
  </StrictMode>,
);
