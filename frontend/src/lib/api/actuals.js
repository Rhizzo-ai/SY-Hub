/**
 * Actuals API client (Chat 19B §R1.2).
 *
 * Thin axios wrappers around the 15 backend endpoints. Mirrors the
 * budgets.js pattern (chat-17 E3 — `lib/api.js` baseURL is `/api`, so
 * callers prepend `/v1/...` themselves).
 */
import { api } from '@/lib/api';

// ─── List ─────────────────────────────────────────────────────────────
export async function listActuals({ signal, params } = {}) {
  const { data } = await api.get('/v1/actuals', { signal, params });
  return data;
}

export async function listProjectActuals(projectId, { signal, params } = {}) {
  const { data } = await api.get(
    `/v1/projects/${projectId}/actuals`,
    { signal, params },
  );
  return data;
}

// ─── CRUD ─────────────────────────────────────────────────────────────
export async function createActual(body) {
  const { data } = await api.post('/v1/actuals', body);
  return data;
}

export async function getActual(actualId, { signal } = {}) {
  const { data } = await api.get(`/v1/actuals/${actualId}`, { signal });
  return data;
}

export async function patchActual(actualId, body) {
  const { data } = await api.patch(`/v1/actuals/${actualId}`, body);
  return data;
}

export async function deleteActual(actualId) {
  await api.delete(`/v1/actuals/${actualId}`);
}

export async function getChangeLog(actualId, { signal } = {}) {
  const { data } = await api.get(
    `/v1/actuals/${actualId}/change-log`,
    { signal },
  );
  return data;
}

// ─── State transitions ────────────────────────────────────────────────
export async function postActual(actualId, body = {}) {
  const { data } = await api.post(`/v1/actuals/${actualId}/post`, body);
  return data;
}

export async function markPaid(actualId, body) {
  const { data } = await api.post(`/v1/actuals/${actualId}/mark-paid`, body);
  return data;
}

export async function voidActual(actualId, body) {
  const { data } = await api.post(`/v1/actuals/${actualId}/void`, body);
  return data;
}

export async function disputeActual(actualId, body) {
  const { data } = await api.post(`/v1/actuals/${actualId}/dispute`, body);
  return data;
}

export async function undisputeActual(actualId, body) {
  const { data } = await api.post(`/v1/actuals/${actualId}/undispute`, body);
  return data;
}

export async function releaseRetention(actualId, body) {
  const { data } = await api.post(
    `/v1/actuals/${actualId}/release-retention`, body,
  );
  return data;
}

// ─── Attachments ──────────────────────────────────────────────────────
export async function listAttachments(actualId, { signal } = {}) {
  const { data } = await api.get(
    `/v1/actuals/${actualId}/attachments`,
    { signal },
  );
  // Backend may return either {items: [...]} or [...]; normalise.
  return Array.isArray(data) ? data : (data?.items ?? []);
}

export async function uploadAttachment(actualId, file) {
  const form = new FormData();
  form.append('file', file);
  // Do NOT set Content-Type. Axios derives `multipart/form-data; boundary=...`
  // from FormData automatically. Setting the header manually drops the
  // boundary suffix → backend rejects with 415 / "missing boundary".
  const { data } = await api.post(
    `/v1/actuals/${actualId}/attachments`,
    form,
  );
  return data;
}

export async function deleteAttachment(actualId, attachmentId) {
  await api.delete(`/v1/actuals/${actualId}/attachments/${attachmentId}`);
}
