import { useQuery } from '@tanstack/react-query';
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
      <div className="pane-header">
        <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-title)' }}>{t.emptyHeader}</span>
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '48px var(--space-6)' }}>
        <div
          className="dropzone"
          data-drop={drop.active}
          {...drop.handlers}
          style={{ maxWidth: 640, padding: '28px 28px 24px', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}
        >
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
            <p style={{ margin: 0, maxWidth: '56ch', lineHeight: 'var(--lh-body)', color: 'var(--text-card-body)', textWrap: 'pretty' }}>
              {t.emptyBody}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)', flexWrap: 'wrap' }}>
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
