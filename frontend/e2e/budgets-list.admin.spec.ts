// frontend/e2e/budgets-list.admin.spec.ts — BudgetsList #4 (.admin companion)
import { test, expect } from '@playwright/test';
import { getProjectId } from './helpers/seed';

test('refresh-attention button visible for super_admin', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets`);
  await expect(page.getByTestId('budgets-list-title')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('budgets-refresh-attention')).toBeVisible({ timeout: 10_000 });
});
