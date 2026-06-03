/**
 * CIS verifications API client — Chat 40 §R3 #8.
 *
 * Endpoints (verified on origin/main, §R0 coverage map):
 *   GET  /v1/cis/verifications?supplier_id=        — list
 *   GET  /v1/cis/verifications/current?supplier_id= — current status
 *   POST /v1/cis/verifications                      — record one
 *
 * Backend strips `verification_number` for callers without
 * `cis.view_sensitive` on GET; POST 201 returns it regardless (actor
 * sees own write).
 */
import { api } from '@/lib/api';

export async function listVerifications(supplierId, { signal } = {}) {
  const { data } = await api.get('/v1/cis/verifications', {
    signal, params: { supplier_id: supplierId },
  });
  return data;
}

export async function getCurrentVerification(supplierId, { signal } = {}) {
  const { data } = await api.get('/v1/cis/verifications/current', {
    signal, params: { supplier_id: supplierId },
  });
  return data;
}

export async function createVerification(body) {
  const { data } = await api.post('/v1/cis/verifications', body);
  return data;
}
