// frontend/e2e/actuals-create.pm.spec.ts — Chat 19B §R7.3
import { test, expect } from '@playwright/test';
import { getProjectId } from './helpers/seed';

test('@smoke create a Draft actual via the Sheet, see new row in list', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await expect(page.getByTestId('actuals-list-page')).toBeVisible({ timeout: 15_000 });
  await page.getByTestId('actuals-create-button').click();
  await expect(page.getByTestId('create-actual-form')).toBeVisible({ timeout: 10_000 });

  // Pick first budget line.
  const lineSelect = page.locator('[data-testid="budget-line-picker"] select');
  await lineSelect.waitFor({ state: 'visible', timeout: 10_000 });
  await lineSelect.selectOption({ index: 1 });

  const stamp = `Smoke create ${Date.now()}`;
  await page.getByTestId('create-actual-description').fill(stamp);
  await page.getByTestId('create-actual-supplier').fill('Playwright Co');
  await page.getByTestId('create-actual-net').fill('500.00');
  await page.getByTestId('create-actual-vat').fill('100.00');

  // Entity is a Radix Select with no default; pick the first option.
  await page.getByTestId('create-actual-entity').click();
  await page.getByRole('option').first().click();

  await page.getByTestId('create-actual-submit').click();
  await expect(page.getByTestId('create-actual-form')).toBeHidden({ timeout: 15_000 });
  await expect(page.getByText(stamp)).toBeVisible({ timeout: 10_000 });
});

test('validation: missing description blocks submit', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await page.getByTestId('actuals-create-button').click();
  await expect(page.getByTestId('create-actual-form')).toBeVisible({ timeout: 10_000 });
  // Fill everything EXCEPT description.
  const lineSelect = page.locator('[data-testid="budget-line-picker"] select');
  await lineSelect.selectOption({ index: 1 });
  await page.getByTestId('create-actual-supplier').fill('No-desc Co');
  await page.getByTestId('create-actual-net').fill('100.00');
  await page.getByTestId('create-actual-submit').click();
  // Form-level error or field-level — sheet stays open.
  await expect(page.getByTestId('create-actual-form')).toBeVisible({ timeout: 5_000 });
});

test('validation: bad money format blocks submit', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await page.getByTestId('actuals-create-button').click();
  await expect(page.getByTestId('create-actual-form')).toBeVisible({ timeout: 10_000 });
  const lineSelect = page.locator('[data-testid="budget-line-picker"] select');
  await lineSelect.selectOption({ index: 1 });
  await page.getByTestId('create-actual-description').fill('Bad money');
  await page.getByTestId('create-actual-supplier').fill('Bad Money Co');
  await page.getByTestId('create-actual-net').fill('12.345'); // 3dp — rejected
  await page.getByTestId('create-actual-submit').click();
  await expect(page.getByTestId('create-actual-form')).toBeVisible({ timeout: 5_000 });
});

test('CIS toggle reveals 3 CIS fields; without it, fields hidden', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await page.getByTestId('actuals-create-button').click();
  await expect(page.getByTestId('create-actual-form')).toBeVisible({ timeout: 10_000 });
  // Initially CIS fields not present.
  await expect(page.getByTestId('cis-fields')).toHaveCount(0);
  await page.getByTestId('create-actual-cis-applicable').click();
  await expect(page.getByTestId('cis-fields')).toBeVisible();
  await expect(page.getByTestId('create-actual-cis-rate')).toBeVisible();
  await expect(page.getByTestId('create-actual-cis-labour')).toBeVisible();
  await expect(page.getByTestId('create-actual-cis-materials')).toBeVisible();
});
