// frontend/e2e/auth.site.spec.ts — Auth #4 (no-perm gate) — site project
//
// test-site is site_manager which lacks `budgets.view`. The BudgetsList
// page renders the no-perm placeholder.
import { test, expect } from '@playwright/test';
import { getProjectId } from './helpers/seed';

test('site_manager hits no-perm placeholder on budgets list', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets`);
  await expect(page.getByTestId('budgets-list-no-perm')).toBeVisible({ timeout: 10_000 });
  // The create button must NOT render.
  await expect(page.getByTestId('budgets-create-button')).toHaveCount(0);
});
