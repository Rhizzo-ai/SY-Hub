/**
 * Budgets API client (Prompt 2.4B-i §R3.3).
 *
 * Wraps the 15 backend endpoints (14 from 2.4A + 1 reorder from 2.4A.1)
 * with Zod-validation on every response. Each function:
 *   - accepts a `signal` (AbortSignal) for queryFn cancellation
 *   - returns the parsed-and-validated payload (or throws on schema drift)
 *   - uses paths starting with `/v1/...` (errata E3: lib/api.js baseURL=`/api`)
 *
 * The flat path convention (errata E2) is reflected here:
 *   PATCH/DELETE on lines/items use /budget-lines/:l and /budget-line-items/:i
 *   directly — NOT nested under /budgets/:b/.
 *
 * On Zod failure we throw an Error that includes the issue path so
 * the caller can surface "backend schema drift" rather than a generic
 * runtime exception. ZodError details propagate to React Query's
 * `error` channel where they're toast-surfaced.
 */
import { api } from '@/lib/api';
import {
  BudgetDetailSchema,
  BudgetListResponseSchema,
} from '@/lib/schemas/budgets';

function parseOrThrow(schema, data, endpoint) {
  const result = schema.safeParse(data);
  if (!result.success) {
    const issues = result.error.issues
      .slice(0, 3)
      .map((i) => `${i.path.join('.') || '<root>'}: ${i.message}`)
      .join('; ');
    const err = new Error(`Schema drift @ ${endpoint}: ${issues}`);
    err.zodIssues = result.error.issues;
    err.endpoint = endpoint;
    throw err;
  }
  return result.data;
}

// ──────────────────────────────────────────────────────────────────────
// Endpoint 1 — list budgets for a project
// ──────────────────────────────────────────────────────────────────────
export async function listProjectBudgets(projectId, { signal, params } = {}) {
  const { data } = await api.get(`/v1/projects/${projectId}/budgets`, {
    signal, params,
  });
  return parseOrThrow(
    BudgetListResponseSchema, data, 'GET /projects/:id/budgets',
  );
}

// ──────────────────────────────────────────────────────────────────────
// Endpoint 2 — get a single budget with lines + items
// ──────────────────────────────────────────────────────────────────────
export async function getBudget(budgetId, { signal } = {}) {
  const { data } = await api.get(`/v1/budgets/${budgetId}`, { signal });
  return parseOrThrow(BudgetDetailSchema, data, 'GET /budgets/:id');
}

// ──────────────────────────────────────────────────────────────────────
// Endpoint 3 — create budget from approved appraisal
// ──────────────────────────────────────────────────────────────────────
export async function createBudgetFromAppraisal(projectId, body) {
  const { data } = await api.post(
    `/v1/projects/${projectId}/budgets/from-appraisal`,
    body,
  );
  return parseOrThrow(
    BudgetDetailSchema, data, 'POST /projects/:id/budgets/from-appraisal',
  );
}

// ──────────────────────────────────────────────────────────────────────
// Endpoints 4–7 — lifecycle transitions
// All four share the same shape: POST with optional body, return refreshed
// budget detail.
// ──────────────────────────────────────────────────────────────────────
function lifecycle(action) {
  return async function fn(budgetId, body) {
    const { data } = await api.post(
      `/v1/budgets/${budgetId}/${action}`, body ?? {},
    );
    return parseOrThrow(
      BudgetDetailSchema, data, `POST /budgets/:id/${action}`,
    );
  };
}
export const activateBudget = lifecycle('activate');
export const lockBudget     = lifecycle('lock');
export const unlockBudget   = lifecycle('unlock');
export const closeBudget    = lifecycle('close');

// ──────────────────────────────────────────────────────────────────────
// Endpoint 8 — new version (clones, supersedes the current)
// ──────────────────────────────────────────────────────────────────────
export async function createNewBudgetVersion(budgetId, body) {
  const { data } = await api.post(
    `/v1/budgets/${budgetId}/new-version`, body,
  );
  return parseOrThrow(
    BudgetDetailSchema, data, 'POST /budgets/:id/new-version',
  );
}

// ──────────────────────────────────────────────────────────────────────
// Endpoint 9 — patch a budget line
// Flat path: PATCH /budget-lines/:lineId (errata E2). Backend returns a
// bare line object; callers usually invalidate the parent budget query
// instead of consuming the response directly.
// ──────────────────────────────────────────────────────────────────────
export async function patchBudgetLine(lineId, body) {
  const { data } = await api.patch(`/v1/budget-lines/${lineId}`, body);
  return data;  // line shape verified at hook layer (parent query refetch)
}

// ──────────────────────────────────────────────────────────────────────
// Endpoint 9b (2.4A.1) — bulk reorder lines
// Flat path: POST /budget-lines/reorder. Returns refreshed budget detail.
// ──────────────────────────────────────────────────────────────────────
export async function reorderBudgetLines(body) {
  const { data } = await api.post('/v1/budget-lines/reorder', body);
  return parseOrThrow(
    BudgetDetailSchema, data, 'POST /budget-lines/reorder',
  );
}

// ──────────────────────────────────────────────────────────────────────
// Endpoints 10–13 — line items (flat paths via errata E2)
// ──────────────────────────────────────────────────────────────────────
export async function listLineItems(lineId, { signal } = {}) {
  const { data } = await api.get(`/v1/budget-lines/${lineId}/items`, {
    signal,
  });
  // Wire shape: bare array of items (backend doesn't wrap with {items: [...]})
  return Array.isArray(data) ? data : (data?.items ?? []);
}

export async function createLineItem(lineId, body) {
  const { data } = await api.post(`/v1/budget-lines/${lineId}/items`, body);
  return data;
}

export async function patchLineItem(itemId, body) {
  const { data } = await api.patch(`/v1/budget-line-items/${itemId}`, body);
  return data;
}

export async function deleteLineItem(itemId) {
  await api.delete(`/v1/budget-line-items/${itemId}`);
}

// ──────────────────────────────────────────────────────────────────────
// Endpoint 14 — internal: refresh attention flags (admin only)
// ──────────────────────────────────────────────────────────────────────
export async function refreshAttention() {
  const { data } = await api.post('/v1/internal/budgets/refresh-attention');
  return data;
}
