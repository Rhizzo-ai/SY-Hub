/**
 * React Query hooks for the Actuals API (Chat 19B §R1.3).
 *
 * Same shape as `hooks/budgets.js` (chat-17 §R3). Conventions:
 *   - Query keys are nested for granular invalidation.
 *   - Every queryFn threads `signal` for queryClient.cancelQueries().
 *   - Mutations invalidate the parent query rather than push the response
 *     into the cache directly, so the next render reflects fully-recomputed
 *     totals (budget detail's actuals_to_date, etc.).
 *   - No mutation retries (queryClient default). 4xx errors surface to
 *     onError; page-level toast layer handles the "Conflict — please
 *     reload" path for 409.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as actualsApi from '@/lib/api/actuals';

// ─── Query-key helpers ───────────────────────────────────────────────
export const actualsKeys = {
  all: ['actuals'],
  list: (params) => ['actuals', 'list', params ?? {}],
  projectList: (projectId, params) =>
    ['actuals', 'project', projectId, params ?? {}],
  byBudgetLine: (budgetLineId, projectId) =>
    ['actuals', 'by-budget-line', budgetLineId, projectId],
  detail: (actualId) => ['actual', actualId],
  changeLog: (actualId) => ['actual-change-log', actualId],
  attachments: (actualId) => ['actual-attachments', actualId],
};

// ─── Queries ─────────────────────────────────────────────────────────
export function useActuals({ params, enabled = true } = {}) {
  return useQuery({
    queryKey: actualsKeys.list(params),
    queryFn: ({ signal }) => actualsApi.listActuals({ signal, params }),
    enabled,
  });
}

export function useProjectActuals(projectId, { params, enabled = true } = {}) {
  return useQuery({
    queryKey: actualsKeys.projectList(projectId, params),
    queryFn: ({ signal }) =>
      actualsApi.listProjectActuals(projectId, { signal, params }),
    enabled: enabled && !!projectId,
  });
}

/**
 * Chat 23 R4.4 — actuals (bills) attached to a single budget line.
 * Uses the existing /api/v1/actuals listing with the `budget_line_id`
 * query parameter (confirmed in routers/actuals.py:65).
 *
 * Previously consumed by the per-line BillsSection (deleted in R6);
 * retained because actuals lists are still surfaced elsewhere when a line row
 * is expanded. staleTime: 30s — pops new bills into the drilldown
 * relatively quickly without thrashing during keyboard-driven row
 * navigation.
 */
export function useActualsForBudgetLine(budgetLineId, projectId, { enabled = true } = {}) {
  return useQuery({
    queryKey: actualsKeys.byBudgetLine(budgetLineId, projectId),
    queryFn: ({ signal }) => actualsApi.listActuals({
      signal,
      params: {
        budget_line_id: budgetLineId,
        project_id: projectId,
        limit: 50,
      },
    }),
    enabled: enabled && !!budgetLineId,
    staleTime: 30_000,
  });
}

export function useActual(actualId, { enabled = true } = {}) {
  return useQuery({
    queryKey: actualsKeys.detail(actualId),
    queryFn: ({ signal }) => actualsApi.getActual(actualId, { signal }),
    enabled: enabled && !!actualId,
  });
}

export function useActualChangeLog(actualId, { enabled = true } = {}) {
  return useQuery({
    queryKey: actualsKeys.changeLog(actualId),
    queryFn: ({ signal }) => actualsApi.getChangeLog(actualId, { signal }),
    enabled: enabled && !!actualId,
  });
}

export function useActualAttachments(actualId, { enabled = true } = {}) {
  return useQuery({
    queryKey: actualsKeys.attachments(actualId),
    queryFn: ({ signal }) => actualsApi.listAttachments(actualId, { signal }),
    enabled: enabled && !!actualId,
  });
}

// ─── Mutations ───────────────────────────────────────────────────────
// Pattern: invalidate the affected lists + detail key on success.
// No mutations retry (queryClient default).

function _invalidateAll(qc, actualId, projectId) {
  qc.invalidateQueries({ queryKey: actualsKeys.all });
  if (actualId) {
    qc.invalidateQueries({ queryKey: actualsKeys.detail(actualId) });
    qc.invalidateQueries({ queryKey: actualsKeys.changeLog(actualId) });
  }
  if (projectId) {
    qc.invalidateQueries({ queryKey: ['actuals', 'project', projectId] });
    // ALSO invalidate budgets — actuals_to_date / committed totals changed.
    qc.invalidateQueries({ queryKey: ['budgets'] });
  }
}

export function useCreateActual() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => actualsApi.createActual(body),
    onSuccess: (data) => _invalidateAll(qc, data?.id, data?.project_id),
  });
}

export function useUpdateActual(actualId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => actualsApi.patchActual(actualId, body),
    onSuccess: (data) => _invalidateAll(qc, actualId, data?.project_id),
  });
}

export function useDeleteActual(actualId, projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => actualsApi.deleteActual(actualId),
    onSuccess: () => _invalidateAll(qc, actualId, projectId),
  });
}

export function usePostActual(actualId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body = {}) => actualsApi.postActual(actualId, body),
    onSuccess: (data) => _invalidateAll(qc, actualId, data?.project_id),
  });
}

export function useMarkPaid(actualId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => actualsApi.markPaid(actualId, body),
    onSuccess: (data) => _invalidateAll(qc, actualId, data?.project_id),
  });
}

export function useVoidActual(actualId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => actualsApi.voidActual(actualId, body),
    onSuccess: (data) => _invalidateAll(qc, actualId, data?.project_id),
  });
}

export function useDisputeActual(actualId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => actualsApi.disputeActual(actualId, body),
    onSuccess: (data) => _invalidateAll(qc, actualId, data?.project_id),
  });
}

export function useUndisputeActual(actualId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body = {}) => actualsApi.undisputeActual(actualId, body),
    onSuccess: (data) => _invalidateAll(qc, actualId, data?.project_id),
  });
}

export function useReleaseRetention(actualId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => actualsApi.releaseRetention(actualId, body),
    onSuccess: (data) => _invalidateAll(qc, actualId, data?.project_id),
  });
}

export function useUploadAttachment(actualId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file) => actualsApi.uploadAttachment(actualId, file),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: actualsKeys.attachments(actualId) }),
  });
}

export function useDeleteAttachment(actualId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId) =>
      actualsApi.deleteAttachment(actualId, attachmentId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: actualsKeys.attachments(actualId) }),
  });
}
