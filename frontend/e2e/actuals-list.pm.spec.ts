// frontend/e2e/actuals-list.pm.spec.ts — Chat 19B §R7.3
import { test, expect } from './helpers/freshActual';
import { getProjectId } from './helpers/seed';

test('@smoke list page loads with table + filters', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await expect(page.getByTestId('actuals-list-page')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('actuals-filters')).toBeVisible();
  await expect(page.getByTestId(`actual-row-${freshPostedActual.id}`)).toBeVisible({ timeout: 10_000 });
});

test('filter by status: only Posted rows show', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await expect(page.getByTestId('actuals-list-page')).toBeVisible({ timeout: 15_000 });
  await page.getByTestId('actuals-filter-status').click();
  await page.getByRole('option', { name: 'Posted', exact: true }).click();
  await expect(page.getByTestId(`actual-row-${freshPostedActual.id}`)).toBeVisible({ timeout: 10_000 });
  // Every visible status badge in a row should be `Posted`.
  await expect(page.locator('[data-testid^="actual-row-"] [data-testid="actual-status-Draft"]')).toHaveCount(0);
});

test('filter by source: only Manual rows show', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await expect(page.getByTestId('actuals-list-page')).toBeVisible({ timeout: 15_000 });
  await page.getByTestId('actuals-filter-source').click();
  await page.getByRole('option', { name: 'Manual', exact: true }).click();
  await expect(page.getByTestId(`actual-row-${freshPostedActual.id}`)).toBeVisible({ timeout: 10_000 });
});

test('search by supplier name: row filtering happens', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await expect(page.getByTestId('actuals-list-page')).toBeVisible({ timeout: 15_000 });
  await page.getByTestId('actuals-filter-search').fill('E2E Test Supplier');
  await expect(page.getByTestId(`actual-row-${freshPostedActual.id}`)).toBeVisible({ timeout: 10_000 });
  await page.getByTestId('actuals-filter-search').fill('___NOTHING_MATCHES_XYZ___');
  await expect(page.getByTestId('actuals-empty-state')).toBeVisible({ timeout: 5_000 });
});

test('clicking a row navigates to detail page', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await expect(page.getByTestId(`actual-row-${freshPostedActual.id}`)).toBeVisible({ timeout: 15_000 });
  await page.getByTestId(`actual-row-${freshPostedActual.id}`).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/actuals/${freshPostedActual.id}`));
  await expect(page.getByTestId('actual-detail-page')).toBeVisible({ timeout: 10_000 });
});
