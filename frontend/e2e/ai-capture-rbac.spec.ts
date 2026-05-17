// frontend/e2e/ai-capture-rbac.spec.ts — Chat 19C §R7.7
import { test, expect } from '@playwright/test';
import { getAwaitingReviewJobId } from './helpers/freshCapture';

test.use({ storageState: 'playwright/.auth/readonly.json' });

test('readonly user does NOT see AI Capture nav entry', async ({ page }) => {
  await page.goto('/entities');
  await expect(page.getByTestId('nav-ai-capture')).toBeHidden();
});

test('readonly user navigating to /ai-capture sees no-perm panel', async ({ page }) => {
  await page.goto('/ai-capture');
  await expect(page.getByTestId('capture-jobs-no-perm')).toBeVisible();
});

test('readonly user direct-URL to detail sees no-perm panel', async ({ page }) => {
  const jobId = getAwaitingReviewJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await expect(page.getByTestId('capture-detail-no-perm')).toBeVisible();
});
