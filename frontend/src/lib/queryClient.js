/**
 * TanStack Query v5 client — single shared instance for the SY Hub app.
 *
 * Defaults align with Build Pack v2 §R1.6:
 *   - staleTime 30s: coarse cache for nav-back snappiness without staleness
 *   - gcTime 5min: drop unused caches after that
 *   - refetchOnWindowFocus: catch out-of-band edits from another tab
 *   - retry only on 5xx (4xx are deterministic; let the caller surface them)
 *   - mutations never retry (may not be idempotent)
 */
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: true,
      retry: (failureCount, error) => {
        const status = error?.response?.status;
        if (status && status >= 400 && status < 500) return false;
        return failureCount < 2;
      },
    },
    mutations: {
      retry: false,
    },
  },
});
