import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './design-system/styles.css';
import './index.css';
import { LangProvider } from './lib/i18n';
import App from './App.tsx';

// No data-theme attribute set: colors.css's :root already holds the design system's light
// palette (the deck-derived default), so this is the light theme without any override. The
// dark product-console palette lives behind [data-theme="dark"] in the same file if a toggle
// is ever added back.

const queryClient = new QueryClient({
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
