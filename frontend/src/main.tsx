import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import './design-system/styles.css';
import './index.css';
import { LangProvider } from './lib/i18n';
import App from './App.tsx';

// data-theme is set once, statically: the design system's product surfaces (the XYLM
// console this app's shell is modelled on) are dark-only, there is no light/dark toggle.
document.documentElement.dataset.theme = 'dark';

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
