/**
 * Subcontract Valuations hooks — Chat 48 (Build Pack 2.8-FE-ii §R3.3).
 *
 * TanStack Query wrappers per the established hook conventions in
 * `hooks/subcontracts.js`. Query keys nested so mutations can
 * invalidate granularly.
 *
 * Invalidation policy (matches §R3.3):
 *   - createValuation        → list (Draft appears).
 *   - submit/certify/reject  → detail AND list (badge resync) via
 *                              `onSettled` so a 409 also triggers a
 *                              resync refetch (the 2.8-FE-i pattern).
 *   - certify ALSO invalidates the payment-notices list for the
 *     valuation — the backend auto-creates a 'Payment' notice.
 *
 * The 409 vs 422 distinction is the caller's responsibility (component
 * layer). Mutations reject with the axios error carrying
 * `response.data.detail`; the dialog/button surfaces the toast.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as valApi from '@/lib/api/subcontractValuations';
import { noticeKeys } from '@/hooks/paymentNotices';


export const valKeys = {
  all: ['subcontract-valuations'],
  list: (params) => ['subcontract-valuations', 'list', params ?? {}],
  detail: (id) => ['subcontract-valuation', id],
};


// ─── Queries ────────────────────────────────────────────────────────

export function useValuations({ params, enabled = true } = {}) {
  return useQuery({
    queryKey: valKeys.list(params),
    queryFn: ({ signal }) =>
      valApi.listValuations({ ...(params ?? {}), signal }),
    enabled,
  });
}

export function useValuation(valuationId, { enabled = true } = {}) {
  return useQuery({
    queryKey: valKeys.detail(valuationId),
    queryFn: ({ signal }) => valApi.getValuation(valuationId, { signal }),
    enabled: enabled && !!valuationId,
  });
}


// ─── Mutations ──────────────────────────────────────────────────────

export function useCreateValuation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => valApi.createValuation(body),
    onSuccess: () => {
      // Any valuations list invalidates — the new Draft may match the
      // current filter.
      qc.invalidateQueries({ queryKey: valKeys.all });
    },
  });
}


// Lifecycle: invalidate detail + list on settled (success or failure),
// matching the 2.8-FE-i hook idiom. A 409 still resyncs the displayed
// status so the badge matches reality after the user dismisses the
// toast.

export function useSubmitValuation(valuationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => valApi.submitValuation(valuationId),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: valKeys.detail(valuationId) });
      qc.invalidateQueries({ queryKey: valKeys.all });
    },
  });
}

export function useCertifyValuation(valuationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => valApi.certifyValuation(valuationId, body),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: valKeys.detail(valuationId) });
      qc.invalidateQueries({ queryKey: valKeys.all });
      // Backend auto-creates a 'Payment' notice on certify — make sure
      // the notices list for this valuation refetches so the panel
      // shows it immediately.
      qc.invalidateQueries({ queryKey: noticeKeys.list(valuationId) });
    },
  });
}

export function useRejectValuation(valuationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => valApi.rejectValuation(valuationId, body),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: valKeys.detail(valuationId) });
      qc.invalidateQueries({ queryKey: valKeys.all });
    },
  });
}
