/**
 * User preferences API client — Chat 23 R1.4 backend.
 *
 * Routes mount under /api/v1/me/preferences/{surface_key}. The
 * `api` axios base is `/api`, so callers add the `/v1/...` prefix.
 *
 * Endpoint matrix (6):
 *   GET    /me/preferences/{surface}                 snapshot
 *   PUT    /me/preferences/{surface}                 autosave current
 *   GET    /me/preferences/{surface}/views/{name}    read view
 *   POST   /me/preferences/{surface}/views           create view
 *   PUT    /me/preferences/{surface}/views/{name}    overwrite view
 *   DELETE /me/preferences/{surface}/views/{name}    delete view
 */
import { api } from '@/lib/api';

export async function getSurfaceSnapshot(surfaceKey, { signal } = {}) {
  const { data } = await api.get(
    `/v1/me/preferences/${encodeURIComponent(surfaceKey)}`,
    { signal },
  );
  return data;
}

export async function putCurrentPreference(surfaceKey, payload) {
  const { data } = await api.put(
    `/v1/me/preferences/${encodeURIComponent(surfaceKey)}`,
    { payload },
  );
  return data;
}

export async function createSavedView(surfaceKey, { name, payload }) {
  const { data } = await api.post(
    `/v1/me/preferences/${encodeURIComponent(surfaceKey)}/views`,
    { name, payload },
  );
  return data;
}

export async function updateSavedView(surfaceKey, name, payload) {
  const { data } = await api.put(
    `/v1/me/preferences/${encodeURIComponent(surfaceKey)}/views/${encodeURIComponent(name)}`,
    { payload },
  );
  return data;
}

export async function deleteSavedView(surfaceKey, name) {
  await api.delete(
    `/v1/me/preferences/${encodeURIComponent(surfaceKey)}/views/${encodeURIComponent(name)}`,
  );
}
