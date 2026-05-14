// frontend/e2e/helpers/freshBudget.ts
//
// Playwright fixture wrapper that supplies a per-test fresh Draft (or
// Active / Locked) budget. Drops the UI overhead of CreateFromAppraisal
// + saves ~3s/test (API POST vs UI dialog).
//
// Usage:
//   import { test, expect } from './helpers/freshBudget';
//   test('foo', async ({ page, freshBudget }) => { ... });

import { test as base, expect } from '@playwright/test';
import { pmApi } from './api';
import { createFreshBudget, createActiveBudget, createLockedBudget, FreshBudget } from './factory';
import { getProjectId } from './seed';

type Fixtures = {
  freshBudget: FreshBudget;
  freshActiveBudget: FreshBudget;
  freshLockedBudget: FreshBudget;
};

export const test = base.extend<Fixtures>({
  // eslint-disable-next-line no-empty-pattern
  freshBudget: async ({}, use) => {
    const ctx = await pmApi();
    const b = await createFreshBudget(ctx, getProjectId());
    await ctx.dispose();
    await use(b);
  },
  // eslint-disable-next-line no-empty-pattern
  freshActiveBudget: async ({}, use) => {
    const ctx = await pmApi();
    const b = await createActiveBudget(ctx, getProjectId());
    await ctx.dispose();
    await use(b);
  },
  // eslint-disable-next-line no-empty-pattern
  freshLockedBudget: async ({}, use) => {
    const ctx = await pmApi();
    const b = await createLockedBudget(ctx, getProjectId());
    await ctx.dispose();
    await use(b);
  },
});

export { expect };
