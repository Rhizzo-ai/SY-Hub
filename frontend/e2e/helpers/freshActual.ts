// frontend/e2e/helpers/freshActual.ts
//
// Chat 19B §R7.2 — Per-test factory: create a Draft / Posted actual against
// the already-seeded budget (v2 Active budget on the demo project).
//
// Same pattern as freshBudget.ts (chat-18 §R3).

import { test as base, expect, APIRequestContext } from '@playwright/test';
import { pmApi } from './api';
import { getProjectId, getBudgetIds } from './seed';

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

// Resolve the first budget line on the v2 budget for E2E factory use.
// Returns the full line object so callers have entity_id (and anything
// else they need) without a second round-trip.
export async function getDefaultBudgetLine(
  ctx: APIRequestContext, _projectId: string,
): Promise<{ id: string; entity_id: string }> {
  const { v2 } = getBudgetIds();
  const res = await ctx.get(`/api/v1/budgets/${v2}`);
  if (!res.ok()) {
    throw new Error(`getDefaultBudgetLine failed: ${await res.text()}`);
  }
  const budget = await res.json();
  if (!budget.lines || budget.lines.length === 0) {
    throw new Error(`v2 budget has no lines — seed must be re-run`);
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
