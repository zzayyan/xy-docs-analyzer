import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError } from './lib/api';
import './design-system/styles.css';
import './index.css';
import { LangProvider } from './lib/i18n';
import App from './App.tsx';


function signedOutOn401(error: unknown) {
  if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(['me'], null);
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: signedOutOn401 }),
  mutationCache: new MutationCache({ onError: signedOutOn401 }),
  defaultOptions: {
    queries: {
      // Polling is set per query; refetch-on-focus would fight it
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
