import { useState, type DragEvent } from 'react';

/** Drag-and-drop a single file onto any element: spread `handlers` on it, read `active` for the
 * hover affordance. dragleave also fires when the pointer crosses into a child element, so it's
 * only treated as leaving once the pointer is outside the drop target entirely. */
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
