// frontend/e2e/ai-capture-discard.admin.spec.ts — Chat 19C §R7.5
import { test, expect } from '@playwright/test';
import { getAwaitingReviewJobId, getQueuedJobId } from './helpers/freshCapture';

test.use({ storageState: 'playwright/.auth/admin.json' });

test('Discard Awaiting_Review with reason transitions to Discarded', async ({ page }) => {
  const jobId = getAwaitingReviewJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await page.getByTestId('capture-discard-button').click();
  await page.getByTestId('capture-discard-dialog-reason').fill('Duplicate of INV-001');
  await page.getByTestId('capture-discard-dialog-confirm').click();
  await expect(page.getByText('Job discarded')).toBeVisible();
});

test('Discard works from Queued status (D46)', async ({ page }) => {
  const jobId = getQueuedJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await page.getByTestId('capture-discard-button').click();
  await expect(page.getByTestId('capture-discard-dialog-confirm')).toBeDisabled();
  await page.getByTestId('capture-discard-dialog-reason').fill('Test discard from queued');
  await expect(page.getByTestId('capture-discard-dialog-confirm')).toBeEnabled();
  await page.getByTestId('capture-discard-dialog-confirm').click();
  await expect(page.getByText('Job discarded')).toBeVisible();
});

test('Empty reason keeps Discard button disabled', async ({ page }) => {
  const jobId = getAwaitingReviewJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await page.getByTestId('capture-discard-button').click();
  await expect(page.getByTestId('capture-discard-dialog-confirm')).toBeDisabled();
  await page.getByTestId('capture-discard-dialog-reason').fill('   ');
  // Whitespace-only is treated as empty
  await expect(page.getByTestId('capture-discard-dialog-confirm')).toBeDisabled();
});
