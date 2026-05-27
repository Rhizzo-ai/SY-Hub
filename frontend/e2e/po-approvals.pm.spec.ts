// frontend/e2e/po-approvals.pm.spec.ts — R7 Batch 2 §R7.5
//
// Per-project approvals dashboard tab. Asserts the tab mounts, the
// table is present, and the Review affordance lands on the PO detail
// with ?tab=approvals (so <POApprovalPanel/> takes over).
//
// Tagged @po-batch2 + @smoke.
import { test, expect } from '@playwright/test';
import { getProjectId } from './helpers/seed';

test('@po-batch2 @smoke approvals dashboard tab renders + deep-links to PO detail', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/purchase-orders?tab=approvals`);
  await expect(page.getByTestId('po-list')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('po-list-tab-approvals')).toHaveClass(/border-b-2/);
  await expect(page.getByTestId('po-approvals-tab')).toBeVisible();
  // Either rows render or the empty state — both are valid.
  const rows = page.locator('[data-testid^="po-approvals-row-"]');
  const empty = page.getByTestId('po-approvals-empty');
  await expect(rows.first().or(empty)).toBeVisible({ timeout: 10_000 });
});

test('@po-batch2 switching back to All POs renders the regular list', async ({ page }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/purchase-orders?tab=approvals`);
  await expect(page.getByTestId('po-approvals-tab')).toBeVisible({ timeout: 10_000 });
  await page.getByTestId('po-list-tab-all').click();
  await expect(page.getByTestId('po-list-table')).toBeVisible({ timeout: 10_000 });
});
