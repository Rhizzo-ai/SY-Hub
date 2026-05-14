// frontend/e2e/auth.anon.spec.ts — Auth #1, #2 (anon project)
import { test, expect } from '@playwright/test';

const PASSWORD = process.env.TEST_USER_PASSWORD || 'TestUser-Dev-2026!';

test('@smoke login success — redirects away from /login and shows topbar', async ({ page }) => {
  await page.goto('/login');
  await page.getByTestId('login-email').fill('test-pm@example.test');
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').click();
  // Route-agnostic: must leave /login + topbar must mount.
  await expect(page).not.toHaveURL(/\/login/, { timeout: 15_000 });
  await expect(page.getByTestId('app-topbar')).toBeVisible();
});

test('login failure — wrong password surfaces error toast', async ({ page }) => {
  await page.goto('/login');
  await page.getByTestId('login-email').fill('test-pm@example.test');
  await page.getByTestId('login-password').fill('definitely-wrong-password');
  await page.getByTestId('login-submit').click();
  // No login-error testid exists; sonner toast surfaces backend message text.
  await expect(page.getByText(/invalid|incorrect|credentials/i)).toBeVisible({ timeout: 10_000 });
  await expect(page).toHaveURL(/\/login/);
});
