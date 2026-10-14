import { useEffect, useRef } from 'react';
import { Button } from '../design-system';
import { useLang } from '../lib/i18n';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Native <dialog>: focus trap, Escape and backdrop click come free. */
export function ConfirmDialog({ open, title, body, confirmLabel, danger, onConfirm, onCancel }: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = useLang();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onCancel={onCancel}
      onClose={onCancel}
      style={{
        border: 'var(--stroke-hairline) solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        padding: 0,
        width: 'min(420px, 90vw)',
        background: 'var(--surface-card)',
        color: 'var(--text-body)',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <div style={{ padding: 'var(--space-6)', display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <h2 style={{ margin: 0, fontSize: 'var(--fs-ui-lg)', fontWeight: 'var(--fw-bold)', color: 'var(--text-title)' }}>
          {title}
        </h2>
        <p style={{ margin: 0, fontSize: 'var(--fs-ui-sm)', lineHeight: 'var(--lh-body)', color: 'var(--text-card-body)' }}>
          {body}
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)', marginTop: 'var(--space-2)' }}>
          <Button variant="ghost" onClick={onCancel}>
            {t.deleteConfirmCancel}
          </Button>
          <Button variant="primary" onClick={onConfirm} style={danger ? { background: 'var(--status-danger)', borderColor: 'var(--status-danger)' } : undefined}>
            {confirmLabel ?? t.deleteConfirmConfirm}
          </Button>
        </div>
      </div>
    </dialog>
  );
}
