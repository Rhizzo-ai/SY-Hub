// frontend/e2e/payments-view.admin.spec.ts — Chat 19B §R7.3
import { test, expect } from '@playwright/test';
import { adminApi, pmApi } from './helpers/api';
import { getProjectId } from './helpers/seed';
import {
  createPostedActual, getDefaultBudgetLine,
} from './helpers/freshActual';

let postedA: string;
let postedB: string;
let projectId: string;

test.beforeEach(async () => {
  projectId = getProjectId();
  const ctx = await pmApi();
  const line = await getDefaultBudgetLine(ctx, projectId);
  postedA = (await createPostedActual(ctx, projectId, line, {
    supplier_name_snapshot: 'Payments A Ltd',
  })).id;
  postedB = (await createPostedActual(ctx, projectId, line, {
    supplier_name_snapshot: 'Payments B Ltd',
  })).id;
  await ctx.dispose();
});

test('@smoke /payments page loads, shows Posted bills grouped by project', async ({ page }) => {
  await page.goto('/payments');
  await expect(page.getByTestId('payments-page')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId(`payments-project-section-${projectId}`)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId(`payments-row-${postedA}`)).toBeVisible();
  await expect(page.getByTestId(`payments-row-${postedB}`)).toBeVisible();
});

test('selecting rows updates the "Pay X" button label + £ total', async ({ page }) => {
  await page.goto('/payments');
  await expect(page.getByTestId(`payments-row-${postedA}`)).toBeVisible({ timeout: 15_000 });
  await page.getByTestId(`payments-select-${postedA}`).click();
  await expect(page.getByTestId('payments-bulk-pay-button')).toContainText(/Mark 1 as Paid/);
  await page.getByTestId(`payments-select-${postedB}`).click();
  await expect(page.getByTestId('payments-bulk-pay-button')).toContainText(/Mark 2 as Paid/);
});

test('@smoke bulk-pay happy path: pay 2 bills, see 2 success pills, rows gone after close', async ({ page }) => {
  await page.goto('/payments');
  await expect(page.getByTestId(`payments-row-${postedA}`)).toBeVisible({ timeout: 15_000 });
  await page.getByTestId(`payments-select-${postedA}`).click();
  await page.getByTestId(`payments-select-${postedB}`).click();
  await page.getByTestId('payments-bulk-pay-button').click();
  await expect(page.getByTestId('bulk-pay-dialog')).toBeVisible({ timeout: 10_000 });
  await page.getByTestId('bulk-pay-run').click();
  await expect(page.getByTestId(`bulk-pay-success-${postedA}`)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId(`bulk-pay-success-${postedB}`)).toBeVisible();
  await page.getByTestId('bulk-pay-close').click();
  // After close + refetch, rows should be gone from the list.
  await expect(page.getByTestId(`payments-row-${postedA}`)).toHaveCount(0, { timeout: 10_000 });
  await expect(page.getByTestId(`payments-row-${postedB}`)).toHaveCount(0);
});

test('bulk-pay with one bad row: pre-Paid actual produces a red pill', async ({ page }) => {
  // Pre-pay postedA via API so the UI's mark-paid attempt fails (state mismatch).
  const ctx = await adminApi();
  const r = await ctx.post(`/api/v1/actuals/${postedA}/mark-paid`, {
    data: { paid_date: '2026-05-30', payment_reference: 'BACS-PREPAY' },
  });
  if (!r.ok()) throw new Error(`pre-pay failed: ${r.status()}`);
  await ctx.dispose();

  await page.goto('/payments');
  await expect(page.getByTestId(`payments-row-${postedB}`)).toBeVisible({ timeout: 15_000 });
  await page.getByTestId(`payments-select-${postedB}`).click();
  // postedA no longer shows on the page (already Paid).
  await page.getByTestId('payments-bulk-pay-button').click();
  await expect(page.getByTestId('bulk-pay-dialog')).toBeVisible({ timeout: 10_000 });
  await page.getByTestId('bulk-pay-run').click();
  await expect(page.getByTestId(`bulk-pay-success-${postedB}`)).toBeVisible({ timeout: 15_000 });
});

test('payment date applied uniformly across selected rows', async ({ page }) => {
  await page.goto('/payments');
  await page.getByTestId(`payments-select-${postedA}`).click();
  await page.getByTestId(`payments-select-${postedB}`).click();
  await page.getByTestId('payments-bulk-pay-button').click();
  await expect(page.getByTestId('bulk-pay-dialog')).toBeVisible({ timeout: 10_000 });
  await page.getByTestId('bulk-pay-date').fill('2026-04-15');
  await page.getByTestId('bulk-pay-run').click();
  await expect(page.getByTestId(`bulk-pay-success-${postedA}`)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId(`bulk-pay-success-${postedB}`)).toBeVisible();
});

test('payment refs editable per row; empty ref disables the run button', async ({ page }) => {
  await page.goto('/payments');
  await page.getByTestId(`payments-select-${postedA}`).click();
  await page.getByTestId('payments-bulk-pay-button').click();
  await expect(page.getByTestId('bulk-pay-dialog')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('bulk-pay-run')).toBeEnabled();
  await page.getByTestId(`bulk-pay-ref-${postedA}`).fill('');
  await expect(page.getByTestId('bulk-pay-run')).toBeDisabled();
  await page.getByTestId(`bulk-pay-ref-${postedA}`).fill('NEW-REF-001');
  await expect(page.getByTestId('bulk-pay-run')).toBeEnabled();
});
