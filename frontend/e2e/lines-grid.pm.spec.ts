// frontend/e2e/lines-grid.pm.spec.ts — Lines grid #1, #2, #3, #4
import { test, expect } from './helpers/freshBudget';
import { getProjectId } from './helpers/seed';
import { assertMobileFloor } from './helpers/asserts';

test('@smoke drag-reorder — order persists across page reload', async ({ page, freshBudget: budget }) => {
  test.setTimeout(45_000);
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  const rows = page.locator('[data-testid^="budget-line-row-"]');
  await expect(rows).toHaveCount(3, { timeout: 10_000 });
  const before = await rows.evaluateAll((els) =>
    els.map((el) => el.querySelector('[data-testid^="budget-line-desc-"]')?.textContent?.trim()),
  );
  expect(before).toEqual(['Substructure works', 'Superstructure', 'Finishes']);

  // dnd-kit KeyboardSensor — focus handle, Space, ArrowDown×2 (with
  // small delays so each swap settles before the next), Space.
  const firstDrag = page.locator('[data-testid^="budget-line-drag-"]').first();
  await firstDrag.focus();
  await page.keyboard.press('Space');
  await page.waitForTimeout(200);
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(300);
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(300);
  await page.keyboard.press('Space');

  // Allow optimistic-update + server confirm to settle.
  await page.waitForTimeout(1_500);

  await page.reload();
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  const rowsAfter = page.locator('[data-testid^="budget-line-row-"]');
  await expect(rowsAfter).toHaveCount(3, { timeout: 10_000 });
  const after = await rowsAfter.evaluateAll((els) =>
    els.map((el) => el.querySelector('[data-testid^="budget-line-desc-"]')?.textContent?.trim()),
  );
  expect(after).toEqual(['Superstructure', 'Finishes', 'Substructure works']);
});

test('inline edit description — Enter saves, persists across reload', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  const firstDesc = page.locator('[data-testid^="budget-line-desc-"]').first();
  await firstDesc.click();
  const input = page.locator('[data-testid^="budget-line-desc-input-"]').first();
  await expect(input).toBeFocused();
  await input.fill('E2E edited description');
  await input.press('Enter');
  await expect(page.locator('[data-testid^="budget-line-desc-"]').first())
    .toContainText('E2E edited description', { timeout: 10_000 });
  await page.reload();
  await expect(page.locator('[data-testid^="budget-line-desc-"]').first())
    .toContainText('E2E edited description', { timeout: 10_000 });
});

test('inline edit %% complete — blur saves, persists across reload', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  const firstPct = page.locator('[data-testid^="budget-line-pct-"]').first();
  await firstPct.click();
  const input = page.locator('[data-testid^="budget-line-pct-input-"]').first();
  await expect(input).toBeFocused();
  await input.fill('42');
  await input.blur();
  await expect(page.locator('[data-testid^="budget-line-pct-"]').first()).toContainText('42', { timeout: 10_000 });
  await page.reload();
  await expect(page.locator('[data-testid^="budget-line-pct-"]').first()).toContainText('42', { timeout: 10_000 });
});

test('mobile floor — 375x812 viewport hides drag, ignores edit tap', async ({ page, freshBudget: budget }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await assertMobileFloor(page);
  const firstDesc = page.locator('[data-testid^="budget-line-desc-"]').first();
  await firstDesc.tap();
  await expect(page.locator('[data-testid^="budget-line-desc-input-"]')).toHaveCount(0);
});
