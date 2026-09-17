import { useEffect } from 'react';

interface ToastProps {
  message: string;
  onDismiss: () => void;
  /** ms before auto-dismiss. Default 6000. */
  duration?: number;
}

/** Not in the design system's component set (it has no toast/snackbar), built from the same
 * tokens. Auto-dismisses but stays clickable to dismiss early — errors worth surfacing (a 413
 * from the upload cap, a failed delete) are worth reading, not just flashing past. */
export function Toast({ message, onDismiss, duration = 6000 }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, duration);
    return () => clearTimeout(timer);
  }, [onDismiss, duration]);

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
