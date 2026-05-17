// frontend/e2e/ai-capture-retry.admin.spec.ts — Chat 19C §R7.6
import { test, expect } from '@playwright/test';
import { getFailedJobId, getAwaitingReviewJobId } from './helpers/freshCapture';

test.use({ storageState: 'playwright/.auth/admin.json' });

test('Failed job shows Retry button; single click queues', async ({ page }) => {
  const jobId = getFailedJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await expect(page.getByTestId('capture-retry-button')).toBeVisible();
  await page.getByTestId('capture-retry-button').click();
  await expect(page.getByText('Retry queued')).toBeVisible();
});

test('Awaiting_Review job does NOT show Retry button', async ({ page }) => {
  const jobId = getAwaitingReviewJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await expect(page.getByTestId('capture-retry-button')).toBeHidden();
});
