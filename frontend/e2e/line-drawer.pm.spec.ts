// frontend/e2e/line-drawer.pm.spec.ts — LineDrawer #1 through #7
//
// #6 (E9 conflict banner) is quarantined per Build Pack v4 known risk —
// window.queryClient exposure is not confirmed in Chat 17 source; the
// deterministic refetch path can't be enforced without a source change
// (DO NOT add `window.queryClient = queryClient` to App.jsx — operator
// policy 3a + 4a, surface flake instead of touching frontend/src).
//
// #5 (FTC method + Manual FTC) uses role selectors — kept active per
// policy 4a until proven flaky.
import { test, expect } from './helpers/freshBudget';
import { getProjectId } from './helpers/seed';

test('open via row menu — drawer renders with line values pre-filled', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();
  await expect(page.getByTestId('line-drawer')).toBeVisible();
  await expect(page.getByTestId('line-drawer-title')).toContainText(/Substructure works/);
  await expect(page.getByTestId('line-drawer-description')).toHaveValue('Substructure works');
});

test('@smoke edit + save — dirty enables Save, click persists', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();
  await expect(page.getByTestId('line-drawer-dirty-state')).toContainText(/No changes/);
  await expect(page.getByTestId('line-drawer-save')).toBeDisabled();
  await page.getByTestId('line-drawer-description').fill('E2E drawer edit');
  await expect(page.getByTestId('line-drawer-dirty-state')).toContainText(/Unsaved changes/);
  await expect(page.getByTestId('line-drawer-save')).toBeEnabled();
  await page.getByTestId('line-drawer-save').click();
  await expect(page.getByTestId('line-drawer-dirty-state'))
    .toContainText(/No changes/, { timeout: 10_000 });
  await page.getByTestId('line-drawer-close').click();
  await expect(page.locator('[data-testid^="budget-line-desc-"]').first())
    .toContainText('E2E drawer edit');
});

test('Esc with dirty changes opens discard dialog, Keep editing preserves state', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();
  await page.getByTestId('line-drawer-description').fill('dirty');
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('line-drawer-discard-dialog')).toBeVisible();
  await page.getByTestId('line-drawer-discard-cancel').click();
  await expect(page.getByTestId('line-drawer-discard-dialog')).toBeHidden();
  await expect(page.getByTestId('line-drawer-description')).toHaveValue('dirty');
  await page.keyboard.press('Escape');
  await page.getByTestId('line-drawer-discard-confirm').click();
  await expect(page.getByTestId('line-drawer')).toBeHidden();
});

test('Cmd+S / Ctrl+S saves when dirty', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();
  await page.getByTestId('line-drawer-description').fill('keyboard-saved');
  const modifier = process.platform === 'darwin' ? 'Meta' : 'Control';
  await page.keyboard.press(`${modifier}+s`);
  await expect(page.getByTestId('line-drawer-dirty-state'))
    .toContainText(/No changes/, { timeout: 10_000 });
  await page.getByTestId('line-drawer-close').click();
  await expect(page.locator('[data-testid^="budget-line-desc-"]').first())
    .toContainText('keyboard-saved');
});

test('FTC method switch to Manual reveals forecast_to_complete input', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();
  const ftcMethod = page.getByRole('combobox', { name: /ftc method/i });
  await expect(page.getByRole('spinbutton', { name: /forecast.*complete|manual/i }))
    .toHaveCount(0);
  await ftcMethod.click();
  await page.getByRole('option', { name: /manual entry/i }).click();
  await expect(page.getByRole('spinbutton', { name: /forecast.*complete|manual/i }))
    .toBeVisible();
});

test.skip('E9 conflict banner — background PATCH advances updated_at, banner appears on refetch', async ({ page, freshBudget: budget }) => {
  // QUARANTINED per Build Pack v4 §15 known risks + operator policy 3a:
  // depends on `window.queryClient` exposure which is NOT confirmed in
  // Chat 17 source. Source change to App.jsx is forbidden without
  // operator approval. Demoted to unit-test coverage (Chat 17 §R8
  // LineDrawer.test.jsx "E9 conflict banner" provides equivalent
  // coverage in the Jest harness).
  expect(true).toBe(true);
  void budget; void page;
});

test('cost-code reassignment — Draft allows picker change, persists', async ({ page, freshBudget: budget }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/budgets/${budget.id}`);
  await expect(page.getByTestId('budget-lines-grid')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[data-testid^="budget-line-row-"]').first())
    .toBeVisible({ timeout: 10_000 });

  const ccCell = page.locator('[data-testid^="budget-line-cost-code-"]').first();
  const initialLabel = (await ccCell.textContent())?.trim() ?? '';
  expect(initialLabel.length).toBeGreaterThan(0);

  await page.locator('[data-testid^="budget-line-menu-"]').first().click();
  await page.locator('[data-testid^="budget-line-menu-open-"]').first().click();

  await page.getByTestId('cost-code-picker-trigger').click();
  const options = page.locator('[data-testid^="cost-code-option-"]');
  await expect(options.first()).toBeVisible({ timeout: 5_000 });
  // The currently-selected option is the first; pick the second.
  await options.nth(1).click();

  await expect(page.getByTestId('line-drawer-dirty-state')).toContainText(/Unsaved changes/);
  await page.getByTestId('line-drawer-save').click();
  await expect(page.getByTestId('line-drawer-dirty-state'))
    .toContainText(/No changes/, { timeout: 10_000 });
  await page.getByTestId('line-drawer-close').click();

  const afterLabel = (await page.locator('[data-testid^="budget-line-cost-code-"]').first().textContent())?.trim() ?? '';
  expect(afterLabel).not.toEqual(initialLabel);
});
