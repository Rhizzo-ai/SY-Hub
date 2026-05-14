// frontend/e2e/budgets-list.pm.spec.ts — BudgetsList #1, #2, #3, #4 (.pm)
import { test, expect } from '@playwright/test';
import { getProjectId, getEmptyProjectId } from './helpers/seed';

test('empty state — empty project renders budgets-table-empty', async ({ page }) => {
  const projectId = getEmptyProjectId();
  await page.goto(`/projects/${projectId}/budgets`);
  await expect(page.getByTestId('budgets-list-title')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('budgets-table-empty')).toBeVisible();
});

test('@smoke populated state — table renders at least 1 budget row', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets`);
  await expect(page.getByTestId('budgets-list-title')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('budgets-table')).toBeVisible();
  const rows = page.locator('[data-testid^="budget-row-"]');
  await expect(rows.first()).toBeVisible({ timeout: 10_000 });
});

test('create-from-appraisal dialog — opens with the un-linked Approved appraisal selectable', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets`);
  await expect(page.getByTestId('budgets-create-button')).toBeVisible({ timeout: 10_000 });
  await page.getByTestId('budgets-create-button').click();
  await expect(page.getByTestId('create-budget-dialog')).toBeVisible();
  // The un-linked extra appraisal name pattern set by the seeder.
  await expect(page.getByText(/Demo Appraisal( v1| extra-)/)).toBeVisible({ timeout: 10_000 });
});

test('refresh-attention button hidden for project_manager role', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets`);
  await expect(page.getByTestId('budgets-list-title')).toBeVisible({ timeout: 10_000 });
  // budgets-refresh-attention requires budgets.admin (super_admin only).
  await expect(page.getByTestId('budgets-refresh-attention')).toHaveCount(0);
});
