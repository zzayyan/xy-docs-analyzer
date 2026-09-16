import { Logo } from './design-system';
import { LanguageSwitch } from './components/LanguageSwitch';
import { DocumentsScreen } from './screens/DocumentsScreen';
import { DocumentScreen } from './screens/DocumentScreen';
import { useLang } from './lib/i18n';
import { useHashRoute } from './lib/useHashRoute';

// Single-destination shell: the design system's XylmShellScreen pattern uses a 264px SideNav rail
// for a multi-module product (Ask / Finance / HR / Documents / Governance). This app currently has
// one top-level screen (the document list; a document's own page is a drill-down, not a nav item),
// so a permanent empty rail would just eat width — a header carries the branding instead. Revisit
// with SideNav if a second top-level section (e.g. settings) shows up.
function App() {
  const { t } = useLang();
  const route = useHashRoute();
  const docMatch = route.match(/^\/doc\/(.+)$/);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
      <header
        style={{
          height: 'var(--app-topbar-h)',
          flex: '0 0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 var(--space-6)',
          borderBottom: 'var(--stroke-hairline) solid var(--border-subtle)',
          background: 'var(--surface-card)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <Logo variant="mark" height={22} basePath="/design-system/assets/" />
          <span style={{ fontSize: 'var(--fs-ui-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>
            {t.appName}
          </span>
        </div>
        <LanguageSwitch />
      </header>
      <main style={{ flex: 1, minHeight: 0, padding: 'var(--space-8) var(--space-6)' }}>
        {docMatch ? <DocumentScreen docId={docMatch[1]} /> : <DocumentsScreen />}
      </main>
    </div>
  );
}

export default App;
