/**
 * Suppliers API client — Chat 24 §R5 (Prompt 2.5) · Chat 40 §R2 D4 fix.
 *
 * Thin axios wrappers around the v1 suppliers endpoints. Same shape
 * convention as lib/api/actuals.js: `lib/api.js` baseURL is `/api`, so
 * we prepend `/v1/...` ourselves.
 *
 * Sensitive fields (bank_account_no, bank_sort_code, bank_name,
 * vat_number, company_number, utr) are stripped server-side for
 * callers without `suppliers.view_sensitive`. Frontend renders an
 * em-dash placeholder via <SensitiveValue/> when the field comes back
 * null.
 *
 * §R2 D4 — `restoreSupplier`→`unarchiveSupplier`, route `/restore`→`/unarchive`
 * (backend mounts `/v1/suppliers/{id}/unarchive`; the 2.5 client wrote
 * `/restore` which silently 404'd).
 */
import { api } from '@/lib/api';

export async function listSuppliers({ signal, params } = {}) {
  const { data } = await api.get('/v1/suppliers', { signal, params });
  return data;
}

export async function getSupplier(supplierId, { signal } = {}) {
  const { data } = await api.get(`/v1/suppliers/${supplierId}`, { signal });
  return data;
}

export async function createSupplier(body) {
  const { data } = await api.post('/v1/suppliers', body);
  return data;
}

export async function patchSupplier(supplierId, body) {
  const { data } = await api.patch(`/v1/suppliers/${supplierId}`, body);
  return data;
}

export async function archiveSupplier(supplierId) {
  const { data } = await api.post(`/v1/suppliers/${supplierId}/archive`, {});
  return data;
}

export async function unarchiveSupplier(supplierId) {
  const { data } = await api.post(`/v1/suppliers/${supplierId}/unarchive`, {});
  return data;
}
