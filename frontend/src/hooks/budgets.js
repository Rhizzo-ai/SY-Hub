/**
 * React Query hooks for the Budgets API (Prompt 2.4B-i §R3.4).
 *
 * Conventions:
 *   - Query keys are nested per-resource for granular invalidation:
 *       ['budgets', { projectId }, params]      list
 *       ['budget',  budgetId]                   detail
 *       ['budget-line-items', lineId]           items
 *   - Every queryFn threads `signal` for queryClient.cancelQueries().
 *   - Mutations invalidate the parent query rather than push the response
 *     into the cache directly, so the next render reflects fully-recomputed
 *     totals (header bumps summary_refreshed_at, summary mutations bump
 *     server totals, etc.).
 *   - No mutation retries (see queryClient.js default). 4xx errors are
 *     surfaced to onError; the page-level toast layer handles the
 *     "Conflict — please reload" path for 409.
 *
 * NB: line-level optimistic mutations (description, notes, percentage_complete,
 * reorder) are wired in §R6/§R7. Hooks here expose `useMutation` directly so
 * the call-site can supply onMutate/onError/onSettled for optimistic UX.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as budgetsApi from '@/lib/api/budgets';

// ──────────────────────────────────────────────────────────────────────
// Query-key helpers
// ──────────────────────────────────────────────────────────────────────
export const budgetsKeys = {
  all:     ['budgets'],
  list:    (projectId, params) => ['budgets', { projectId }, params ?? {}],
  detail:  (budgetId) => ['budget', budgetId],
  items:   (lineId) => ['budget-line-items', lineId],
};

// ──────────────────────────────────────────────────────────────────────
// Queries
// ──────────────────────────────────────────────────────────────────────

export function useProjectBudgets(projectId, { params, enabled = true } = {}) {
  return useQuery({
    queryKey: budgetsKeys.list(projectId, params),
    queryFn: ({ signal }) =>
      budgetsApi.listProjectBudgets(projectId, { signal, params }),
    enabled: enabled && !!projectId,
  });
}

export function useBudget(budgetId, { enabled = true } = {}) {
  return useQuery({
    queryKey: budgetsKeys.detail(budgetId),
    queryFn: ({ signal }) => budgetsApi.getBudget(budgetId, { signal }),
    enabled: enabled && !!budgetId,
  });
}

export function useLineItems(lineId, { enabled = true } = {}) {
  return useQuery({
    queryKey: budgetsKeys.items(lineId),
    queryFn: ({ signal }) => budgetsApi.listLineItems(lineId, { signal }),
    enabled: enabled && !!lineId,
  });
}

// ──────────────────────────────────────────────────────────────────────
// Mutations (helper invalidator + per-action hooks)
// ──────────────────────────────────────────────────────────────────────

function makeInvalidate(qc, budgetId, projectId) {
  return () => {
    if (budgetId) {
      qc.invalidateQueries({ queryKey: budgetsKeys.detail(budgetId) });
    }
    if (projectId) {
      qc.invalidateQueries({
        queryKey: ['budgets', { projectId }], exact: false,
      });
    }
  };
}

export function useCreateBudgetFromAppraisal(projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) =>
      budgetsApi.createBudgetFromAppraisal(projectId, body),
    onSuccess: (data) => {
      qc.invalidateQueries({
        queryKey: ['budgets', { projectId }], exact: false,
      });
      // Pre-seed the detail cache so the redirect-to-detail is instant
      if (data?.id) qc.setQueryData(budgetsKeys.detail(data.id), data);
    },
  });
}

function lifecycleHook(action) {
  return function useLifecycleHook(budgetId, projectId) {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (body) => budgetsApi[action](budgetId, body),
      onSuccess: makeInvalidate(qc, budgetId, projectId),
    });
  };
}
export const useActivateBudget = lifecycleHook('activateBudget');
export const useLockBudget     = lifecycleHook('lockBudget');
export const useUnlockBudget   = lifecycleHook('unlockBudget');
export const useCloseBudget    = lifecycleHook('closeBudget');

export function useCreateNewBudgetVersion(budgetId, projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => budgetsApi.createNewBudgetVersion(budgetId, body),
    onSuccess: (data) => {
      // Invalidate both the source budget and the project list
      qc.invalidateQueries({ queryKey: budgetsKeys.detail(budgetId) });
      if (projectId) {
        qc.invalidateQueries({
          queryKey: ['budgets', { projectId }], exact: false,
        });
      }
      // Pre-seed the new budget's detail cache
      if (data?.id) qc.setQueryData(budgetsKeys.detail(data.id), data);
    },
  });
}

export function usePatchBudgetLine(budgetId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ lineId, body }) => budgetsApi.patchBudgetLine(lineId, body),
    // §R6 optimistic update for description / notes / percentage_complete
    // edits. The body keys are applied directly to the cached line so the
    // grid updates instantly. On error we roll back; on settled we
    // invalidate so the server-confirmed line (with refreshed totals +
    // variance + updated_at) replaces the optimistic copy.
    onMutate: async ({ lineId, body }) => {
      await qc.cancelQueries({ queryKey: budgetsKeys.detail(budgetId) });
      const prev = qc.getQueryData(budgetsKeys.detail(budgetId));
      if (prev?.lines) {
        qc.setQueryData(budgetsKeys.detail(budgetId), {
          ...prev,
          lines: prev.lines.map((ln) =>
            ln.id === lineId ? { ...ln, ...body } : ln,
          ),
        });
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(budgetsKeys.detail(budgetId), ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: budgetsKeys.detail(budgetId) });
    },
  });
}

export function useReorderBudgetLines(budgetId, projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orderedLineIds) =>
      budgetsApi.reorderBudgetLines({
        budget_id: budgetId,
        ordered_line_ids: orderedLineIds,
      }),
    // Optimistic update: rewrite display_order on the cached budget so
    // the grid jumps to the new order immediately. Rollback on error.
    onMutate: async (orderedLineIds) => {
      await qc.cancelQueries({ queryKey: budgetsKeys.detail(budgetId) });
      const prev = qc.getQueryData(budgetsKeys.detail(budgetId));
      if (prev?.lines) {
        const byId = new Map(prev.lines.map((ln) => [ln.id, ln]));
        const reordered = orderedLineIds
          .map((id, idx) => {
            const ln = byId.get(id);
            return ln ? { ...ln, display_order: idx } : null;
          })
          .filter(Boolean);
        qc.setQueryData(budgetsKeys.detail(budgetId), {
          ...prev, lines: reordered,
        });
      }
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) {
        qc.setQueryData(budgetsKeys.detail(budgetId), ctx.prev);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: budgetsKeys.detail(budgetId) });
      if (projectId) {
        qc.invalidateQueries({
          queryKey: ['budgets', { projectId }], exact: false,
        });
      }
    },
  });
}

export function useCreateLineItem(lineId, budgetId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => budgetsApi.createLineItem(lineId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetsKeys.items(lineId) });
      if (budgetId) {
        qc.invalidateQueries({ queryKey: budgetsKeys.detail(budgetId) });
      }
    },
  });
}

export function usePatchLineItem(lineId, budgetId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, body }) => budgetsApi.patchLineItem(itemId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetsKeys.items(lineId) });
      if (budgetId) {
        qc.invalidateQueries({ queryKey: budgetsKeys.detail(budgetId) });
      }
    },
  });
}

export function useDeleteLineItem(lineId, budgetId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemId) => budgetsApi.deleteLineItem(itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetsKeys.items(lineId) });
      if (budgetId) {
        qc.invalidateQueries({ queryKey: budgetsKeys.detail(budgetId) });
      }
    },
  });
}

export function useRefreshAttention() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => budgetsApi.refreshAttention(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['budgets'] }),
  });
}
