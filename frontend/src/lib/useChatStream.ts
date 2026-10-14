import { useCallback, useEffect, useRef, useState } from 'react';
import type { Citation } from './api';
import { useLang } from './i18n';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

export interface StreamState {
  status: 'idle' | 'streaming';
  answer: string;
  citations: Citation[];
  statusNode: string | null;
}

const IDLE: StreamState = { status: 'idle', answer: '', citations: [], statusNode: null };

export interface ChatStreamCallbacks {
  onDone?: () => void;
  /** Backend "failed" event or a connection drop; either way a partial Turn was saved. */
  onError?: (message: string) => void;
}

/** GET /chat/stream via EventSource. Every terminal path must close() it: EventSource auto-reconnects,
 * which would re-run the whole query and save a duplicate Turn. */
export function useChatStream(docId: string, callbacks: ChatStreamCallbacks = {}) {
  const { t } = useLang();
  const [state, setState] = useState<StreamState>(IDLE);
  const esRef = useRef<EventSource | null>(null);
  const callbacksRef = useRef(callbacks);
  // Callbacks live in a ref, so send's identity does not depend on them and reopen the stream
  useEffect(() => {
    callbacksRef.current = callbacks;
  });

  const close = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  useEffect(() => close, [docId, close]);

  const send = useCallback(
    (question: string, model?: string | null) => {
      close();
      setState({ ...IDLE, status: 'streaming' });

      const params = new URLSearchParams({ doc_id: docId, question });
      if (model) params.set('model', model);
      const url = `${API_URL}/chat/stream?${params}`;
      // withCredentials: the session cookie lives on the API's origin
      const es = new EventSource(url, { withCredentials: true });
      esRef.current = es;

      es.addEventListener('status', (e) => {
        const { node } = JSON.parse((e as MessageEvent).data);
        setState((s) => ({ ...s, statusNode: node }));
      });
      es.addEventListener('citations', (e) => {
        const citations: Citation[] = JSON.parse((e as MessageEvent).data);
        setState((s) => ({ ...s, citations }));
      });
      es.addEventListener('token', (e) => {
        const text: string = JSON.parse((e as MessageEvent).data);
        setState((s) => ({ ...s, answer: s.answer + text }));
      });
      es.addEventListener('done', () => {
        close();
        setState(IDLE);
        callbacksRef.current.onDone?.();
      });
      // "failed", not "error": EventSource reserves "error" for connection failures
      es.addEventListener('failed', (e) => {
        const { detail } = JSON.parse((e as MessageEvent).data);
        close();
        setState(IDLE);
        callbacksRef.current.onError?.(detail);
      });
      es.onerror = () => {
        close();
        // close() detaches this handler, so reaching here means a real mid-stream drop
        setState(IDLE);
        callbacksRef.current.onError?.(t.errorGeneric);
      };
    },
    [docId, close, t],
  );

  return { state, send };
}
