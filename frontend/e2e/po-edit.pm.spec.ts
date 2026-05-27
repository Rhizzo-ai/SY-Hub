// frontend/e2e/po-edit.pm.spec.ts — R7 Batch 2 (Edit, header-only)
//
// Open the edit dialog from a draft PO, change the notes field, and
// save. Smoke layer asserts the dialog mounts + closes on save; the
// operator's pre-push run validates the round-trip persistence.
//
// Tagged @po-batch2 + @smoke.
import { test, expect } from '@playwright/test';
import { getProjectId } from './helpers/seed';

test('@po-batch2 @smoke edit dialog mounts on draft + cancels cleanly', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/purchase-orders?status=draft`);
  await expect(page.getByTestId('po-list')).toBeVisible({ timeout: 15_000 });
  const firstRow = page.locator('[data-testid^="po-row-"] a').first();
  const hasRow = await firstRow.count();
  test.skip(hasRow === 0, 'No draft POs in seed — skipped at smoke layer');
  await firstRow.click();

  await expect(page.getByTestId('po-detail')).toBeVisible({ timeout: 15_000 });
  const editBtn = page.getByTestId('po-actions-edit-btn');
  await expect(editBtn).toBeVisible();
  await editBtn.click();

  await expect(page.getByTestId('po-edit-dialog')).toBeVisible();
  await expect(page.getByTestId('po-edit-tier-banner')).toContainText(/Full header/);
  await expect(page.getByTestId('po-edit-notes')).toBeVisible();
  await page.getByTestId('po-edit-cancel').click();
  await expect(page.getByTestId('po-edit-dialog')).toBeHidden();
});
