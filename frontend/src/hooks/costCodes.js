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
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

async function fetchCostCodes(projectId, signal) {
  const { data } = await api.get(`/v1/projects/${projectId}/cost-codes`, {
    signal,
  });
  // Backend returns a bare array (verified against
  // backend/app/routers/cost_codes.py — list endpoint produces []
  // not {items:[]}). Defensive double-shape.
  if (Array.isArray(data)) return data;
  return data?.items ?? [];
}

export function useCostCodes(projectId) {
  return useQuery({
    queryKey: ['cost-codes', projectId],
    queryFn: ({ signal }) => fetchCostCodes(projectId, signal),
    enabled: !!projectId,
    staleTime: 5 * 60_000,
  });
}

/**
 * Helper: build a `Map<id, costCode>` for O(1) label lookups in
 * grids. Memoised at call-site (see §R6 grid header).
 */
export function buildCostCodeMap(rows) {
  const m = new Map();
  for (const row of rows ?? []) {
    if (row && row.id) m.set(row.id, row);
  }
  return m;
}
