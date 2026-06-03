/**
 * CIS hooks — Chat 40 §R3 #10.
 *
 * TanStack Query wrappers around lib/api/cis.js. Invalidation contract
 * (§R4.4) on a successful record-verification:
 *   - ['cis', 'verifications', supplierId]  — history refresh
 *   - ['cis', 'current', supplierId]        — current-status banner
 *   - ['supplier', supplierId]              — Overview reflects new
 *                                             current_cis_status
 *   - ['suppliers']                         — list badge / unverified cue
 *
 * These literal keys match `suppliersKeys` in hooks/purchaseOrders.js.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as cisApi from '@/lib/api/cis';

export const cisKeys = {
  verifications: (supplierId) => ['cis', 'verifications', supplierId],
  current: (supplierId) => ['cis', 'current', supplierId],
};

export function useVerifications(supplierId, { enabled = true } = {}) {
  return useQuery({
    queryKey: cisKeys.verifications(supplierId),
    queryFn: ({ signal }) => cisApi.listVerifications(supplierId, { signal }),
    enabled: enabled && !!supplierId,
  });
}

export function useCurrentVerification(supplierId, { enabled = true } = {}) {
  return useQuery({
    queryKey: cisKeys.current(supplierId),
    queryFn: ({ signal }) => cisApi.getCurrentVerification(supplierId, { signal }),
    enabled: enabled && !!supplierId,
    // Backend returns null when no verification exists; treat as a
    // valid result rather than an error.
    retry: false,
  });
}

export function useRecordVerification(supplierId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => cisApi.createVerification({ ...body, supplier_id: supplierId }),
    onSuccess: () => {
      // §R4.4 — explicit invalidation list. Each key matters:
      //   verifications → history table
      //   current       → banner
      //   supplier      → Overview current_cis_status row
      //   suppliers     → list unverified cue / CIS column
      qc.invalidateQueries({ queryKey: cisKeys.verifications(supplierId) });
      qc.invalidateQueries({ queryKey: cisKeys.current(supplierId) });
      qc.invalidateQueries({ queryKey: ['supplier', supplierId] });
      qc.invalidateQueries({ queryKey: ['suppliers'] });
    },
  });
}
