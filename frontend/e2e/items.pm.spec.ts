// frontend/e2e/items.pm.spec.ts — Items #1, #2, #3, #4
import { test, expect } from './helpers/freshBudget';
import { getProjectId } from './helpers/seed';

test('add new item — fill add-row, submit, computed amount = qty × rate', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  // Open drawer on line 2 (Superstructure — 0 items per seed).
  await page.locator('[data-testid^="budget-line-menu-"]').nth(1).click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').nth(1).click();
  await expect(page.getByTestId('line-items-panel')).toBeVisible();
  await expect(page.getByTestId('line-items-empty')).toBeVisible();

  await page.getByTestId('line-items-add-desc').fill('E2E test item');
  await page.getByTestId('line-items-add-qty').fill('5');
  await page.getByTestId('line-items-add-unit').fill('m2');
  await page.getByTestId('line-items-add-rate').fill('120');
  await page.getByTestId('line-items-add-button').click();

  await expect(page.getByTestId('line-items-empty')).toHaveCount(0);
  await expect(page.locator('[data-testid^="line-item-row-"]')).toHaveCount(1, { timeout: 10_000 });
  await expect(page.locator('[data-testid^="line-item-amount-"]').first()).toContainText('£600');
});

test('edit qty — blur fires PATCH, persists across reload', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  // Line 1 (Substructure) has 2 seeded items.
  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();

  const firstQty = page.locator('[data-testid^="line-item-qty-"]').first();
  await firstQty.click();
  await firstQty.fill('999');
  await firstQty.blur();

  await page.waitForTimeout(1_000);
  await page.reload();
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();
  await expect(page.locator('[data-testid^="line-item-qty-"]').first()).toHaveValue('999');
});

test('delete item — ConfirmDialog gates destructive action', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();

  const itemsBefore = await page.locator('[data-testid^="line-item-row-"]').count();
  expect(itemsBefore).toBeGreaterThanOrEqual(1);

  const firstDelete = page.locator('[data-testid^="line-item-delete-"]').first();
  const firstItemId = (await firstDelete.getAttribute('data-testid'))
    ?.replace('line-item-delete-', '');
  await firstDelete.click();
  await expect(page.getByTestId(`line-item-delete-${firstItemId}-dialog`)).toBeVisible();
  await page.getByTestId(`line-item-delete-${firstItemId}-dialog-confirm`).click();
  await expect(page.locator('[data-testid^="line-item-row-"]'))
    .toHaveCount(itemsBefore - 1, { timeout: 10_000 });
});

test('Locked budget — items panel is read-only (no add-row, no delete, inputs disabled)', async ({ page, freshLockedBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();
  await expect(page.getByTestId('line-items-panel')).toBeVisible();
  await expect(page.getByTestId('line-items-add-row')).toHaveCount(0);
  const firstQty = page.locator('[data-testid^="line-item-qty-"]').first();
  await expect(firstQty).toBeDisabled();
  await expect(page.locator('[data-testid^="line-item-delete-"]')).toHaveCount(0);
});
