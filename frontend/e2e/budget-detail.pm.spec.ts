// frontend/e2e/budget-detail.pm.spec.ts — BudgetDetail #1, #2, #4
import { test, expect } from '@playwright/test';
import { getProjectId, getBudgetIds } from './helpers/seed';

test('@smoke header tiles render with non-empty values on v2', async ({ page }) => {
  const projectId = getProjectId();
  const { v2 } = getBudgetIds();
  await page.goto(`/projects/${projectId}/budgets/${v2}`);
  await expect(page.getByTestId('budget-header')).toBeVisible({ timeout: 10_000 });
  for (const k of [
    'total_budget', 'total_actuals', 'total_committed_not_invoiced',
    'total_forecast_to_complete', 'forecast_final_cost',
  ]) {
    const tile = page.getByTestId(`budget-tile-${k}`);
    await expect(tile).toBeVisible();
    const txt = (await tile.textContent())?.trim() ?? '';
    expect(txt.length).toBeGreaterThan(0);
  }
});

test('lineage breadcrumb — v2 shows prev link to v1', async ({ page }) => {
  const projectId = getProjectId();
  const { v2 } = getBudgetIds();
  await page.goto(`/projects/${projectId}/budgets/${v2}`);
  await expect(page.getByTestId('budget-lineage')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('budget-lineage-prev')).toBeVisible();
});

test('deep link — direct nav to a budget ID renders the detail page', async ({ page }) => {
  const projectId = getProjectId();
  const { v1 } = getBudgetIds();
  await page.goto(`/projects/${projectId}/budgets/${v1}`);
  await expect(page.getByTestId('budget-header')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('budget-header-title')).toBeVisible();
});
