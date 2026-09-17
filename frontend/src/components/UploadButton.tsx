import { useRef } from 'react';
import { Button } from '../design-system';
import { useLang } from '../lib/i18n';

interface UploadButtonProps {
  onFile: (file: File) => void;
  uploading: boolean;
  variant?: 'primary' | 'secondary';
  size?: 'sm' | 'md';
}

export function UploadButton({ onFile, uploading, variant = 'primary', size = 'sm' }: UploadButtonProps) {
  const { t } = useLang();
  const input = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={input}
        type="file"
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
