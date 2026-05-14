// frontend/e2e/budget-detail.readonly.spec.ts — BudgetDetail #3 (sensitive hidden)
//
// test-readonly has budgets.view but NOT budgets.view_sensitive. The header
// must omit the £ values on the tiles (or render dashes / blanks) and the
// variance pill.
import { test, expect } from '@playwright/test';
import { getProjectId, getBudgetIds } from './helpers/seed';

test('sensitive fields hidden for read_only role', async ({ page }) => {
  const projectId = getProjectId();
  const { v2 } = getBudgetIds();
  await page.goto(`/projects/${projectId}/budgets/${v2}`);
  await expect(page.getByTestId('budget-header')).toBeVisible({ timeout: 10_000 });
  // Variance row must be absent or value masked — assert NO £ amount renders
  // anywhere on the tiles row. Tiles must still render labels.
  const allTiles = page.getByTestId('budget-tiles');
  await expect(allTiles).toBeVisible();
  const tilesText = (await allTiles.textContent()) ?? '';
  // For read_only, the backend should redact monetary values; the UI replaces
  // them with em-dashes or hides the tile entirely.
  expect(tilesText).not.toMatch(/£[\d,]+/);
});
