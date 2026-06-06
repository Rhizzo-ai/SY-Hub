// frontend/e2e/helpers/api.ts
//
// Authenticated API contexts + small typed wrappers used by tests
// that bypass the UI (e.g. factory + background PATCH for E9 conflict).

import { request, APIRequestContext } from '@playwright/test';
import { authenticator } from 'otplib';
import * as path from 'path';

const PREVIEW_URL =
  process.env.REACT_APP_PREVIEW_URL
  || process.env.REACT_APP_BACKEND_URL
  || 'https://auth-verify-preview.preview.emergentagent.com';

const PASSWORD = process.env.TEST_USER_PASSWORD || 'TestUser-Dev-2026!';

const AUTH_DIR = path.resolve(__dirname, '../../playwright/.auth');

/** Build a request context backed by the pm storageState. */
export async function pmApi(): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: PREVIEW_URL,
    storageState: path.join(AUTH_DIR, 'pm.json'),
  });
}

/** Build a request context backed by the admin storageState. */
export async function adminApi(): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: PREVIEW_URL,
    storageState: path.join(AUTH_DIR, 'admin.json'),
  });
}

/**
 * Build an admin-authenticated context fresh (no storageState reuse).
 * Used when storageState may be stale (e.g. >15 min into a debug session).
 */
export async function adminApiFresh(): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL: PREVIEW_URL });
  const loginResp = await ctx.post('/api/auth/login', {
    data: { email: 'test-admin@example.test', password: PASSWORD, remember_me: false },
  });
  if (!loginResp.ok()) {
    throw new Error(`adminApiFresh: login failed ${loginResp.status()}`);
  }
  const body = await loginResp.json();
  if (body.mfa_enrollment_required) {
    const startResp = await ctx.post('/api/auth/mfa/enroll/start');
    const { secret } = await startResp.json();
    await ctx.post('/api/auth/mfa/enroll/confirm', {
      data: { secret, code: authenticator.generate(secret) },
    });
  }
  return ctx;
}

export async function patchBudgetLine(
  ctx: APIRequestContext,
  lineId: string,
  patch: Record<string, unknown>,
): Promise<void> {
  const r = await ctx.patch(`/api/v1/budget-lines/${lineId}`, { data: patch });
  if (!r.ok()) {
    throw new Error(`patchBudgetLine ${lineId} failed ${r.status()}: ${await r.text()}`);
  }
}

export async function activateBudget(ctx: APIRequestContext, budgetId: string): Promise<void> {
  const r = await ctx.post(`/api/v1/budgets/${budgetId}/activate`, {
    data: { reason: 'e2e factory activate' },
  });
  if (!r.ok()) {
    throw new Error(`activateBudget ${budgetId} failed ${r.status()}: ${await r.text()}`);
  }
}

export async function lockBudget(ctx: APIRequestContext, budgetId: string): Promise<void> {
  const r = await ctx.post(`/api/v1/budgets/${budgetId}/lock`, {
    data: { reason: 'e2e factory lock' },
  });
  if (!r.ok()) {
    throw new Error(`lockBudget ${budgetId} failed ${r.status()}: ${await r.text()}`);
  }
}

// ─── Chat 19B §R7.4 — readonly + site role API contexts ──────────────
export async function readonlyApi(): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: PREVIEW_URL,
    storageState: path.join(AUTH_DIR, 'readonly.json'),
  });
}

export async function siteApi(): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: PREVIEW_URL,
    storageState: path.join(AUTH_DIR, 'site.json'),
  });
}
