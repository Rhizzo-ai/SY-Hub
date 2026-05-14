// frontend/e2e/lifecycle.admin.spec.ts — Lifecycle #1, #2, #3
import { test as base, expect } from '@playwright/test';
import { adminApi } from './helpers/api';
import { createFreshBudget } from './helpers/factory';
import { getProjectId } from './helpers/seed';

type Fix = { freshBudget: { id: string; status: string; version_number: number } };

const test = base.extend<Fix>({
  // eslint-disable-next-line no-empty-pattern
  freshBudget: async ({}, use) => {
    const ctx = await adminApi();
    const b = await createFreshBudget(ctx, getProjectId());
    await ctx.dispose();
    await use(b);
  },
});

test('@smoke full lifecycle Draft → Active → Locked → Closed', async ({ page, freshBudget: budget }) => {
  test.setTimeout(60_000);
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('lifecycle-actions')).toBeVisible({ timeout: 10_000 });

  // Draft → Active (immediate mutation, no ConfirmDialog).
  await expect(page.getByText('Draft')).toBeVisible();
  await page.getByTestId('lifecycle-activate').click();
  await expect(page.getByText('Active')).toBeVisible({ timeout: 10_000 });

  // Active → Locked (immediate mutation, no ConfirmDialog).
  await page.getByTestId('lifecycle-lock').click();
  await expect(page.getByText('Locked')).toBeVisible({ timeout: 10_000 });

  // Locked → Closed (requires reason via ConfirmDialog).
  await page.getByTestId('lifecycle-close').click();
  await page.getByTestId('lifecycle-close-dialog').waitFor();
  await page.getByTestId('lifecycle-close-dialog-reason-input').fill('e2e close reason');
  await page.getByTestId('lifecycle-close-dialog-confirm').click();
  await expect(page.getByText('Closed')).toBeVisible({ timeout: 10_000 });
});

test('new-version dialog — creates v[N+1] Draft', async ({ page, freshBudget: budget }) => {
  test.setTimeout(45_000);
  const projectId = getProjectId();
  // Promote to Active first (NewVersion is allowed from Active too).
  const ctx = await adminApi();
  const activateResp = await ctx.post(`/api/v1/budgets/${budget.id}/activate`, {
    data: { reason: 'e2e prep' },
  });
  if (!activateResp.ok()) throw new Error(`activate failed ${activateResp.status()}`);
  await ctx.dispose();

  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('lifecycle-newver')).toBeVisible({ timeout: 10_000 });
  await page.getByTestId('lifecycle-newver').click();
  await expect(page.getByTestId('lifecycle-newver-dialog')).toBeVisible();
  await page.getByTestId('lifecycle-newver-label-input').fill('e2e new version label');
  await page.getByTestId('lifecycle-newver-dialog-reason-input').fill('e2e new version reason');
  await page.getByTestId('lifecycle-newver-dialog-confirm').click();
  // URL navigates to the new budget; header re-renders.
  await expect(page.getByText('Draft')).toBeVisible({ timeout: 15_000 });
});

test('refresh-attention scan — admin can trigger the scan endpoint', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets`);
  await expect(page.getByTestId('budgets-refresh-attention')).toBeVisible({ timeout: 10_000 });
  await page.getByTestId('budgets-refresh-attention').click();
  // Click is a fire-and-forget POST; surface that no error toast appears.
  await expect(page.getByText(/error|failed/i)).toHaveCount(0, { timeout: 5_000 });
});
