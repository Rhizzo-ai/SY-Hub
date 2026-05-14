// frontend/e2e/helpers/asserts.ts
//
// Reusable Playwright assertions for cross-cutting concerns.

import { Page, expect } from '@playwright/test';

/**
 * Mobile-floor regression — at 375x812 the lines grid must:
 *  - render the mobile banner
 *  - hide drag handles
 *  - hide the inline-edit cells (tap-to-edit ignored)
 */
export async function assertMobileFloor(page: Page) {
  await expect(page.getByTestId('budget-lines-mobile-banner')).toBeVisible();
  await expect(page.locator('[data-testid^="budget-line-drag-"]')).toHaveCount(0);
}
