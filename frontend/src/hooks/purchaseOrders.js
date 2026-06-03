/**
 * Suppliers / Purchase Orders / Number Prefix hooks — Chat 24 §R5.
 *
 * TanStack Query wrappers per Build Pack §5.6 convention (matches
 * hooks/actuals.js, hooks/budgets.js shapes). Query keys are nested so
 * mutations can invalidate granularly.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as suppliersApi from '@/lib/api/suppliers';
import * as poApi from '@/lib/api/purchaseOrders';
import * as prefixApi from '@/lib/api/numberPrefixes';

// ─── Suppliers ───────────────────────────────────────────────────────
export const suppliersKeys = {
  all: ['suppliers'],
  list: (params) => ['suppliers', 'list', params ?? {}],
  detail: (id) => ['supplier', id],
};

export function useSuppliers({ params, enabled = true } = {}) {
  return useQuery({
    queryKey: suppliersKeys.list(params),
    queryFn: ({ signal }) => suppliersApi.listSuppliers({ signal, params }),
    enabled,
  });
}

export function useSupplier(supplierId, { enabled = true } = {}) {
  return useQuery({
    queryKey: suppliersKeys.detail(supplierId),
    queryFn: ({ signal }) => suppliersApi.getSupplier(supplierId, { signal }),
    enabled: enabled && !!supplierId,
  });
}

export function useCreateSupplier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => suppliersApi.createSupplier(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: suppliersKeys.all }); },
  });
}

export function usePatchSupplier(supplierId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => suppliersApi.patchSupplier(supplierId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: suppliersKeys.detail(supplierId) });
      qc.invalidateQueries({ queryKey: suppliersKeys.all });
    },
  });
}

export function useArchiveSupplier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => suppliersApi.archiveSupplier(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: suppliersKeys.all }); },
  });
}

// §R2 D4 — was `useRestoreSupplier` calling `/restore`; backend mounts
// `/unarchive`, so the old hook silently 404'd. Rename + reroute.
export function useUnarchiveSupplier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => suppliersApi.unarchiveSupplier(id),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: suppliersKeys.detail(id) });
      qc.invalidateQueries({ queryKey: suppliersKeys.all });
    },
  });
}


// ─── Purchase Orders ─────────────────────────────────────────────────
export const poKeys = {
  all: ['purchase-orders'],
  projectList: (projectId, params) =>
    ['purchase-orders', 'project', projectId, params ?? {}],
  budgetLineList: (lineId) =>
    ['purchase-orders', 'budget-line', lineId],
  budgetList: (budgetId) =>
    ['purchase-orders', 'budget', budgetId],
  detail: (poId) => ['purchase-order', poId],
  receipts: (poId) => ['purchase-order', poId, 'receipts'],
};

export function useProjectPOs(projectId, { params, enabled = true } = {}) {
  return useQuery({
    queryKey: poKeys.projectList(projectId, params),
    queryFn: ({ signal }) => poApi.listProjectPOs(projectId, { signal, params }),
    enabled: enabled && !!projectId,
  });
}

// R5.5 — Budget-line scoped POs. Driven lazily by the R6 expandable
// row: the hook is mounted only when the row is expanded, so
// `enabled: !!lineId` is sufficient to defer the fetch until first
// expand.
//
// `staleTime` is non-zero so that when the R6 Expand-All flow
// hydrates every line's cache from P0.2 in ONE bulk call, the
// downstream POsSection mounts find the data fresh and DON'T fire
// individual GETs. 30s mirrors the typical user dwell on a line
// without being long enough to mask stale data after a mutation.
export function useBudgetLinePOs(lineId, { enabled = true } = {}) {
  return useQuery({
    queryKey: poKeys.budgetLineList(lineId),
    queryFn: ({ signal }) => poApi.listBudgetLinePOs(lineId, { signal }),
    enabled: enabled && !!lineId,
    staleTime: 30_000,
  });
}

// R5.5 — Bulk PO fetch indexed by budget_line_id. Not consumed by R6
// (each row fetches its own), but exposed here so future "expand-all"
// flows have a single batch endpoint.
export function useBudgetPOs(budgetId, { enabled = true } = {}) {
  return useQuery({
    queryKey: poKeys.budgetList(budgetId),
    queryFn: ({ signal }) => poApi.listBudgetPOs(budgetId, { signal }),
    enabled: enabled && !!budgetId,
  });
}

export function usePO(poId, { enabled = true } = {}) {
  return useQuery({
    queryKey: poKeys.detail(poId),
    queryFn: ({ signal }) => poApi.getPO(poId, { signal }),
    enabled: enabled && !!poId,
  });
}

export function useCreatePO(projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => poApi.createPO(projectId, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: poKeys.all }); },
  });
}

export function usePatchPO(poId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => poApi.patchPO(poId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: poKeys.detail(poId) });
      qc.invalidateQueries({ queryKey: poKeys.all });
    },
  });
}

// R7 Batch 2 — Delete a draft PO. Backend enforces 422 on non-draft,
// the UI mounts the button only on draft (mirrors that contract).
// Invalidates the global PO list namespace so the now-deleted row
// disappears from any cached project list.
export function useDeletePO(poId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => poApi.deletePO(poId),
    onSuccess: () => {
      qc.removeQueries({ queryKey: poKeys.detail(poId) });
      qc.invalidateQueries({ queryKey: poKeys.all });
    },
  });
}

// R7.6 — verbs that change *commitment* on the budget line(s) this PO
// touches. After settle we coarse-invalidate `['budgets']` so the
// Budgets grid's committed column refreshes alongside the PO detail.
// (The transition hook does not have budgetId/lineId on hand, so the
// coarse precedent from budgets.js:245 is the right shape.)
//
//   - void      — releases committed → 0
//   - sendBack  — approved → draft; trigger drops committed → 0
//   - approve   — pending_approval → approved; commitment first appears
//   - close     — issued/receipted → closed; releases committed → 0
//
// R7-polish — `issue` removed: approved → issued is a status flip
// between two states both inside the commitment-inclusion set
// (approved, issued, partially_receipted, receipted) per
// 0032_po_approvals.py fn_budget_line_recompute_commitments, so the
// trigger leaves committed_value unchanged. Invalidating `['budgets']`
// on issue was dead weight.
//
// `receipt` is its own hook (`useCreateReceipt` below).
const COMMITMENT_VERBS = new Set(['void', 'sendBack', 'approve', 'close']);

// R7.6 — verbs that benefit from an optimistic PO-detail patch while
// the request is in flight. Each entry returns the patch to apply on
// the cached `po` object so the status pill + action set update
// instantly. On error we roll back; on settle we invalidate.
//
// We deliberately keep the set narrow (void / sendBack only): these
// are the destructive / corrective verbs where the perceived
// latency is most jarring. issue / approve / close still benefit from
// the budgets-cache invalidation above but go through the plain
// onSuccess path because a botched optimistic status flip on those
// would surface scary intermediate UI.
const OPTIMISTIC_STATUS_PATCH = {
  void: () => ({ status: 'voided' }),
  sendBack: () => ({ status: 'draft' }),
};

export function usePoTransition(poId, verb) {
  const qc = useQueryClient();
  const fn = {
    submit: () => poApi.submitPO(poId),
    approve: (body) => poApi.approvePO(poId, body),
    reject: (body) => poApi.rejectPO(poId, body),
    // R7.0b — approved → draft. R7.6 — sendBack is now a commitment-
    // changing verb; the coarse `['budgets']` invalidation below
    // refreshes the R6 grid's committed column on settle.
    sendBack: (body) => poApi.sendBackPO(poId, body),
    issue: () => poApi.issuePO(poId),
    void: (body) => poApi.voidPO(poId, body),
    close: () => poApi.closePO(poId),
  }[verb];

  const isCommitmentVerb = COMMITMENT_VERBS.has(verb);
  const patchFn = OPTIMISTIC_STATUS_PATCH[verb];

  return useMutation({
    mutationFn: fn,
    // R7.6 — optimistic PO-detail patch (void / sendBack only). Mirrors
    // the budgets.js:137-156 / 169-200 onMutate/onError/onSettled shape.
    onMutate: patchFn ? async () => {
      await qc.cancelQueries({ queryKey: poKeys.detail(poId) });
      const prev = qc.getQueryData(poKeys.detail(poId));
      if (prev) {
        qc.setQueryData(poKeys.detail(poId), { ...prev, ...patchFn() });
      }
      return { prev };
    } : undefined,
    onError: patchFn ? (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(poKeys.detail(poId), ctx.prev);
    } : undefined,
    onSettled: () => {
      qc.invalidateQueries({ queryKey: poKeys.detail(poId) });
      qc.invalidateQueries({ queryKey: poKeys.all });
      if (isCommitmentVerb) {
        // AC5 — refresh the Budgets grid's committed column. Coarse
        // invalidation is intentional: the hook has no budgetId/lineId
        // and budgets.js:245 sets the in-repo precedent.
        qc.invalidateQueries({ queryKey: ['budgets'] });
      }
    },
  });
}


// R7.3 — list approval rows for a PO. Mounted by <POApprovalPanel/>
// when status === 'pending_approval' to surface the open row's
// budget_snapshot. Disabled by default so it doesn't fire on every PO
// detail mount.
export function usePOApprovals(poId, { enabled = true } = {}) {
  return useQuery({
    queryKey: ['purchase-order', poId, 'approvals'],
    queryFn: ({ signal }) => poApi.listPOApprovals(poId, { signal }),
    enabled: enabled && !!poId,
  });
}


// ─── Receipts (R4) ───────────────────────────────────────────────────
export function useReceipts(poId, { enabled = true } = {}) {
  return useQuery({
    queryKey: poKeys.receipts(poId),
    queryFn: ({ signal }) => poApi.listReceipts(poId, { signal }),
    enabled: enabled && !!poId,
  });
}

export function useCreateReceipt(poId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => poApi.createReceipt(poId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: poKeys.detail(poId) });
      qc.invalidateQueries({ queryKey: poKeys.receipts(poId) });
      // R7.6 / AC5 — a receipt moves committed → actual, so the Budgets
      // grid's committed column is stale until refreshed. Coarse
      // invalidation mirrors the budgets.js:245 precedent (no
      // budgetId/lineId on hand here).
      qc.invalidateQueries({ queryKey: ['budgets'] });
    },
  });
}


// ─── Number prefixes ─────────────────────────────────────────────────
export const prefixKeys = {
  list: (projectId, params) =>
    ['number-prefixes', projectId, params ?? {}],
};

export function usePrefixes(projectId, { params, enabled = true } = {}) {
  return useQuery({
    queryKey: prefixKeys.list(projectId, params),
    queryFn: ({ signal }) => prefixApi.listPrefixes(projectId, { signal, params }),
    enabled: enabled && !!projectId,
  });
}

export function useCreatePrefix(projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => prefixApi.createPrefix(projectId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['number-prefixes', projectId] });
    },
  });
}

export function usePatchPrefix(projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => prefixApi.patchPrefix(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['number-prefixes', projectId] });
    },
  });
}
