import { useQuery } from '@tanstack/react-query';
import { Logo } from '../design-system';
import { LanguageSwitch } from './LanguageSwitch';
import { UploadButton } from './UploadButton';
import { api, isInFlight, type Document, type User } from '../lib/api';
import { formatRelative } from '../lib/format';
import { statusLabel } from '../lib/status';
import { useFileDrop } from '../lib/useFileDrop';
import { useLang } from '../lib/i18n';

interface DocumentRailProps {
  activeId: string | null;
  onUpload: (file: File) => void;
  uploading: boolean;
  onToggle: () => void;
  user: User;
  onLogout: () => void;
}

export function DocumentRail({ activeId, onUpload, uploading, onToggle, user, onLogout }: DocumentRailProps) {
  const { t } = useLang();
  const drop = useFileDrop(onUpload);

  const limitsQuery = useQuery({ queryKey: ['limits'], queryFn: api.limits });
  const documentsQuery = useQuery({
    queryKey: ['documents'],
    queryFn: api.listDocuments,
    refetchInterval: (query) => (query.state.data?.some((d) => isInFlight(d.status)) ? 3000 : false),
  });
  const documents = documentsQuery.data ?? [];

  return (
    <aside className="rail" data-drop={drop.active} {...drop.handlers}>
      {/* Shown instead of everything else while the rail is collapsed (CSS, desktop only) */}
      <div className="rail-strip">
        <button className="quiet-button rail-toggle" onClick={onToggle} aria-label={t.railExpand} title={t.railExpand}>
          <PanelIcon />
        </button>
      </div>

      <div className="rail-body">
        <div className="pane-header">
          <Logo variant="mark" height={20} basePath="/design-system/assets/" />
          <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>{t.appName}</span>
          <button
            className="quiet-button rail-toggle"
            style={{ marginLeft: 'auto' }}
            onClick={onToggle}
            aria-label={t.railCollapse}
            title={t.railCollapse}
          >
            <PanelIcon />
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px 8px' }}>
          <span style={{ fontSize: 'var(--fs-ui-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-card-title)' }}>
            {t.railDocuments}
            {documentsQuery.data && (
              <span style={{ marginLeft: 6, fontWeight: 'var(--fw-regular)', color: 'var(--text-muted)' }}>{documents.length}</span>
            )}
          </span>
          <UploadButton onFile={onUpload} uploading={uploading} variant="secondary" />
        </div>

        <nav style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2, paddingBottom: 12 }}>
          {documentsQuery.isPending &&
            [64, 48, 72, 56].map((w) => (
              <div key={w} style={{ padding: '10px 20px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div className="skeleton-block" style={{ height: 12, width: `${w}%` }} />
                <div className="skeleton-block" style={{ height: 10, width: '36%' }} />
              </div>
            ))}

          {documentsQuery.isError && (
            <p style={{ margin: 0, padding: '8px 20px', fontSize: 'var(--fs-ui-xs)', color: 'var(--status-danger)' }}>{t.errorGeneric}</p>
          )}

          {documentsQuery.isSuccess && documents.length === 0 && (
            <p style={{ margin: 0, padding: '8px 20px', fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>{t.railEmpty}</p>
          )}

          {documents.map((doc) => (
            <RailItem key={doc.id} doc={doc} active={doc.id === activeId} />
          ))}
        </nav>

        <div
          style={{
            flex: '0 0 auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 'var(--space-3)',
            padding: '10px 20px',
            borderTop: 'var(--stroke-hairline) solid var(--border-subtle)',
          }}
        >
          <span style={{ fontSize: 11, lineHeight: 1.35, color: 'var(--text-muted)' }}>
            {drop.active
              ? t.dropActive
              : limitsQuery.data
                ? t.uploadLimitsShort(limitsQuery.data.max_upload_mb, limitsQuery.data.max_pages)
                : limitsQuery.isError
                  ? t.uploadLimitsUnavailable
                  : ''}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            <LanguageSwitch />
            <button
              className="quiet-button"
              style={{ padding: 5 }}
              onClick={onLogout}
              aria-label={t.logout(user.username)}
              title={t.logout(user.username)}
            >
              <LogoutIcon />
            </button>
          </span>
        </div>
      </div>
    </aside>
  );
}

function PanelIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="2" y="2.5" width="12" height="11" rx="2" />
      <path d="M6 2.5v11" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 2.5H3.5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1H6" />
      <path d="M10.5 11 13.5 8l-3-3M13.5 8H6" />
    </svg>
  );
}

function RailItem({ doc, active }: { doc: Document; active: boolean }) {
  const { t, lang } = useLang();
  const inFlight = isInFlight(doc.status);

  let meta: React.ReactNode;
  if (inFlight) {
    meta = (
      <span style={{ color: 'var(--brand-primary)' }}>
        {statusLabel(doc.status, t)}
        {doc.step_total ? ` ${doc.step_done ?? 0}/${doc.step_total}` : ''}
      </span>
    );
  } else if (doc.status === 'error') {
    meta = <span style={{ color: 'var(--status-danger)' }}>{t.statusError}</span>;
  } else {
    meta = (
      <>
        <span>{doc.mode === 'long' ? t.modeLong : t.modeShort}</span>
        {doc.created_at && <span>{formatRelative(doc.created_at, lang, t.relativeJustNow)}</span>}
      </>
    );
  }

  return (
    <a href={`#/doc/${doc.id}`} className="rail-item" aria-current={active ? 'page' : undefined} title={doc.name}>
      <div
        className="truncate"
        style={{ fontWeight: active ? 'var(--fw-semibold)' : 'var(--fw-medium)', color: 'var(--text-title)', lineHeight: 1.35 }}
      >
        {doc.name}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 2, fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>{meta}</div>
      {inFlight && (
        <div style={{ height: 2, marginTop: 7, borderRadius: 2, background: 'var(--surface-raised)', overflow: 'hidden' }}>
          <div
            style={{
              height: '100%',
              width: `${Math.round(doc.progress * 100)}%`,
              background: 'var(--brand-primary)',
              transition: 'width var(--dur-slow) var(--ease-out)',
            }}
          />
        </div>
      )}
    </a>
  );
}
