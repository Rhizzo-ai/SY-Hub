// frontend/e2e/ai-capture-promote.admin.spec.ts — Chat 19C §R7.4
import { test, expect } from '@playwright/test';
import { getAwaitingReviewJobId } from './helpers/freshCapture';
import { getProjectId } from './helpers/seed';

test.use({ storageState: 'playwright/.auth/admin.json' });

test('@smoke happy-path promote creates Draft actual and navigates', async ({ page }) => {
  const jobId = getAwaitingReviewJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await expect(page.getByTestId('promote-form')).toBeVisible();

  // Pick project (E2E demo project from globalSetup seed.ts)
  await page.getByTestId('project-picker').click();
  await page.getByTestId(`project-picker-option-${getProjectId()}`).click();

  // Pick entity
  await page.getByTestId('promote-entity').click();
  await page.locator('[data-testid^="promote-entity-"]').first().click();

  // Budget line
  await page.locator('[data-testid="budget-line-picker"] [role="combobox"]').click();
  await page.locator('[data-testid^="budget-line-option-"]').first().click();

  // Required fields pre-filled from stub provider extracted_data;
  // submit and assert navigation.
  await page.getByTestId('promote-submit').click();

  await expect(page.getByText('Promoted to Draft actual')).toBeVisible({ timeout: 10_000 });
  // PASS-2 H1: nav uses form's project_id, not stale suggested_project_id
  await expect(page).toHaveURL(new RegExp(`/projects/${getProjectId()}/actuals/`));
});

test('submitting with missing entity shows error, no navigation', async ({ page }) => {
  const jobId = getAwaitingReviewJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await page.getByTestId('project-picker').click();
  await page.getByTestId(`project-picker-option-${getProjectId()}`).click();
  // skip entity selection
  await page.getByTestId('promote-submit').click();
  await expect(page.getByTestId('promote-entity-error')).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/ai-capture/${jobId}$`));
});

test('CIS toggle reveals CIS fields', async ({ page }) => {
  const jobId = getAwaitingReviewJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await expect(page.getByTestId('promote-cis-rate')).toBeHidden();
  await page.getByTestId('promote-cis-toggle').click();
  await expect(page.getByTestId('promote-cis-rate')).toBeVisible();
});

test('AI extraction panel renders confidence pills', async ({ page }) => {
  const jobId = getAwaitingReviewJobId();
  await page.goto(`/ai-capture/${jobId}`);
  await expect(page.getByTestId('extracted-fields-panel')).toBeVisible();
  await expect(
    page.locator('[data-testid="confidence-pill-ok"], [data-testid="confidence-pill-low"]').first(),
  ).toBeVisible();
});
