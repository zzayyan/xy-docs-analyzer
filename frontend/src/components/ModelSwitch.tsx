import { useEffect, useRef, useState } from 'react';
import { useLang } from '../lib/i18n';

interface ModelSwitchProps {
  value: string | null;
  onChange: (model: string) => void;
  choices: string[];
}

/** Custom listbox, not <select>: the OS draws <select>'s open list and ignores CSS. */
export function ModelSwitch({ value, onChange, choices }: ModelSwitchProps) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onPointerDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('mousedown', onPointerDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('mousedown', onPointerDown);
    };
  }, [open]);

  if (choices.length === 0) return null;

  return (
    <div ref={wrapRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        className="chip"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t.modelLabel}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="truncate">{value ?? t.modelLabel}</span>
        <span aria-hidden style={{ color: 'var(--text-muted)', fontSize: 9 }}>▾</span>
      </button>

      {open && (
        <div className="menu" role="listbox">
          {choices.map((choice) => (
            <button
              key={choice}
              type="button"
              role="option"
              aria-selected={choice === value}
              className="menu-item"
              onClick={() => {
                onChange(choice);
                setOpen(false);
              }}
            >
              {choice}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
