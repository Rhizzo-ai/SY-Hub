/**
 * Packages API client — B88 Pack 3 (Chat 53, the tendering spine).
 *
 * Thin axios wrappers around the `/api/v1` packages endpoints. Mirrors
 * `lib/api/subcontracts.js` shape: shared `lib/api.js` baseURL is `/api`,
 * each path here is prefixed `/v1/...` ourselves. All functions return
 * the response body directly (`data`).
 *
 * Endpoint contract (verified against backend/app/routers/packages.py,
 * Gate 1 head=0047_packages):
 *
 *   POST   /v1/projects/{pid}/packages           → 201 + package
 *   GET    /v1/projects/{pid}/packages           → {items,total}
 *   GET    /v1/packages                          → {items,total}
 *   GET    /v1/packages/{id}                     → package
 *   PATCH  /v1/packages/{id}                     → updated package
 *   DELETE /v1/packages/{id}                     → 204
 *   POST   /v1/packages/{id}/lines               → 201 + package
 *   PATCH  /v1/packages/{id}/lines/{lid}         → updated package
 *   DELETE /v1/packages/{id}/lines/{lid}         → 204
 *   POST   /v1/packages/{id}/send-to-tender      → updated package
 *   POST   /v1/packages/{id}/cancel              → updated package
 *   POST   /v1/packages/{id}/bids                → 201 + package
 *   GET    /v1/packages/{id}/bids                → {items,total}
 *   POST   /v1/bids/{bid_id}/enter               → updated package
 *   POST   /v1/bids/{bid_id}/decline             → updated package
 *   POST   /v1/bids/{bid_id}/withdraw            → updated package
 *   POST   /v1/packages/{id}/award               → updated package
 *   POST   /v1/awards/{award_id}/cancel          → updated package
 *
 * Error mapping (mirrored in component error toasts):
 *   404 — not found / cross-tenant.
 *   409 — state error (e.g. award from non-tender, cancel a partially
 *         issued award). UI surfaces `detail` verbatim and refetches.
 *   422 — validation error (Σ-guard overage, per-line quantity exceed,
 *         labour-vs-Contractor mismatch). UI surfaces `detail` verbatim
 *         — NEVER paraphrase the server's money-math message.
 *   403 — missing permission.
 *
 * Sensitive pricing fields (`total_net`, `awarded_net`,
 * `budgeted_unit_rate`, `budgeted_net_amount`, bid `total_net` +
 * quoted_*, award `awarded_net` + awarded_*) come back as `null`
 * without `packages.view_sensitive`. UI redacts via em-dash.
 */
import { api } from '@/lib/api';

// ─── List + read ────────────────────────────────────────────────────

export async function listPackagesGlobal(
  { status, kind, limit, offset, signal } = {},
) {
  const params = {};
  if (status != null) params.status = status;
  if (kind != null) params.kind = kind;
  if (limit != null) params.limit = limit;
  if (offset != null) params.offset = offset;
  const { data } = await api.get('/v1/packages', { signal, params });
  return data;
}

export async function listPackagesForProject(
  projectId, { status, kind, limit, offset, signal } = {},
) {
  const params = {};
  if (status != null) params.status = status;
  if (kind != null) params.kind = kind;
  if (limit != null) params.limit = limit;
  if (offset != null) params.offset = offset;
  const { data } = await api.get(
    `/v1/projects/${projectId}/packages`, { signal, params },
  );
  return data;
}

export async function getPackage(packageId, { signal } = {}) {
  const { data } = await api.get(`/v1/packages/${packageId}`, { signal });
  return data;
}

// ─── Header CRUD ───────────────────────────────────────────────────

export async function createPackage(
  projectId, { budget_id, title, kind, description },
) {
  const body = { budget_id, title, kind };
  if (description != null) body.description = description;
  const { data } = await api.post(
    `/v1/projects/${projectId}/packages`, body,
  );
  return data;
}

export async function updatePackage(packageId, { title, description }) {
  const body = {};
  if (title !== undefined) body.title = title;
  if (description !== undefined) body.description = description;
  const { data } = await api.patch(`/v1/packages/${packageId}`, body);
  return data;
}

export async function deletePackage(packageId) {
  await api.delete(`/v1/packages/${packageId}`);
}

// ─── Lines ─────────────────────────────────────────────────────────

export async function addPackageLine(packageId, body) {
  // body: { budget_line_id, description?, quantity?, unit?,
  //         budgeted_unit_rate?, notes? } — strings for Decimal fidelity.
  const { data } = await api.post(
    `/v1/packages/${packageId}/lines`, body,
  );
  return data;
}

export async function updatePackageLine(packageId, lineId, body) {
  const { data } = await api.patch(
    `/v1/packages/${packageId}/lines/${lineId}`, body,
  );
  return data;
}

export async function removePackageLine(packageId, lineId) {
  await api.delete(`/v1/packages/${packageId}/lines/${lineId}`);
}

// ─── Tender ────────────────────────────────────────────────────────

export async function sendToTender(packageId) {
  const { data } = await api.post(
    `/v1/packages/${packageId}/send-to-tender`, {},
  );
  return data;
}

export async function cancelPackage(packageId, { reason } = {}) {
  const body = reason ? { reason } : {};
  const { data } = await api.post(
    `/v1/packages/${packageId}/cancel`, body,
  );
  return data;
}

// ─── Bids ──────────────────────────────────────────────────────────

export async function inviteBidder(packageId, { supplier_id }) {
  const { data } = await api.post(
    `/v1/packages/${packageId}/bids`, { supplier_id },
  );
  return data;
}

export async function listBids(packageId, { signal } = {}) {
  const { data } = await api.get(
    `/v1/packages/${packageId}/bids`, { signal },
  );
  return data;
}

export async function enterBid(bidId, { lines, notes }) {
  // lines: [{ package_line_id, quoted_unit_rate (string) }]
  const body = { lines };
  if (notes != null) body.notes = notes;
  const { data } = await api.post(`/v1/bids/${bidId}/enter`, body);
  return data;
}

export async function declineBid(bidId) {
  const { data } = await api.post(`/v1/bids/${bidId}/decline`, {});
  return data;
}

export async function withdrawBid(bidId) {
  const { data } = await api.post(`/v1/bids/${bidId}/withdraw`, {});
  return data;
}

// ─── Award engine ──────────────────────────────────────────────────

/**
 * Award one or more bidders. Multi-spec payload is atomic: either every
 * spec succeeds and creates its downstream PO/SC, or NONE persist.
 *
 * awards: [
 *   { supplier_id,
 *     source_bid_id (null = fast-track),
 *     lines: [{ package_line_id, quantity, awarded_unit_rate }],
 *     // optional downstream-create hints:
 *     required_by_date?, delivery_address?,
 *     scope_description?, retention_pct?, cis_applies? }
 * ]
 *
 * The CLIENT NEVER sends `net_amount`. The server recomputes
 * net = qty × rate and the Σ-guard verifies total ≤ package.total_net
 * + £0.01.
 */
export async function awardPackage(packageId, { awards }) {
  const { data } = await api.post(
    `/v1/packages/${packageId}/award`, { awards },
  );
  return data;
}

export async function cancelAward(awardId, { reason }) {
  const { data } = await api.post(
    `/v1/awards/${awardId}/cancel`, { reason },
  );
  return data;
}
