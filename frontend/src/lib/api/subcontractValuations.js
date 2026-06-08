/**
 * Subcontract Valuations API client — Chat 48 (Build Pack 2.8-FE-ii §R3.1).
 *
 * Thin axios wrappers around the `/v1/subcontract-valuations` endpoints.
 * Mirrors `lib/api/subcontracts.js` conventions: shared `lib/api.js`
 * baseURL is `/api`, so paths here are prefixed `/v1/...` ourselves.
 * All functions return the response body directly (`data`).
 *
 * Endpoint contract (verified origin/main, Chat 48,
 * routers/subcontract_valuations.py + services/subcontract_valuations.py
 * + models/sc_valuations.py — alembic head 0043_document_folders):
 *
 *   POST   /v1/subcontract-valuations              → 201 valuation
 *   GET    /v1/subcontract-valuations              → { items, total }
 *      params: subcontract_id, status, limit, offset
 *   GET    /v1/subcontract-valuations/{id}         → valuation
 *   POST   /v1/subcontract-valuations/{id}/submit  → updated valuation
 *   POST   /v1/subcontract-valuations/{id}/certify → updated valuation
 *   POST   /v1/subcontract-valuations/{id}/reject  → updated valuation
 *
 * Money fields are STRINGS on the wire (Pydantic Decimal serialisation).
 * The UI must NEVER do float maths — the server is the single source of
 * truth for all money calculations (retention, CIS, net payable). This
 * client is a thin pass-through: it does not validate, transform, or
 * compute. Callers send strings, callers receive strings.
 *
 * Error mapping (mirrored in hook callers + components):
 *   - 404  not found / cross-tenant (never leaks existence).
 *   - 409  STATE error (wrong workflow status, wrong parent status,
 *          missing budget_line_id at certify, budget line not on the
 *          subcontract's project). UI surfaces `detail` distinctly from
 *          422 and refetches to resync.
 *   - 422  VALIDATION error (gross < previously certified, labour +
 *          materials != gross_this_cert, net payable < 0, negative
 *          inputs at create, blank rejection reason). UI surfaces the
 *          server `detail` verbatim — the maths messages are
 *          user-meaningful.
 *   - 403  missing permission.
 *
 * Permission map (verified, differs from earlier guesses):
 *   - submit  → `subcontract_valuations.create`  (NOT a separate perm)
 *   - certify → `subcontract_valuations.certify`
 *   - reject  → `subcontract_valuations.certify` (shared)
 *
 * Sensitive money fields on the GET serialiser (gated by
 * `subcontract_valuations.view_sensitive`, null otherwise):
 *   previous_certified_net, retention_this_cert, cis_rate_pct,
 *   cis_deduction_this_cert, net_payable_this_cert
 */
import { api } from '@/lib/api';


// ─── List + read ────────────────────────────────────────────────────

/**
 * List valuations visible to the caller.
 *
 * Params (all optional except convention):
 *   - subcontractId — REQUIRED in practice (this surface is always
 *     scoped to a parent subcontract); sent as `subcontract_id`.
 *   - status        — 'Draft' | 'Submitted' | 'Certified' | 'Rejected'.
 *                     Other values 422 server-side.
 *   - limit         — 1..200 (server-clamped).
 *   - offset        — >= 0.
 *
 * Snake_case forwarding is hard-pinned in __tests__/subcontractValuations.test.js
 * — the backend rejects camelCase keys.
 */
export async function listValuations(
  { subcontractId, status, limit, offset, signal } = {},
) {
  const params = {};
  if (subcontractId != null) params.subcontract_id = subcontractId;
  if (status != null) params.status = status;
  if (limit != null) params.limit = limit;
  if (offset != null) params.offset = offset;
  const { data } = await api.get(
    '/v1/subcontract-valuations', { signal, params },
  );
  return data;
}

export async function getValuation(valuationId, { signal } = {}) {
  const { data } = await api.get(
    `/v1/subcontract-valuations/${valuationId}`, { signal },
  );
  return data;
}


// ─── Create ──────────────────────────────────────────────────────────

/**
 * Create a Draft valuation. Body (verified ValuationCreateBody):
 *   { subcontract_id          (uuid, required),
 *     gross_applied_to_date   (str Decimal, required),
 *     labour_portion          (str Decimal, default "0"),
 *     materials_portion       (str Decimal, default "0"),
 *     period_start            (date | null),
 *     period_end              (date | null) }
 *
 * 422 from the backend at create:
 *   - gross_applied_to_date < 0
 *   - labour_portion < 0 or materials_portion < 0
 *
 * 409 from the backend at create:
 *   - parent subcontract not in {Active, Completed}
 *     ("Cannot create a valuation on a {status} subcontract …")
 *
 * Thin pass-through: caller is responsible for sending money as
 * STRINGS (e.g. "10000.00", not 10000). The wire test asserts this.
 */
export async function createValuation(body) {
  const { data } = await api.post('/v1/subcontract-valuations', body);
  return data;
}


// ─── Lifecycle transitions ──────────────────────────────────────────
//
// All action endpoints return the updated valuation. On 409 (wrong
// status), the caller surfaces the server detail and refetches to
// resync the displayed status badge.

/**
 * Submit: Draft → Submitted.
 * Body: {} (empty). Permission: subcontract_valuations.create.
 * 409 if status != Draft.
 */
export async function submitValuation(valuationId) {
  const { data } = await api.post(
    `/v1/subcontract-valuations/${valuationId}/submit`, {},
  );
  return data;
}

/**
 * Certify: Submitted → Certified. Body (verified ValuationCertifyBody):
 *   { transaction_date  (date | null),
 *     description       (str | null, <= 500),
 *     budget_line_id    (uuid, REQUIRED) }
 *
 * Permission: subcontract_valuations.certify.
 *
 * The backend REFUSES to guess the budget line — `budget_line_id` is
 * a hard requirement. This client is a pass-through; the UI's certify
 * dialog disables Confirm until a line is selected, and the wire test
 * asserts the body shape.
 *
 * 409 cases:
 *   - status != Submitted ("must be Submitted")
 *   - missing budget_line_id  ("budget_line_id is required …")
 *   - budget line not on this subcontract's project
 *     ("budget_line is not on the subcontract's project")
 *
 * 422 cases (the maths guards — surface verbatim):
 *   - gross_this_cert < 0  (application went backwards)
 *   - labour + materials != gross_this_cert  (split mismatches the
 *     NEW-this-cert gross, NOT the cumulative — see §R4.4 UX note)
 *   - net_payable_this_cert < 0
 */
export async function certifyValuation(valuationId, body) {
  const { data } = await api.post(
    `/v1/subcontract-valuations/${valuationId}/certify`, body,
  );
  return data;
}

/**
 * Reject: Submitted → Rejected. Body: { reason (str, 1..2000) }.
 * Permission: subcontract_valuations.certify (shared with certify).
 *
 * 409 if status != Submitted.
 * 422 if reason blank ("rejection reason is required").
 */
export async function rejectValuation(valuationId, body) {
  const { data } = await api.post(
    `/v1/subcontract-valuations/${valuationId}/reject`, body,
  );
  return data;
}
