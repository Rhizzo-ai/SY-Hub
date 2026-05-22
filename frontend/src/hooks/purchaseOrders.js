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
export function useBudgetLinePOs(lineId, { enabled = true } = {}) {
  return useQuery({
    queryKey: poKeys.budgetLineList(lineId),
    queryFn: ({ signal }) => poApi.listBudgetLinePOs(lineId, { signal }),
    enabled: enabled && !!lineId,
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

export function usePoTransition(poId, verb) {
  const qc = useQueryClient();
  const fn = {
    submit: () => poApi.submitPO(poId),
    approve: (body) => poApi.approvePO(poId, body),
    reject: (body) => poApi.rejectPO(poId, body),
    issue: () => poApi.issuePO(poId),
    void: (body) => poApi.voidPO(poId, body),
    close: () => poApi.closePO(poId),
  }[verb];
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: poKeys.detail(poId) });
      qc.invalidateQueries({ queryKey: poKeys.all });
    },
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
