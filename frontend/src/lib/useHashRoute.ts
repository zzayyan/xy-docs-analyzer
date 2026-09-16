import { useEffect, useState } from 'react';

/** Current location.hash with the leading "#" stripped, e.g. "/doc/abc123". Updates on navigation
 * and browser back/forward, and survives a page refresh — which is the point of using the hash
 * instead of pulling in a router for what is currently two screens. */
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
