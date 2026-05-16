// frontend/e2e/actuals-permissions.readonly.spec.ts — Chat 19B §R7.3
//
// Readonly role: has actuals.view only — no create, no state transitions,
// no sensitive-payload viewing.
import { test, expect } from '@playwright/test';
import { pmApi, readonlyApi as _readonlyApi } from './helpers/api';
import { getProjectId } from './helpers/seed';
import { createPostedActual, getDefaultBudgetLine } from './helpers/freshActual';

let seededActualId: string;

test.beforeAll(async () => {
  // Seed one Posted actual for read-only viewing (PM creates; readonly observes).
  const ctx = await pmApi();
  const line = await getDefaultBudgetLine(ctx, getProjectId());
  const a = await createPostedActual(ctx, getProjectId(), line);
  seededActualId = a.id;
  await ctx.dispose();
});

test('readonly user sees list but no create button', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await expect(page.getByTestId('actuals-list-page')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('actuals-create-button')).toHaveCount(0);
});

test('readonly user sees no state-transition buttons on detail page', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${seededActualId}`);
  await expect(page.getByTestId('actual-detail-page')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('action-post')).toHaveCount(0);
  await expect(page.getByTestId('action-mark-paid')).toHaveCount(0);
  await expect(page.getByTestId('action-void')).toHaveCount(0);
  await expect(page.getByTestId('action-dispute')).toHaveCount(0);
});

test('readonly user: history payload section hidden (no actuals.view_sensitive)', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${seededActualId}`);
  await page.getByTestId('actual-history-toggle').click();
  // Events should still render — but the payload JSON tile must not.
  await expect(page.locator('[data-testid^="history-event-"]').first()).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[data-testid^="history-payload-"]')).toHaveCount(0);
});
