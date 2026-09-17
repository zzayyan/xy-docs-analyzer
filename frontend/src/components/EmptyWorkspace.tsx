import { useQuery } from '@tanstack/react-query';
import { Logo } from '../design-system';
import { UploadButton } from './UploadButton';
import { api } from '../lib/api';
import { useFileDrop } from '../lib/useFileDrop';
import { useLang } from '../lib/i18n';

export function EmptyWorkspace({ onUpload, uploading }: { onUpload: (file: File) => void; uploading: boolean }) {
  const { t } = useLang();
  const drop = useFileDrop(onUpload);
  const limitsQuery = useQuery({ queryKey: ['limits'], queryFn: api.limits });

  return (
    <>
      <div className="pane-header" />
      <div
        className="workspace-empty"
        data-drop={drop.active}
        {...drop.handlers}
        style={{ flex: 1, minHeight: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-6)' }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-4)', maxWidth: 380, textAlign: 'center' }}>
          <Logo variant="mark" height={32} basePath="/design-system/assets/" style={{ opacity: 0.5 }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <h1
              style={{
                margin: 0,
                fontSize: 'var(--fs-ui-lg)',
                fontWeight: 'var(--fw-semibold)',
                letterSpacing: 'var(--ls-title)',
                color: 'var(--text-title)',
              }}
            >
              {drop.active ? t.dropActive : t.emptyTitle}
            </h1>
            <p style={{ margin: 0, lineHeight: 'var(--lh-body)', color: 'var(--text-card-body)' }}>{t.emptyBody}</p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            <UploadButton onFile={onUpload} uploading={uploading} size="md" />
            {limitsQuery.data && (
              <span style={{ fontSize: 'var(--fs-ui-xs)', color: 'var(--text-muted)' }}>
                {t.uploadLimitsCaption(limitsQuery.data.max_upload_mb, limitsQuery.data.max_pages)}
              </span>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
