/**
 * Subcontracts hooks — Chat 47 (Build Pack 2.8-FE-i §R3.2).
 *
 * TanStack Query wrappers per the established hook conventions in
 * `hooks/purchaseOrders.js` / `hooks/actuals.js`. Query keys are nested
 * so mutations can invalidate granularly.
 *
 * Lifecycle-mutation hooks invalidate BOTH the affected detail AND the
 * list namespace — a status flip changes the badge in the list as well
 * as the detail panel (Build Pack §R3.2).
 *
 * 409 handling is the caller's job (component layer): the mutation
 * rejects with the axios error carrying `response.data.detail`; we
 * still `onSettled`-invalidate so the displayed status resyncs after
 * the user dismisses the toast.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as scApi from '@/lib/api/subcontracts';


export const scKeys = {
  all: ['subcontracts'],
  list: (params) => ['subcontracts', 'list', params ?? {}],
  detail: (id) => ['subcontract', id],
};


// ─── Queries ────────────────────────────────────────────────────────

export function useSubcontracts({ params, enabled = true } = {}) {
  return useQuery({
    queryKey: scKeys.list(params),
    queryFn: ({ signal }) => scApi.listSubcontracts({ ...(params ?? {}), signal }),
    enabled,
  });
}

export function useSubcontract(subcontractId, { enabled = true } = {}) {
  return useQuery({
    queryKey: scKeys.detail(subcontractId),
    queryFn: ({ signal }) => scApi.getSubcontract(subcontractId, { signal }),
    enabled: enabled && !!subcontractId,
  });
}


// ─── Mutations ──────────────────────────────────────────────────────

export function useCreateSubcontract() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => scApi.createSubcontract(body),
    onSuccess: () => {
      // Any list query invalidates — the new row may match the current filter.
      qc.invalidateQueries({ queryKey: scKeys.all });
    },
  });
}

export function useUpdateSubcontract(subcontractId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => scApi.updateSubcontract(subcontractId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: scKeys.detail(subcontractId) });
      qc.invalidateQueries({ queryKey: scKeys.all });
    },
  });
}

// ─── Lifecycle transitions ──────────────────────────────────────────
//
// `onSettled` (not `onSuccess`) so the displayed status also resyncs
// after a 409 — the caller surfaces the toast, we refetch in the
// background to make sure the badge matches reality.

export function useActivateSubcontract(subcontractId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => scApi.activateSubcontract(subcontractId),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: scKeys.detail(subcontractId) });
      qc.invalidateQueries({ queryKey: scKeys.all });
    },
  });
}

export function useCompleteSubcontract(subcontractId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => scApi.completeSubcontract(subcontractId),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: scKeys.detail(subcontractId) });
      qc.invalidateQueries({ queryKey: scKeys.all });
    },
  });
}

export function useTerminateSubcontract(subcontractId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => scApi.terminateSubcontract(subcontractId),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: scKeys.detail(subcontractId) });
      qc.invalidateQueries({ queryKey: scKeys.all });
    },
  });
}
