import { useLang, type Lang } from '../lib/i18n';

const OPTIONS: Lang[] = ['en', 'id'];

export function LanguageSwitch() {
  const { lang, setLang, t } = useLang();
  const label: Record<Lang, string> = { en: t.langEnglish, id: t.langIndonesian };

  return (
    <div
      role="group"
      aria-label="Language"
      style={{
        display: 'inline-flex',
        border: 'var(--stroke-hairline) solid var(--border-subtle)',
        borderRadius: 'var(--radius-sm)',
        overflow: 'hidden',
      }}
    >
      {OPTIONS.map((option) => {
        const active = option === lang;
        return (
          <button
            key={option}
            type="button"
            aria-pressed={active}
            onClick={() => setLang(option)}
            style={{
              padding: '6px 12px',
              fontSize: 'var(--fs-ui-xs)',
              fontWeight: 'var(--fw-semibold)',
              letterSpacing: 'var(--ls-caps)',
              cursor: active ? 'default' : 'pointer',
              border: 'none',
              background: active ? 'var(--brand-primary)' : 'transparent',
              color: active ? 'var(--text-on-brand)' : 'var(--text-muted)',
              transition: 'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard)',
            }}
          >
            {label[option]}
          </button>
        );
      })}
    </div>
  );
}
