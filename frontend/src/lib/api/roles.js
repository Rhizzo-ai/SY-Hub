/**
 * Roles & Permissions API client — B83 (Chat 52).
 *
 * IMPORTANT: roles/permissions routers mount on the bare `/api` router in
 * backend/server.py — NOT under `/v1`. `lib/api.js` baseURL is already
 * `/api`, so paths here are `/roles...` and `/permissions` with NO `/v1`
 * prefix (unlike suppliers/budgets clients).
 *
 * Mutations (B83):
 *  - saveRolePermissionsBatch: ONE transactional call for the whole draft.
 *  - create/patch/deleteRole: custom-role lifecycle (system roles are
 *    locked server-side: 409s surface verbatim to the operator).
 */
import { api } from '@/lib/api';

export async function listRoles({ signal } = {}) {
  const { data } = await api.get('/roles', { signal });
  return data;
}

export async function getRole(roleId, { signal } = {}) {
  const { data } = await api.get(`/roles/${roleId}`, { signal });
  return data;
}

export async function listPermissions({ signal } = {}) {
  const { data } = await api.get('/permissions', { signal });
  return data;
}

/**
 * changes: [{ role_id, add: [codes], remove: [codes] }]
 * Returns { updated: [RoleDetail, ...] } — reconcile state from this.
 */
export async function saveRolePermissionsBatch(changes) {
  const { data } = await api.post('/roles/permissions-batch', { changes });
  return data;
}

export async function createRole(body) {
  const { data } = await api.post('/roles', body);
  return data;
}

export async function patchRole(roleId, body) {
  const { data } = await api.patch(`/roles/${roleId}`, body);
  return data;
}

export async function deleteRole(roleId) {
  await api.delete(`/roles/${roleId}`);
}
