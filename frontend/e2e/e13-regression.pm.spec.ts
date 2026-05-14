// frontend/e2e/e13-regression.pm.spec.ts — E13 #1
import { test, expect } from './helpers/freshBudget';
import { getProjectId } from './helpers/seed';

test('E13 regression — fresh budget FTC defaults give FFC = total_budget, variance Green', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-header')).toBeVisible({ timeout: 10_000 });

  const totalBudget = (await page.getByTestId('budget-tile-total_budget').textContent())?.trim();
  const ffc = (await page.getByTestId('budget-tile-forecast_final_cost').textContent())?.trim();
  expect(totalBudget).toEqual(ffc);
  expect(totalBudget?.length ?? 0).toBeGreaterThan(0);
  expect(totalBudget).not.toContain('—');

  await expect(page.getByTestId('variance-badge-Green')).toBeVisible();
  await expect(page.getByTestId('variance-badge-Red')).toHaveCount(0);
});
