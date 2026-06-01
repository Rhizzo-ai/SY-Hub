/**
 * BCR React Query hooks — Prompt 2.6-FE §R1.
 *
 * Same nested-key convention as hooks/purchaseOrders.js. Mutations
 * coarse-invalidate ['budgets'] when the verb affects the parent
 * budget's totals (the BCR `apply` writes approved_changes and
 * recomputes the summary). Other verbs only touch BCR caches.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as bcrApi from '@/lib/api/budgetChanges';

export const bcrKeys = {
  all: ['budget-changes'],
  budgetList: (budgetId, params) =>
    ['budget-changes', 'budget', budgetId, params ?? {}],
  changeLog: (budgetId) => ['budget-change-log', budgetId],
  detail: (bcrId) => ['budget-change', bcrId],
};

// ─── Queries ────────────────────────────────────────────────────────
export function useBudgetBCRs(budgetId, { params, enabled = true } = {}) {
  return useQuery({
    queryKey: bcrKeys.budgetList(budgetId, params),
    queryFn: ({ signal }) =>
      bcrApi.listBCRs(budgetId, { signal, params }),
    enabled: enabled && !!budgetId,
  });
}

export function useBudgetChangeLog(budgetId, { enabled = true } = {}) {
  return useQuery({
    queryKey: bcrKeys.changeLog(budgetId),
    queryFn: ({ signal }) => bcrApi.listChangeLog(budgetId, { signal }),
    enabled: enabled && !!budgetId,
  });
}

export function useBCR(bcrId, { enabled = true } = {}) {
  return useQuery({
    queryKey: bcrKeys.detail(bcrId),
    queryFn: ({ signal }) => bcrApi.getBCR(bcrId, { signal }),
    enabled: enabled && !!bcrId,
  });
}

// ─── Mutations ──────────────────────────────────────────────────────
export function useCreateBCR() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => bcrApi.createBCR(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: bcrKeys.all });
      qc.invalidateQueries({ queryKey: ['budget-change-log'] });
    },
  });
}

export function usePatchBCR(bcrId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => bcrApi.patchBCR(bcrId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: bcrKeys.detail(bcrId) });
      qc.invalidateQueries({ queryKey: bcrKeys.all });
    },
  });
}

// `apply` is the ONLY verb that mutates the parent budget — it writes
// approved_changes and runs recompute_summary. Coarse-invalidate the
// ['budgets'] namespace so the grid's current_budget / variance refresh.
const BUDGET_MUTATING_VERBS = new Set(['apply']);

export function useBCRTransition(bcrId, verb) {
  const qc = useQueryClient();
  const fn = {
    submit: () => bcrApi.submitBCR(bcrId),
    approve: () => bcrApi.approveBCR(bcrId),
    reject: (body) => bcrApi.rejectBCR(bcrId, body),
    withdraw: () => bcrApi.withdrawBCR(bcrId),
    apply: () => bcrApi.applyBCR(bcrId),
  }[verb];

  const isBudgetMutating = BUDGET_MUTATING_VERBS.has(verb);

  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      qc.invalidateQueries({ queryKey: bcrKeys.detail(bcrId) });
      qc.invalidateQueries({ queryKey: bcrKeys.all });
      qc.invalidateQueries({ queryKey: ['budget-change-log'] });
      if (isBudgetMutating) {
        // BCR apply writes budget_lines.approved_changes and runs
        // budgets_svc.recompute_summary — the BudgetGridV2 needs to
        // re-fetch. Coarse invalidation mirrors the purchaseOrders.js
        // commitment-verb pattern (see hooks/purchaseOrders.js:235).
        qc.invalidateQueries({ queryKey: ['budgets'] });
        qc.invalidateQueries({ queryKey: ['budget'] });
      }
    },
  });
}
