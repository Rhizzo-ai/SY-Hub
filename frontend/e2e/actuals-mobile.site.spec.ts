// frontend/e2e/actuals-mobile.site.spec.ts — Chat 19B §R7.3
//
// Site-role tests on a mobile viewport. Confirms (a) Read-only banner +
// no state-transition buttons in mobile rows, and (b) Create button routes
// to /actuals/new on mobile rather than opening the desktop Sheet.

import { test, expect } from '@playwright/test';

test.use({ viewport: { width: 375, height: 800 } });

import { getProjectId } from './helpers/seed';

test('site user on mobile viewport: list renders, banner present, no row state-transition buttons', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  await expect(page.getByTestId('actuals-list-page')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('actuals-list-mobile-banner')).toBeVisible();
  // Mobile rows: any in-row action buttons should not render.
  await expect(page.locator('[data-testid^="actual-row-"] [data-testid="action-post"]')).toHaveCount(0);
});

test('site user on mobile: tap "Create actual" → navigates to /actuals/new', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals`);
  const createBtn = page.getByTestId('actuals-create-button');
  // Site role may or may not have create perm; if visible, must navigate (not sheet).
  if (await createBtn.count() === 0) {
    test.skip(true, 'site role lacks actuals.create — sheet/route path not exercisable');
  }
  await createBtn.click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/actuals/new`));
});
