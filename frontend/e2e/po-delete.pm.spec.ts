// frontend/e2e/po-delete.pm.spec.ts — R7 Batch 2 (Delete, draft-only)
//
// Two assertions:
//   1. On a draft PO, po-actions-delete-btn renders and the confirm
//      dialog mounts on click.
//   2. On an issued PO, po-actions-delete-btn does NOT render (the
//      backend would 422 anyway).
//
// Tagged @po-batch2 + @smoke.
import { test, expect } from '@playwright/test';
import { getProjectId } from './helpers/seed';

test('@po-batch2 @smoke draft PO: delete-btn mounts behind confirm dialog', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/purchase-orders?status=draft`);
  await expect(page.getByTestId('po-list')).toBeVisible({ timeout: 15_000 });
  const firstRow = page.locator('[data-testid^="po-row-"] a').first();
  const hasRow = await firstRow.count();
  test.skip(hasRow === 0, 'No draft POs in seed — skipped at smoke layer');
  await firstRow.click();

  await expect(page.getByTestId('po-detail')).toBeVisible({ timeout: 15_000 });
  const delBtn = page.getByTestId('po-actions-delete-btn');
  await expect(delBtn).toBeVisible();
  await delBtn.click();
  await expect(page.getByTestId('po-delete-dialog')).toBeVisible();
  await expect(page.getByTestId('po-delete-confirm')).toBeVisible();
  await page.getByTestId('po-delete-cancel').click();
  await expect(page.getByTestId('po-delete-dialog')).toBeHidden();
});

test('@po-batch2 issued PO: delete-btn does NOT render (mirrors 422)', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/purchase-orders?status=issued`);
  await expect(page.getByTestId('po-list')).toBeVisible({ timeout: 15_000 });
  const firstRow = page.locator('[data-testid^="po-row-"] a').first();
  const hasRow = await firstRow.count();
  test.skip(hasRow === 0, 'No issued POs in seed — skipped at smoke layer');
  await firstRow.click();

  await expect(page.getByTestId('po-detail')).toBeVisible({ timeout: 15_000 });
  // Delete must not render on a non-draft PO.
  await expect(page.getByTestId('po-actions-delete-btn')).toHaveCount(0);
});
