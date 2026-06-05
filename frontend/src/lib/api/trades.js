/**
 * Trades API client — Chat 41 §R1.1 (Build Pack 2.7-FE-revision).
 *
 * Mirrors the lib/api/suppliers.js conventions (axios `api` from
 * `@/lib/api`, baseURL `/api`, so we prefix `/v1/...` ourselves).
 *
 * Backend contract (rev-A, verified):
 *   - GET  /api/v1/trades                → {items,total,limit,offset}
 *                                          params: q, include_archived,
 *                                                  limit, offset.
 *                                          perm: trades.view.
 *   - POST /api/v1/trades { name }       → 201 trade row (idempotent
 *                                          get-or-create, case-insensitive).
 *                                          perm: trades.create.
 *
 * Archive/unarchive endpoints exist server-side (perm trades.create) but
 * are not consumed by this prompt's UI — list is view + create only.
 */
import { api } from '@/lib/api';

export async function listTrades({ signal, params } = {}) {
  const { data } = await api.get('/v1/trades', { signal, params });
  return data;
}

export async function createTrade(name) {
  const { data } = await api.post('/v1/trades', { name });
  return data;
}
