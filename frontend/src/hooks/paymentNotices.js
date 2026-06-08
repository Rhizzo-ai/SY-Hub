/**
 * Payment Notices hooks — Chat 48 (Build Pack 2.8-FE-ii §R3.3).
 *
 * TanStack Query wrappers per the established hook conventions in
 * `hooks/subcontracts.js` / `hooks/subcontractValuations.js`. Keys are
 * scoped per-valuation so the certify mutation can invalidate just the
 * relevant slice (see hooks/subcontractValuations.js → useCertifyValuation).
 *
 * Enablement: the notices list query is `enabled` only when a valuation
 * id is supplied — components call it with `enabled: status === 'Certified'`
 * (a Draft/Submitted/Rejected valuation has no notices).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as noticesApi from '@/lib/api/paymentNotices';


export const noticeKeys = {
  all: ['payment-notices'],
  list: (valuationId) => ['payment-notices', 'list', { valuationId }],
};


// ─── Queries ────────────────────────────────────────────────────────

export function usePaymentNotices(valuationId, { enabled = true } = {}) {
  return useQuery({
    queryKey: noticeKeys.list(valuationId),
    queryFn: ({ signal }) =>
      noticesApi.listPaymentNotices({
        subcontractValuationId: valuationId, signal,
      }),
    enabled: enabled && !!valuationId,
  });
}


// ─── Mutations ──────────────────────────────────────────────────────

/**
 * Issue a PayLess notice against a Certified valuation. Invalidates
 * the notices list for that valuation so the new PayLess row appears.
 */
export function useCreatePayLess(valuationId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => noticesApi.createPayLessNotice(body),
    onSettled: () => {
      if (valuationId) {
        qc.invalidateQueries({ queryKey: noticeKeys.list(valuationId) });
      } else {
        qc.invalidateQueries({ queryKey: noticeKeys.all });
      }
    },
  });
}
