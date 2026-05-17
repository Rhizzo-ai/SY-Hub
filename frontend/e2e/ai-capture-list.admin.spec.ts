// frontend/e2e/ai-capture-list.admin.spec.ts — Chat 19C §R7.3
import { test, expect } from '@playwright/test';
import { getAwaitingReviewJobId } from './helpers/freshCapture';

test.use({ storageState: 'playwright/.auth/admin.json' });

test('@smoke /ai-capture page loads + shows the inbox queue', async ({ page }) => {
  await page.goto('/ai-capture');
  await expect(page.getByTestId('capture-jobs-list-page')).toBeVisible();
  await expect(
    page.getByTestId('capture-jobs-table').or(page.getByTestId('capture-jobs-empty')),
  ).toBeVisible({ timeout: 10_000 });
});

test('status filter switches between Awaiting_Review and Failed', async ({ page }) => {
  await page.goto('/ai-capture');
  await page.getByTestId('capture-status-trigger').click();
  await page.getByTestId('capture-status-option-Failed').click();
  await expect(
    page.getByTestId('capture-jobs-table').or(page.getByTestId('capture-jobs-empty')),
  ).toBeVisible({ timeout: 10_000 });
});

test('All statuses option shows every job', async ({ page }) => {
  await page.goto('/ai-capture');
  await page.getByTestId('capture-status-trigger').click();
  await page.getByTestId('capture-status-option-__ALL__').click(); // D40 sentinel
  await expect(page.getByTestId('capture-jobs-table')).toBeVisible({ timeout: 10_000 });
});

test('row click navigates to detail page', async ({ page }) => {
  await page.goto('/ai-capture');
  const jobId = getAwaitingReviewJobId();
  await page.getByTestId(`capture-row-${jobId}`).click();
  await expect(page).toHaveURL(new RegExp(`/ai-capture/${jobId}$`));
  await expect(page.getByTestId('capture-detail-page')).toBeVisible();
});
