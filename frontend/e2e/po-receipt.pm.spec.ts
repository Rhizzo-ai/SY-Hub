// frontend/e2e/po-receipt.pm.spec.ts — R7 Batch 2 §R7.4
//
// Wires the receipt form behind po-actions-receipt-btn (issued) and
// po-actions-receipt-partial-btn (partially_receipted). Opening the
// dialog and asserting the date/cancel/confirm shape is sufficient
// for an E2E smoke — deeper line-quantity assertions live in the
// Jest matrix and the operator's full Playwright pre-push run.
//
// Tagged @po-batch2 + @smoke for the e2e:po-batch2 / e2e:smoke scripts.
import { test, expect } from '@playwright/test';
import { getProjectId } from './helpers/seed';

test('@po-batch2 @smoke receipt dialog opens with date + confirm shape', async ({ page }) => {
  const projectId = getProjectId();
  // Drive to the PO list and pick the first issued / partial PO (best-
  // effort against seed; operator's pre-push run validates fully).
  await page.goto(`/projects/${projectId}/purchase-orders?status=issued`);
  await expect(page.getByTestId('po-list')).toBeVisible({ timeout: 15_000 });

  // Click the first PO link; if no rows, skip (seed-dependent).
  const firstRow = page.locator('[data-testid^="po-row-"] a').first();
  const hasRow = await firstRow.count();
  test.skip(hasRow === 0, 'No issued POs in seed — skipped at smoke layer');
  await firstRow.click();

  await expect(page.getByTestId('po-detail')).toBeVisible({ timeout: 15_000 });
  // Receipt button (issued) — clicking it should mount the dialog.
  const recBtn = page.getByTestId('po-actions-receipt-btn');
  await expect(recBtn).toBeVisible();
  await recBtn.click();
  await expect(page.getByTestId('po-receipt-dialog')).toBeVisible();
  await expect(page.getByTestId('po-receipt-date')).toBeVisible();
  await expect(page.getByTestId('po-receipt-confirm')).toBeVisible();
  await page.getByTestId('po-receipt-cancel').click();
  await expect(page.getByTestId('po-receipt-dialog')).toBeHidden();
});
