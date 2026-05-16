// frontend/e2e/actuals-state-machine.admin.spec.ts — Chat 19B §R7.3
import { test, expect } from './helpers/freshActual';
import { getProjectId } from './helpers/seed';

test('@smoke Draft → Post: status pill updates to Posted', async ({ page, freshDraftActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshDraftActual.id}`);
  await expect(page.getByTestId('action-post')).toBeVisible({ timeout: 15_000 });
  await page.getByTestId('action-post').click();
  await page.getByTestId('action-dialog-submit').click();
  await expect(page.getByTestId('actual-status-Posted')).toBeVisible({ timeout: 10_000 });
});

test('Posted → Mark Paid: dialog needs payment_ref; status → Paid', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  await expect(page.getByTestId('action-mark-paid')).toBeVisible({ timeout: 15_000 });
  await page.getByTestId('action-mark-paid').click();
  // Submit disabled until reference is filled.
  await expect(page.getByTestId('action-dialog-submit')).toBeDisabled();
  await page.getByTestId('mark-paid-reference').fill('BACS-E2E-PAY');
  await page.getByTestId('action-dialog-submit').click();
  await expect(page.getByTestId('actual-status-Paid')).toBeVisible({ timeout: 10_000 });
});

test('Posted → Void: dialog needs reason; void_reason banner appears', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  await page.getByTestId('action-void').click();
  await expect(page.getByTestId('action-dialog-submit')).toBeDisabled();
  await page.getByTestId('void-reason').fill('Duplicate entry, voiding');
  await page.getByTestId('action-dialog-submit').click();
  await expect(page.getByTestId('actual-status-Void')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('void-reason-banner')).toBeVisible();
});

test('Posted → Dispute: reason required, dispute banner appears', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  await page.getByTestId('action-dispute').click();
  await expect(page.getByTestId('action-dialog-submit')).toBeDisabled();
  await page.getByTestId('dispute-reason').fill('Supplier overbilled by £100');
  await page.getByTestId('action-dialog-submit').click();
  await expect(page.getByTestId('actual-status-Disputed')).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('dispute-reason-banner')).toBeVisible();
});

test('Disputed → Undispute: returns to Posted', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  // Disputed first via UI.
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  await page.getByTestId('action-dispute').click();
  await page.getByTestId('dispute-reason').fill('Temp dispute for undispute test');
  await page.getByTestId('action-dialog-submit').click();
  await expect(page.getByTestId('actual-status-Disputed')).toBeVisible({ timeout: 10_000 });
  // Undispute.
  await page.getByTestId('action-undispute').click();
  await page.getByTestId('action-dialog-submit').click();
  await expect(page.getByTestId('actual-status-Posted')).toBeVisible({ timeout: 10_000 });
});

test('Release retention: button visible when retention is unreleased (Posted state)', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  // Fresh Posted actuals have `retention_released=false` by default, so the
  // button is visible (per `canReleaseRetention` — which gates on state +
  // approve perm + !retention_released, NOT on retention amount being > 0).
  await expect(page.getByTestId('action-release-retention')).toBeVisible({ timeout: 10_000 });
});

test('Paid actual: no action buttons rendered', async ({ page, freshPostedActual, browserName: _bn }) => {
  const projectId = getProjectId();
  // First flip to Paid via UI.
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  await page.getByTestId('action-mark-paid').click();
  await page.getByTestId('mark-paid-reference').fill('BACS-PAID-TEST');
  await page.getByTestId('action-dialog-submit').click();
  await expect(page.getByTestId('actual-status-Paid')).toBeVisible({ timeout: 10_000 });
  // No Post / Mark Paid / Dispute / Undispute on a Paid row.
  await expect(page.getByTestId('action-post')).toHaveCount(0);
  await expect(page.getByTestId('action-mark-paid')).toHaveCount(0);
  await expect(page.getByTestId('action-dispute')).toHaveCount(0);
  await expect(page.getByTestId('action-void')).toHaveCount(0);
});
