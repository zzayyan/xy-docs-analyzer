import { useEffect, useState } from 'react';

export function useHashRoute(): string {
  const [hash, setHash] = useState(() => location.hash.slice(1) || '/');
  useEffect(() => {
    const onChange = () => setHash(location.hash.slice(1) || '/');
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return hash;
}

export function navigate(path: string): void {
  location.hash = path;
}
