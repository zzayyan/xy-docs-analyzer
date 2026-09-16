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
  /** Fires once the answer is fully streamed and persisted server-side. */
  onDone?: () => void;
  /** Fires on an application-level failure (backend's "failed" event) or a connection drop
   * (EventSource's own onerror) -- either way the backend still persisted a partial Turn. */
  onError?: (message: string) => void;
}

/** GET /chat/stream via native EventSource -- the endpoint is GET specifically so this needs no
 * extra library. EventSource auto-reconnects on any connection drop, including a server-closed
 * one; without calling close() on every terminal path (done, failed, network onerror, and on
 * unmount/docId change) it would silently re-run the whole LangGraph query and write a duplicate
 * Turn -- the single most expensive bug available in this design (see backend/app/api.py).
 *
 * Terminal handling is done via callbacks fired directly from the SSE event handlers, not by the
 * caller watching state.status in an effect: the state change and the side effect (invalidating
 * the turns query, showing a toast) are the same event, so there's nothing to synchronize --
 * "when this arrives, do that" belongs in the handler that receives it. */
export function useChatStream(docId: string, callbacks: ChatStreamCallbacks = {}) {
  const { t } = useLang();
  const [state, setState] = useState<StreamState>(IDLE);
  const esRef = useRef<EventSource | null>(null);
  const callbacksRef = useRef(callbacks);
  // Writing a ref during render (rather than here) breaks React's rules and can misbehave under
  // concurrent rendering; this effect keeps the ref at the latest callbacks without making send's
  // own identity depend on them (which would tear down and reopen the EventSource on every
  // render if the caller passes new callback closures each time, as ChatPanel does).
  useEffect(() => {
    callbacksRef.current = callbacks;
  });

  const close = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  useEffect(() => close, [docId, close]);

  const send = useCallback(
    (question: string) => {
      close();
      setState({ ...IDLE, status: 'streaming' });

      const url = `${API_URL}/chat/stream?${new URLSearchParams({ doc_id: docId, question })}`;
      const es = new EventSource(url);
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
      // Named "failed" on the backend, deliberately not "error" -- EventSource reserves that name
      // for its own connection-level failures below, and the two payload shapes don't match.
      es.addEventListener('failed', (e) => {
        const { detail } = JSON.parse((e as MessageEvent).data);
        close();
        setState(IDLE);
        callbacksRef.current.onError?.(detail);
      });
      es.onerror = () => {
        close();
        // A native onerror after "done" already closed the connection can't happen -- close()
        // detaches all listeners, this handler included -- so reaching here always means the
        // stream genuinely dropped mid-flight.
        setState(IDLE);
        callbacksRef.current.onError?.(t.errorGeneric);
      };
    },
    [docId, close, t],
  );

  return { state, send };
}
