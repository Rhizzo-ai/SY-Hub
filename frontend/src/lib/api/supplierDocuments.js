/**
 * Supplier-documents API client — Chat 40 §R3 #9.
 *
 * Endpoints (verified on origin/main, §R0 coverage map):
 *   GET    /v1/supplier-documents?supplier_id=&include_archived=
 *   POST   /v1/supplier-documents
 *   PATCH  /v1/supplier-documents/{id}
 *   POST   /v1/supplier-documents/{id}/archive
 *   POST   /v1/supplier-documents/{id}/unarchive
 *
 * GET single (`/v1/supplier-documents/{id}`) intentionally NOT surfaced
 * (§R0: list already returns full rows; edit uses the cached row).
 *
 * Backend strips `file_ref` + `notes` for callers without
 * `supplier_documents.view_sensitive`.
 */
import { api } from '@/lib/api';

export async function listDocuments(supplierId, { signal, includeArchived } = {}) {
  const { data } = await api.get('/v1/supplier-documents', {
    signal,
    params: {
      supplier_id: supplierId,
      include_archived: includeArchived || undefined,
    },
  });
  return data;
}

export async function createDocument(body) {
  const { data } = await api.post('/v1/supplier-documents', body);
  return data;
}

export async function patchDocument(id, body) {
  const { data } = await api.patch(`/v1/supplier-documents/${id}`, body);
  return data;
}

export async function archiveDocument(id) {
  const { data } = await api.post(`/v1/supplier-documents/${id}/archive`, {});
  return data;
}

export async function unarchiveDocument(id) {
  const { data } = await api.post(`/v1/supplier-documents/${id}/unarchive`, {});
  return data;
}
