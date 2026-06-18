/**
 * System-config hooks — currently exposes the budget self-approval
 * threshold (used by both budget activation and BCR approval).
 *
 * Reads from `GET /api/v1/system-config/budget.self_approval_threshold_gbp`
 * (system_config.view; PM and above). Falls back to the backend default
 * (£10,000) when the request fails — the backend remains the authority
 * either way (a 403 BudgetSelfApprovalError is the safety net).
 */
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

const KEY = 'budget.self_approval_threshold_gbp';
const FALLBACK = 10000;

export function useBudgetSelfApprovalThreshold() {
  const q = useQuery({
    queryKey: ['system-config', KEY],
    queryFn: async ({ signal }) => {
      const { data } = await api.get(`/v1/system-config/${KEY}`, { signal });
      // Backend returns { config_value: number, raw_value: string, ... }.
      const n = Number(data?.config_value ?? data?.raw_value);
      return Number.isFinite(n) ? n : FALLBACK;
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
  return {
    threshold: q.data ?? FALLBACK,
    isLoading: q.isLoading,
  };
}

// ─── B107 §2 — unbudgeted-order sign-off floor ────────────────────────
// The budget grid reads this to choose RED (blocking, committed ≥ floor)
// vs AMBER (flagged, below floor) for un-cleared unbudgeted lines, and the
// PO line editor uses it for the mint-hint figure. £1000 fallback is the
// backend default (seed_system_config.py) — display-only if the fetch
// fails; the server gate stays the authority.
const FLOOR_KEY = 'budget.unbudgeted_ack_floor_gbp';
const FLOOR_FALLBACK = 1000;

export function useUnbudgetedAckFloor() {
  const q = useQuery({
    queryKey: ['system-config', FLOOR_KEY],
    queryFn: async ({ signal }) => {
      const { data } = await api.get(`/v1/system-config/${FLOOR_KEY}`, { signal });
      const n = Number(data?.config_value ?? data?.raw_value);
      return Number.isFinite(n) ? n : FLOOR_FALLBACK;
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
  return { floor: q.data ?? FLOOR_FALLBACK, isLoading: q.isLoading };
}
