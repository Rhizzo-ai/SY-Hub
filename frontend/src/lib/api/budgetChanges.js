/**
 * Budget Change Requests (BCR) API client — Prompt 2.6-FE §R1.
 *
 * Wraps the 10 backend endpoints from `app/routers/budget_changes.py`
 * (mounted at /api/v1, see server.py). Same shape as suppliers / POs
 * (lib/api.js baseURL is `/api`, so all calls prepend `/v1/...`).
 *
 * State machine (from services/budget_changes.py):
 *   Draft ──submit──> Submitted ──approve──> Approved ──apply──> Applied
 *                                  └─reject──> Rejected (terminal)
 *   Draft / Submitted ──withdraw──> Withdrawn (terminal)
 *
 * IMPORTANT: approve does NOT auto-apply. A separate POST /apply is
 * required to mutate budget_lines.approved_changes and recompute the
 * parent summary. The UI must surface this two-step explicitly.
 */
import { api } from '@/lib/api';

// ─── List + read ────────────────────────────────────────────────────
// GET /api/v1/budget-changes requires budget_id. There is NO cross-
// budget / cross-project list endpoint today (backlog B51).
export async function listBCRs(budgetId, { signal, params } = {}) {
  const { data } = await api.get(`/v1/budget-changes`, {
    signal,
    params: { budget_id: budgetId, ...(params ?? {}) },
  });
  return data;
}

export async function getBCR(bcrId, { signal } = {}) {
  const { data } = await api.get(`/v1/budget-changes/${bcrId}`, { signal });
  return data;
}

export async function listChangeLog(budgetId, { signal } = {}) {
  const { data } = await api.get(
    `/v1/budgets/${budgetId}/change-log`, { signal },
  );
  return data;
}

// ─── Create + edit ──────────────────────────────────────────────────
export async function createBCR(body) {
  const { data } = await api.post(`/v1/budget-changes`, body);
  return data;
}

export async function patchBCR(bcrId, body) {
  const { data } = await api.patch(`/v1/budget-changes/${bcrId}`, body);
  return data;
}

// ─── Lifecycle transitions ──────────────────────────────────────────
export async function submitBCR(bcrId) {
  const { data } = await api.post(`/v1/budget-changes/${bcrId}/submit`, {});
  return data;
}

export async function approveBCR(bcrId) {
  const { data } = await api.post(`/v1/budget-changes/${bcrId}/approve`, {});
  return data;
}

export async function rejectBCR(bcrId, body) {
  // body: { reason: string } — required (min_length=1 at backend).
  const { data } = await api.post(`/v1/budget-changes/${bcrId}/reject`, body);
  return data;
}

export async function withdrawBCR(bcrId) {
  const { data } = await api.post(`/v1/budget-changes/${bcrId}/withdraw`, {});
  return data;
}

export async function applyBCR(bcrId) {
  const { data } = await api.post(`/v1/budget-changes/${bcrId}/apply`, {});
  return data;
}
