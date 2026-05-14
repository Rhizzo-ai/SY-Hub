// frontend/e2e/auth.pm.spec.ts — Auth #3 (logout) — pm project
import { test, expect } from '@playwright/test';

test('logout via topbar menu — returns to /login', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('app-topbar')).toBeVisible({ timeout: 10_000 });
  await page.getByTestId('topbar-user-menu').click();
  await page.getByTestId('menu-signout').click();
  await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
});
