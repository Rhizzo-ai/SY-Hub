/**
 * Cost-codes hook wrapper (Build Pack v2 D13, errata E5).
 *
 * `useCostCodes(projectId)` returns the enabled cost codes for the
 * project. Used by §R7 (LineDrawer's CostCodePicker) and by the lines
 * grid for cost-code label rendering (the budget API returns
 * `cost_code_id` only — the human label comes from this map).
 *
 * Backend: GET /v1/projects/:projectId/cost-codes. Returns a flat array
 * of `{ id, code, label, enabled, ... }`. We keep all of them (including
 * disabled) because a line may still reference a disabled code; callers
 * filter on `enabled` when rendering the picker.
 *
 * staleTime is 5min — cost codes change rarely; aggressive caching is
 * worth the staleness window.
 */
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { api } from '@/lib/api';

async function fetchCostCodes(projectId, signal) {
  // Backend: cost_codes_router is mounted directly under /api (NOT /api/v1).
  // The list endpoint returns `ProjectCostCodeRead` rows whose `id` is
  // the project_cost_codes mapping id — the FK on budget_lines is
  // `cost_code_id`, which is a separate field on this payload.
  const { data } = await api.get(`/projects/${projectId}/cost-codes`, {
    signal,
  });
  // Defensive double-shape (bare array vs {items: []}).
  if (Array.isArray(data)) return data;
  return data?.items ?? [];
}

export function useCostCodes(projectId) {
  return useQuery({
    queryKey: ['cost-codes', projectId],
    queryFn: ({ signal }) => fetchCostCodes(projectId, signal),
    enabled: !!projectId,
    staleTime: 5 * 60_000,
    // Chat 39 §R2 C-UNCAT: keep the previous payload during a refetch
    // so the cost-code map never blanks mid-render. Without this the
    // grid briefly groups every line under "— Uncategorised —" while
    // a post-mutation refetch is in flight.
    placeholderData: keepPreviousData,
  });
}

/**
 * Helper: build a `Map<cost_code_id, costCodeRow>` for O(1) label
 * lookups in grids. Keyed by `cost_code_id` (NOT row.id) because the
 * `ProjectCostCodeRead` payload's `id` is the project_cost_codes
 * mapping row id, while `BudgetLine.cost_code_id` references the
 * underlying `cost_codes.id`. Memoised at call-site (see §R6 grid).
 */
export function buildCostCodeMap(rows) {
  const m = new Map();
  for (const row of rows ?? []) {
    // Test fixtures pass minimal `{ id, code, name }` shapes (no
    // cost_code_id) — fall back to `id` so existing tests still pass.
    const key = row?.cost_code_id ?? row?.id;
    if (key) m.set(key, row);
  }
  return m;
}
