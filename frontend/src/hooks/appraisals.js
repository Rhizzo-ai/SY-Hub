/**
 * Appraisals hook wrapper (Build Pack v2 D12, errata E5 + D12.1 fallback).
 *
 * `useApprovedAppraisals(projectId, { enabled })` returns approved
 * appraisals for the project, excluding those already linked to the
 * current budget. Used by §R4.5 (CreateBudget dialog source picker).
 *
 * Server-side filtering deviation D12.1:
 *   The backend's GET /v1/projects/:id/appraisals endpoint accepts
 *   NO query params (verified 2026-05-10 against
 *   backend/app/routers/appraisals.py:510-527). We fetch the full list
 *   and filter client-side via `select`. The transformer runs once per
 *   refetch and is memoised by React Query.
 *
 * To exclude appraisals already linked to a budget, the caller must
 * pass `existingSourceAppraisalIds` (a Set of UUIDs derived from the
 * project's current budgets list). If null/undefined, only the
 * status filter is applied.
 */
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

async function fetchProjectAppraisals(projectId, signal) {
  const { data } = await api.get(`/v1/projects/${projectId}/appraisals`, {
    signal,
  });
  return data?.items ?? [];
}

export function useApprovedAppraisals(
  projectId,
  { enabled = true, existingSourceAppraisalIds = null } = {},
) {
  return useQuery({
    queryKey: ['appraisals', 'approved', projectId, {
      // Cache-key includes a stable representation of the exclude-set so
      // toggling the linked-budgets state busts the memo.
      exclude:
        existingSourceAppraisalIds instanceof Set
          ? [...existingSourceAppraisalIds].sort()
          : null,
    }],
    queryFn: ({ signal }) => fetchProjectAppraisals(projectId, signal),
    enabled: enabled && !!projectId,
    select: (rows) => rows.filter((a) => {
      if (a?.status !== 'Approved') return false;
      if (existingSourceAppraisalIds instanceof Set
          && existingSourceAppraisalIds.has(a.id)) {
        return false;
      }
      return true;
    }),
  });
}
