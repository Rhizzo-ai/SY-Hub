/**
 * Project Number Prefixes API client — Chat 24 §R5 (Prompt 2.5).
 *
 * Manages the per-project, per-document-type (PO / Bill) prefix rows
 * that drive sequential numbering in R2/R3. The Numbering Manager page
 * lets a tenant admin configure suffix / middle / next_sequence.
 */
import { api } from '@/lib/api';

export async function listPrefixes(projectId, { signal, params } = {}) {
  const { data } = await api.get(
    `/v1/projects/${projectId}/number-prefixes`,
    { signal, params },
  );
  return data;
}

export async function createPrefix(projectId, body) {
  const { data } = await api.post(
    `/v1/projects/${projectId}/number-prefixes`, body,
  );
  return data;
}

export async function patchPrefix(prefixId, body) {
  const { data } = await api.patch(
    `/v1/number-prefixes/${prefixId}`, body,
  );
  return data;
}

export async function deletePrefix(prefixId) {
  await api.delete(`/v1/number-prefixes/${prefixId}`);
}
