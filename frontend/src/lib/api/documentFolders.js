/**
 * Document folders API client — Build Pack 2.7-DOCS-FE §R3.1 (Chat 46, B79-FE).
 *
 * Mirrors `lib/api/supplierDocuments.js` conventions exactly (shared
 * axios `api` instance, JSON bodies, returns `data`). Wraps the folder
 * engine endpoints shipped Chat 45:
 *
 *   GET    /v1/document-folders                — tree (nested) for an owner
 *   GET    /v1/document-folders/{id}           — folder + immediate children
 *   POST   /v1/document-folders                — create
 *   PATCH  /v1/document-folders/{id}           — rename
 *   POST   /v1/document-folders/{id}/move      — move (new_parent_id, null=root)
 *   POST   /v1/document-folders/{id}/archive   — archive (blocks if non-empty)
 *   POST   /v1/document-folders/{id}/unarchive — unarchive (blocks if parent archived)
 *
 * Folder reads gate on the OWNER's view perm (e.g. supplier_documents.view
 * for supplier-owned folders) — handled server-side. Writes gate on the
 * platform-wide `documents.create`/`documents.edit`/`documents.move`
 * actions. The UI surfaces 403/404/422 via the existing toast pattern;
 * this module just speaks HTTP.
 */
import { api } from '@/lib/api';


/**
 * GET /v1/document-folders — full nested tree for an owner.
 *
 * `data.items` is the list of root nodes; each node has a `children[]`
 * array recursively. The backend builds the tree in one query (no N+1)
 * and includes per-folder `file_count` (DIRECT count, not recursive).
 */
export async function listFolderTree(ownerType, ownerId, { includeArchived, signal } = {}) {
  const { data } = await api.get('/v1/document-folders', {
    signal,
    params: {
      owner_type: ownerType,
      owner_id: ownerId,
      // Only forward the flag when truthy — matches the supplier-docs
      // convention so query-key cache identity stays stable.
      include_archived: includeArchived || undefined,
    },
  });
  return data.items;
}


/** GET /v1/document-folders/{id} — folder + immediate children + file_count. */
export async function getFolder(id, { signal } = {}) {
  const { data } = await api.get(`/v1/document-folders/${id}`, { signal });
  return data;
}


/** POST /v1/document-folders — body: {owner_type, owner_id, name, parent_id?}. */
export async function createFolder(body) {
  const { data } = await api.post('/v1/document-folders', body);
  return data;
}


/** PATCH /v1/document-folders/{id} — body: {name}. */
export async function renameFolder(id, name) {
  const { data } = await api.patch(`/v1/document-folders/${id}`, { name });
  return data;
}


/**
 * POST /v1/document-folders/{id}/move — body: {new_parent_id}.
 *
 * `newParentId === null` (or undefined) means "move to root". The
 * backend's loop-guard rejects self / descendant targets with 422.
 */
export async function moveFolder(id, newParentId) {
  const { data } = await api.post(
    `/v1/document-folders/${id}/move`,
    { new_parent_id: newParentId ?? null },
  );
  return data;
}


/** POST /v1/document-folders/{id}/archive — 422 when folder is non-empty. */
export async function archiveFolder(id) {
  const { data } = await api.post(`/v1/document-folders/${id}/archive`, {});
  return data;
}


/** POST /v1/document-folders/{id}/unarchive — 422 when parent is archived. */
export async function unarchiveFolder(id) {
  const { data } = await api.post(`/v1/document-folders/${id}/unarchive`, {});
  return data;
}
