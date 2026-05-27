// frontend/e2e/po-void.pm.spec.ts — R7 Batch 2 §R7.6
//
// Void confirm-dialog: required-reason gate + cancel returns control.
// The destructive "actually void" path is exercised by the operator's
// pre-push Playwright run against a fresh issued PO; the smoke layer
// only validates that the dialog mounts and gates correctly.
//
// Tagged @po-batch2 + @smoke.
import { test, expect } from '@playwright/test';
import { getProjectId } from './helpers/seed';

test('@po-batch2 @smoke void dialog: confirm disabled until reason; cancel closes', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/purchase-orders?status=issued`);
  await expect(page.getByTestId('po-list')).toBeVisible({ timeout: 15_000 });
  const firstRow = page.locator('[data-testid^="po-row-"] a').first();
  const hasRow = await firstRow.count();
  test.skip(hasRow === 0, 'No issued POs in seed — skipped at smoke layer');
  await firstRow.click();

  await expect(page.getByTestId('po-detail')).toBeVisible({ timeout: 15_000 });
  const voidBtn = page.getByTestId('po-actions-void-issued-btn');
  await expect(voidBtn).toBeVisible();
  await voidBtn.click();

  await expect(page.getByTestId('po-void-dialog')).toBeVisible();
  const confirm = page.getByTestId('po-void-confirm');
  await expect(confirm).toBeDisabled();
  await page.getByTestId('po-void-reason').fill('   ');
  await expect(confirm).toBeDisabled();
  await page.getByTestId('po-void-reason').fill('duplicate PO');
  await expect(confirm).toBeEnabled();
  // Walk back out via cancel — smoke layer doesn't mutate state.
  await page.getByTestId('po-void-cancel').click();
  await expect(page.getByTestId('po-void-dialog')).toBeHidden();
});
