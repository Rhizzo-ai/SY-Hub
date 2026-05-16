// frontend/e2e/actuals-detail.pm.spec.ts — Chat 19B §R7.3
import { test, expect } from './helpers/freshActual';
import { getProjectId } from './helpers/seed';

test('Draft actual: header shows source + dates + money tiles', async ({ page, freshDraftActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshDraftActual.id}`);
  await expect(page.getByTestId('actual-detail-page')).toBeVisible({ timeout: 15_000 });
  // Money tiles: Net / VAT / Gross / CIS — 4 tiles.
  await expect(page.getByText('Net')).toBeVisible();
  await expect(page.getByText('Gross')).toBeVisible();
  await expect(page.getByText(/Transaction date:/)).toBeVisible();
});

test('Posted actual: status pill shows Posted; paid-info section hidden', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  await expect(page.getByTestId('actual-detail-page')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('actual-status-Posted')).toBeVisible();
  // Paid-info banner not present until status flips to Paid.
  await expect(page.getByTestId('paid-info-banner')).toHaveCount(0);
});
