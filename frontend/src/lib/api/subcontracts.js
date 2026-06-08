/**
 * Subcontracts API client — Chat 47 (Build Pack 2.8-FE-i §R3.1).
 *
 * Thin axios wrappers around the v1 subcontracts endpoints. Mirrors
 * lib/api/suppliers.js shape: shared `lib/api.js` baseURL is `/api`, so
 * each path here is prefixed `/v1/...` ourselves. All functions return
 * the response body directly (`data`).
 *
 * Endpoint contract (from backend/app/routers/subcontracts.py, verified
 * Chat 47 — origin/main, alembic head 0043_document_folders):
 *
 *   GET    /v1/subcontracts?project_id=&status=&limit=&offset=
 *                                     → { items, total }
 *   GET    /v1/subcontracts/{id}      → serialised subcontract
 *   POST   /v1/subcontracts           → 201 + serialised subcontract
 *   PATCH  /v1/subcontracts/{id}      → updated subcontract
 *   POST   /v1/subcontracts/{id}/activate   → updated subcontract
 *   POST   /v1/subcontracts/{id}/complete   → updated subcontract
 *   POST   /v1/subcontracts/{id}/terminate  → updated subcontract
 *
 * Error mapping (mirrored in hook callers + components):
 *   404 — not found / cross-tenant.
 *   409 — state error (e.g. activate non-Draft, activate unsigned,
 *         complete non-Active, terminate already-terminal). The UI
 *         MUST treat 409 distinctly from 422: surface the server
 *         `detail`, then refetch to resync the displayed status.
 *   422 — validation error (server `detail` shown).
 *   403 — missing permission.
 *
 * Sensitive contract-sum fields (`original_contract_sum`,
 * `current_contract_sum`) come back as `null` for callers without
 * `subcontracts.view_sensitive`; render via the existing em-dash
 * fallback in <SensitiveValue/> when null.
 *
 * Build-Pack §R3.1 wire contracts pinned in __tests__/subcontracts.test.js:
 *   - createSubcontract body MUST NOT include `reference` (backend
 *     generates it) or `status` (transitions go via action endpoints).
 *   - updateSubcontract body uses Pydantic `extra:"forbid"` server-side;
 *     the caller is responsible for trimming to the allowed set
 *     (`title, scope_description, original_contract_sum, retention_pct,
 *     cis_applies, start_on, end_on, signed_at, signed_by,
 *     purchase_order_id`). Sending `project_id` / `subcontractor_id` /
 *     `status` would 422.
 */
import { api } from '@/lib/api';

// ─── List + read ────────────────────────────────────────────────────

/**
 * List subcontracts visible to the caller.
 *
 * Params (all optional):
 *   - projectId — server-side filter on `project_id`.
 *   - status    — one of 'Draft' | 'Active' | 'Completed' | 'Terminated'.
 *   - limit     — 1..200 (server-clamped).
 *   - offset    — ≥0.
 *
 * Note (Build Pack §R4.1): the endpoint has NO `subcontractor_id` filter;
 * the supplier Contracts tab fetches the visible set then filters
 * client-side by `subcontractor_id === supplierId`. Surfaced in §R9
 * backlog as a future backend follow-up.
 */
export async function listSubcontracts(
  { projectId, status, limit, offset, signal } = {},
) {
  const params = {};
  if (projectId != null) params.project_id = projectId;
  if (status != null) params.status = status;
  if (limit != null) params.limit = limit;
  if (offset != null) params.offset = offset;
  const { data } = await api.get('/v1/subcontracts', { signal, params });
  return data;
}

export async function getSubcontract(subcontractId, { signal } = {}) {
  const { data } = await api.get(
    `/v1/subcontracts/${subcontractId}`, { signal },
  );
  return data;
}

// ─── Create + edit ──────────────────────────────────────────────────

/**
 * Create a Draft subcontract.
 *
 * Body shape (mirrors `SubcontractCreateBody`):
 *   { project_id, subcontractor_id, title,
 *     scope_description?, purchase_order_id?,
 *     original_contract_sum?, retention_pct?, cis_applies?,
 *     start_on?, end_on? }
 *
 * Caller MUST omit `reference` (backend generates SC-NNNN) and `status`
 * (defaults to Draft; transitions go via action endpoints).
 */
export async function createSubcontract(body) {
  const { data } = await api.post('/v1/subcontracts', body);
  return data;
}

/**
 * Patch a subcontract.
 *
 * Server uses Pydantic `extra:"forbid"`. The caller must send ONLY
 * fields in `SubcontractUpdateBody`:
 *   title, scope_description, original_contract_sum, retention_pct,
 *   cis_applies, start_on, end_on, signed_at, signed_by,
 *   purchase_order_id.
 *
 * Sending project_id / subcontractor_id / status → 422.
 */
export async function updateSubcontract(subcontractId, body) {
  const { data } = await api.patch(
    `/v1/subcontracts/${subcontractId}`, body,
  );
  return data;
}

// ─── Lifecycle transitions ──────────────────────────────────────────
//
// Action endpoints take no body. On a 409 (e.g. activating a non-Draft,
// activating an unsigned subcontract, completing a non-Active,
// terminating a terminal) the caller surfaces the server `detail` and
// refetches the detail+list to resync.

export async function activateSubcontract(subcontractId) {
  const { data } = await api.post(
    `/v1/subcontracts/${subcontractId}/activate`, {},
  );
  return data;
}

export async function completeSubcontract(subcontractId) {
  const { data } = await api.post(
    `/v1/subcontracts/${subcontractId}/complete`, {},
  );
  return data;
}

export async function terminateSubcontract(subcontractId) {
  const { data } = await api.post(
    `/v1/subcontracts/${subcontractId}/terminate`, {},
  );
  return data;
}
