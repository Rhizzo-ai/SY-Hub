// frontend/e2e/helpers/freshActual.ts
//
// Chat 19B §R7.2 — Per-test factory: create a Draft / Posted actual against
// whatever Active/Locked+is_current budget exists on the demo project.
//
// Build-pack-shipped E7 deviation: the original factory hard-coded the v2
// budget ID from the seed state. But `lifecycle.admin.spec.ts` lifecycles v2
// through Draft→Active→Locked→Closed, leaving v2 in a terminal status and
// breaking subsequent actuals tests. The factory now queries the project for
// its current non-terminal budget and (if none exists) bootstraps one via
// `createActiveBudget`.

import { test as base, expect, APIRequestContext } from '@playwright/test';
import { pmApi } from './api';
import { createActiveBudget } from './factory';
import { getProjectId } from './seed';

export type FreshActual = {
  id: string;
  project_id: string;
  budget_line_id: string;
  status: string;
  gross_amount: string;
};

// Create a Draft actual against the first budget line of the current (v2)
// budget. Caller resolves the line up-front (see getDefaultBudgetLine).
export async function createDraftActual(
  ctx: APIRequestContext,
  projectId: string,
  budgetLine: { id: string; entity_id: string },
  overrides: Record<string, unknown> = {},
): Promise<FreshActual> {
  const body = {
    project_id: projectId,
    budget_line_id: budgetLine.id,
    entity_id: budgetLine.entity_id,
    source_type: 'Manual_Entry',
    transaction_date: new Date().toISOString().slice(0, 10),
    description: `E2E test bill ${Date.now()}`,
    net_amount: '1000.00',
    vat_amount: '200.00',
    vat_rate_pct: '20',
    is_vat_recoverable: true,
    currency: 'GBP',
    supplier_name_snapshot: 'E2E Test Supplier',
    ...overrides,
  };
  const res = await ctx.post('/api/v1/actuals', { data: body });
  if (!res.ok()) {
    throw new Error(
      `createDraftActual failed: ${res.status()} ${await res.text()}`,
    );
  }
  return res.json();
}

export async function postActual(
  ctx: APIRequestContext, actualId: string,
): Promise<FreshActual> {
  const res = await ctx.post(`/api/v1/actuals/${actualId}/post`, { data: {} });
  if (!res.ok()) {
    throw new Error(`postActual failed: ${res.status()} ${await res.text()}`);
  }
  return res.json();
}

export async function createPostedActual(
  ctx: APIRequestContext,
  projectId: string,
  budgetLine: { id: string; entity_id: string },
  overrides: Record<string, unknown> = {},
): Promise<FreshActual> {
  const draft = await createDraftActual(ctx, projectId, budgetLine, overrides);
  return postActual(ctx, draft.id);
}

// Resolve the first budget line on the current Active/Locked budget. If no
// such budget exists (e.g. lifecycle.admin closed v2), bootstrap a fresh
// Active budget via the chat-18 factory.
export async function getDefaultBudgetLine(
  ctx: APIRequestContext, projectId: string,
): Promise<{ id: string; entity_id: string }> {
  // 1. Look for a non-terminal current budget on the project.
  const listResp = await ctx.get(`/api/v1/projects/${projectId}/budgets`);
  if (!listResp.ok()) {
    throw new Error(`getDefaultBudgetLine list failed: ${listResp.status()}`);
  }
  const listBody = await listResp.json();
  const items = (listBody.items ?? []) as Array<{
    id: string; status: string; is_current: boolean;
  }>;
  let current =
    items.find((b) => b.is_current && (b.status === 'Active' || b.status === 'Locked')) ||
    items.find((b) => b.status === 'Active') ||
    items.find((b) => b.status === 'Locked');

  // 2. None? Bootstrap a fresh Active budget (chat-18 factory).
  if (!current) {
    const fresh = await createActiveBudget(ctx, projectId);
    current = { id: fresh.id, status: fresh.status, is_current: true };
  }

  // 3. Fetch detail to get the lines.
  const detailResp = await ctx.get(`/api/v1/budgets/${current.id}`);
  if (!detailResp.ok()) {
    throw new Error(`getDefaultBudgetLine detail failed: ${detailResp.status()}`);
  }
  const budget = await detailResp.json();
  if (!budget.lines || budget.lines.length === 0) {
    throw new Error(`Budget ${current.id} has no lines — seed must be re-run`);
  }
  const line = budget.lines[0];
  return { id: line.id, entity_id: line.entity_id };
}

// ─── Test fixture wrapper — supplies fresh Draft / Posted actuals ────
type Fixtures = {
  freshDraftActual: FreshActual;
  freshPostedActual: FreshActual;
};

export const test = base.extend<Fixtures>({
  // eslint-disable-next-line no-empty-pattern
  freshDraftActual: async ({}, use) => {
    const ctx = await pmApi();
    const projectId = getProjectId();
    const line = await getDefaultBudgetLine(ctx, projectId);
    const a = await createDraftActual(ctx, projectId, line);
    await ctx.dispose();
    await use(a);
  },
  // eslint-disable-next-line no-empty-pattern
  freshPostedActual: async ({}, use) => {
    const ctx = await pmApi();
    const projectId = getProjectId();
    const line = await getDefaultBudgetLine(ctx, projectId);
    const a = await createPostedActual(ctx, projectId, line);
    await ctx.dispose();
    await use(a);
  },
});

export { expect };
