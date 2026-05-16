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

test('History payload visible for pm with actuals.view_sensitive', async ({ page, freshPostedActual }) => {
  const projectId = getProjectId();
  await page.goto(`/projects/${projectId}/actuals/${freshPostedActual.id}`);
  await page.getByTestId('actual-history-toggle').click();
  // At least one event has a payload (Posted event has the previous status etc.).
  await expect(page.locator('[data-testid^="history-payload-"]').first())
    .toBeVisible({ timeout: 10_000 });
});
