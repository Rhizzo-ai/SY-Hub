/**
 * Payment Notices API client — Chat 48 (Build Pack 2.8-FE-ii §R3.2).
 *
 * Wraps `/v1/payment-notices` endpoints. Mirrors `lib/api/subcontracts.js`
 * + `lib/api/subcontractValuations.js` shape — shared `lib/api.js`
 * baseURL is `/api`, paths prefixed `/v1/...` here. All functions
 * return the response body directly.
 *
 * Endpoint contract (verified origin/main, Chat 48,
 * routers/payment_notices.py + services/payment_notices.py):
 *
 *   GET   /v1/payment-notices              → { items, total }
 *     params: subcontract_valuation_id, limit, offset
 *   GET   /v1/payment-notices/{id}         → notice
 *   POST  /v1/payment-notices/payless      → 201 notice
 *
 * Note (Build Pack §R0.2 scope fence): the retention-release endpoints
 *   POST /v1/subcontracts/{id}/retention-release
 *   GET  /v1/subcontracts/{id}/retention-releases
 * are explicitly OUT OF SCOPE in 2.8-FE-ii. They ship in 2.8-FE-iii-ret.
 * Do NOT add wrappers for them here.
 *
 * Notice types (verified models/sc_valuations.py):
 *   - 'Payment'   auto-created by the backend at certify time. The UI
 *                 does not POST these — they appear in the list after
 *                 the certify mutation invalidates the notices query.
 *   - 'PayLess'   manually issued via POST /payment-notices/payless,
 *                 against a CERTIFIED valuation.
 *
 * Notice serialiser fields (no sensitive gating on the serialiser
 * itself — gating is via `payment_notices.view` on the route):
 *   { id, tenant_id, subcontract_valuation_id, reference, notice_type,
 *     gross_certified, retention, cis_deducted, net_due,
 *     due_date, notes, issued_at, issued_by, created_at }
 * All money values are STRINGS.
 *
 * Error mapping:
 *   - 404  notice / valuation not found.
 *   - 409  PayLess against a non-Certified valuation
 *          ("PayLess notices can only be issued against a Certified
 *          valuation (current status: {status})").
 *   - 422  bad withhold_amount, blank reason, etc.
 *   - 403  missing permission.
 */
import { api } from '@/lib/api';


// ─── List + read ────────────────────────────────────────────────────

/**
 * List payment notices for a valuation.
 *
 * Params:
 *   - subcontractValuationId — sent as `subcontract_valuation_id`
 *     snake_case (backend rejects camelCase).
 *   - limit / offset         — standard pagination.
 */
export async function listPaymentNotices(
  { subcontractValuationId, limit, offset, signal } = {},
) {
  const params = {};
  if (subcontractValuationId != null) {
    params.subcontract_valuation_id = subcontractValuationId;
  }
  if (limit != null) params.limit = limit;
  if (offset != null) params.offset = offset;
  const { data } = await api.get('/v1/payment-notices', { signal, params });
  return data;
}

export async function getPaymentNotice(noticeId, { signal } = {}) {
  const { data } = await api.get(
    `/v1/payment-notices/${noticeId}`, { signal },
  );
  return data;
}


// ─── Create — PayLess only ──────────────────────────────────────────

/**
 * Issue a PayLess notice. Body (verified PayLessNoticeBody):
 *   { subcontract_valuation_id  (uuid, required),
 *     withhold_amount           (str Decimal, required, >= 0),
 *     reason                    (str, required, 1..2000),
 *     due_date                  (date | null) }
 *
 * Permission: payment_notices.create.
 *
 * The backend rejects PayLess on a non-Certified valuation with 409;
 * the UI gates the button behind status === 'Certified' but the
 * backend is the source of truth.
 *
 * Thin pass-through: caller sends withhold_amount as a STRING.
 */
export async function createPayLessNotice(body) {
  const { data } = await api.post('/v1/payment-notices/payless', body);
  return data;
}
