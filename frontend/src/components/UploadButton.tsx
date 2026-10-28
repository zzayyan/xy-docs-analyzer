import { useRef } from 'react';
import { Button } from '../design-system';
import { useLang } from '../lib/i18n';

interface UploadButtonProps {
  onFile: (file: File) => void;
  uploading: boolean;
  variant?: 'primary' | 'secondary';
  size?: 'sm' | 'md';
  /** Extensions the file picker offers, e.g. ".pdf,.docx" */
  accept?: string;
}

export function UploadButton({ onFile, uploading, variant = 'primary', size = 'sm', accept }: UploadButtonProps) {
  const { t } = useLang();
  const input = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={input}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = ''; // allow re-selecting the same file after an error
          if (file) onFile(file);
        }}
      />
      <Button variant={variant} size={size} onClick={() => input.current?.click()} disabled={uploading}>
        {uploading ? t.uploadUploading : t.uploadButton}
      </Button>
    </>
  );
}
