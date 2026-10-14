import { useEffect, useRef } from 'react';

interface ToastProps {
  message: string;
  onDismiss: () => void;
  duration?: number;
}

export function Toast({ message, onDismiss, duration = 6000 }: ToastProps) {
  // onDismiss is a fresh closure every render; depending on it would restart the countdown forever
  const dismissRef = useRef(onDismiss);
  useEffect(() => {
    dismissRef.current = onDismiss;
  });

  useEffect(() => {
    const timer = setTimeout(() => dismissRef.current(), duration);
    return () => clearTimeout(timer);
  }, [message, duration]);

  return (
    <div
      role="alert"
      onClick={onDismiss}
      style={{
        position: 'fixed',
        bottom: 'var(--space-6)',
        right: 'var(--space-6)',
        maxWidth: 360,
        padding: 'var(--space-4)',
        background: 'var(--surface-danger-soft)',
        border: 'var(--stroke-hairline) solid var(--brand-primary)',
        borderRadius: 'var(--radius-sm)',
        color: 'var(--text-danger-soft)',
        fontSize: 'var(--fs-ui-sm)',
        lineHeight: 'var(--lh-body)',
        boxShadow: 'var(--shadow-lg)',
        cursor: 'pointer',
        zIndex: 100,
      }}
    >
      {message}
    </div>
  );
}
