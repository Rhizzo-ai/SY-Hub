/**
 * Purchase Orders API client — Chat 24 §R5 (Prompt 2.5).
 *
 * Mirrors the actuals.js shape: `lib/api.js` baseURL is `/api`, so all
 * calls prepend `/v1/...`. Endpoints are scoped under a project for
 * list+create, then under the PO id for detail / lifecycle transitions.
 *
 * Lifecycle: draft -> submitted -> issued -> partially_receipted ->
 * receipted -> closed. Approve / reject / void / unlock are separate
 * verb endpoints.
 *
 * Sensitive fields (line totals, unit rates, supplier banking) are
 * stripped server-side for callers without `pos.view_sensitive`. Render
 * an em-dash placeholder via <SensitiveValue/> when null comes back.
 */
import { api } from '@/lib/api';

// ─── List + read ────────────────────────────────────────────────────
export async function listProjectPOs(projectId, { signal, params } = {}) {
  const { data } = await api.get(
    `/v1/projects/${projectId}/purchase-orders`,
    { signal, params },
  );
  return data;
}

// ─── R5.5 — Budget-line / budget scoped PO lists ────────────────────
// Used by the R6 inline expandable budget-line grid. Each call hits
// the exact path the Jest URL-contract pins assert on.
export async function listBudgetLinePOs(lineId, { signal, params } = {}) {
  const { data } = await api.get(
    `/v1/budget-lines/${lineId}/purchase-orders`,
    { signal, params },
  );
  return data;
}

export async function listBudgetPOs(budgetId, { signal, params } = {}) {
  const { data } = await api.get(
    `/v1/budgets/${budgetId}/purchase-orders`,
    { signal, params },
  );
  return data;
}

export async function getPO(poId, { signal } = {}) {
  const { data } = await api.get(`/v1/purchase-orders/${poId}`, { signal });
  return data;
}

// ─── Create + edit ──────────────────────────────────────────────────
export async function createPO(projectId, body) {
  const { data } = await api.post(
    `/v1/projects/${projectId}/purchase-orders`, body,
  );
  return data;
}

export async function patchPO(poId, body) {
  const { data } = await api.patch(`/v1/purchase-orders/${poId}`, body);
  return data;
}

export async function deletePO(poId) {
  await api.delete(`/v1/purchase-orders/${poId}`);
}

// ─── Lifecycle transitions ──────────────────────────────────────────
export async function submitPO(poId) {
  const { data } = await api.post(`/v1/purchase-orders/${poId}/submit`, {});
  return data;
}

export async function approvePO(poId, body = {}) {
  const { data } = await api.post(`/v1/purchase-orders/${poId}/approve`, body);
  return data;
}

export async function rejectPO(poId, body) {
  const { data } = await api.post(`/v1/purchase-orders/${poId}/reject`, body);
  return data;
}

export async function issuePO(poId) {
  const { data } = await api.post(`/v1/purchase-orders/${poId}/issue`, {});
  return data;
}

export async function voidPO(poId, body = {}) {
  const { data } = await api.post(`/v1/purchase-orders/${poId}/void`, body);
  return data;
}

export async function closePO(poId) {
  const { data } = await api.post(`/v1/purchase-orders/${poId}/close`, {});
  return data;
}

// ─── Receipts (R4) ──────────────────────────────────────────────────
export async function listReceipts(poId, { signal } = {}) {
  const { data } = await api.get(
    `/v1/purchase-orders/${poId}/receipts`, { signal },
  );
  return data;
}

export async function createReceipt(poId, body) {
  const { data } = await api.post(
    `/v1/purchase-orders/${poId}/receipts`, body,
  );
  return data;
}

export async function patchReceipt(receiptId, body) {
  const { data } = await api.patch(`/v1/receipts/${receiptId}`, body);
  return data;
}

export async function deleteReceipt(receiptId) {
  await api.delete(`/v1/receipts/${receiptId}`);
}
