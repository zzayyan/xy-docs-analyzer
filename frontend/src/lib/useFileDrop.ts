import { useState, type DragEvent } from 'react';

/** dragleave also fires entering a child, so leaving counts only once outside the target. */
export function useFileDrop(onFile: (file: File) => void) {
  const [active, setActive] = useState(false);

  const handlers = {
    onDragOver: (e: DragEvent<HTMLElement>) => {
      if (!e.dataTransfer.types.includes('Files')) return;
      e.preventDefault();
      setActive(true);
    },
    onDragLeave: (e: DragEvent<HTMLElement>) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setActive(false);
    },
    onDrop: (e: DragEvent<HTMLElement>) => {
      e.preventDefault();
      setActive(false);
      const file = e.dataTransfer.files?.[0];
      if (file) onFile(file);
    },
  };

  return { active, handlers };
}
