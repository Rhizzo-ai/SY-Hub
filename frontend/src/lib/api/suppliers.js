/**
 * Suppliers API client — Chat 24 §R5 (Prompt 2.5).
 *
 * Thin axios wrappers around the v1 suppliers endpoints. Same shape
 * convention as lib/api/actuals.js: `lib/api.js` baseURL is `/api`, so
 * we prepend `/v1/...` ourselves.
 *
 * Sensitive fields (bank_account_number, bank_sort_code, vat_number)
 * are stripped server-side for callers without `suppliers.view_sensitive`.
 * Frontend renders an em-dash placeholder via <SensitiveValue/> when the
 * field comes back null.
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

export async function restoreSupplier(supplierId) {
  const { data } = await api.post(`/v1/suppliers/${supplierId}/restore`, {});
  return data;
}
