/**
 * useIsDesktop — single source of truth for mobile read-only floor.
 *
 * Returns true when viewport is ≥ 768px (Tailwind `md`). Listens for
 * resize via matchMedia so the gate is reactive.
 *
 * Used by every Budgets write-path component (drawer save, lifecycle
 * buttons, drag-reorder, inline edit). When `false`, the component
 * renders its read-only branch.
 */
import { useEffect, useState } from 'react';

export function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(min-width: 768px)').matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia('(min-width: 768px)');
    const onChange = (e) => setIsDesktop(e.matches);
    if (mq.addEventListener) {
      mq.addEventListener('change', onChange);
      return () => mq.removeEventListener('change', onChange);
    }
    // Legacy fallback (Safari < 14)
    mq.addListener(onChange);
    return () => mq.removeListener(onChange);
  }, []);

  return isDesktop;
}
