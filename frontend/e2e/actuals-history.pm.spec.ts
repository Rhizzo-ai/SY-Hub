// frontend/e2e/actuals-history.pm.spec.ts — Chat 19B §R7.3
import { test, expect } from './helpers/freshActual';
import { getProjectId } from './helpers/seed';

test('History toggle: collapsed by default, expands on click, shows events', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  await expect(page.getByTestId('actual-history')).toBeVisible({ timeout: 15_000 });
  // Collapsed: the list should not be rendered.
  await expect(page.getByTestId('actual-history-list')).toHaveCount(0);
  await page.getByTestId('actual-history-toggle').click();
  // At least one event (Created / Posted) should appear.
  await expect(page.locator('[data-testid^="history-event-"]').first()).toBeVisible({ timeout: 10_000 });
});

test('History payload tile renders only when caller has actuals.view_sensitive', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  await page.getByTestId('actual-history-toggle').click();
  // PM in the current seed lacks `actuals.view_sensitive`, so the payload tile
  // is gated off (D26). Assert the inverse — the gating works. The positive
  // case (payload visible for super_admin) is exercised implicitly via the
  // admin-only state-machine spec, where the same component renders the same
  // history with payloads visible.
  await expect(page.locator('[data-testid^="history-event-"]').first())
    .toBeVisible({ timeout: 10_000 });
  await expect(page.locator('[data-testid^="history-payload-"]')).toHaveCount(0);
});
