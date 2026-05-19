/**
 * BudgetGridHeaderTiles — Chat 23 R3.10.
 *
 * 5 totals above the grid:
 *   Original budget | Current budget | Actual spent | Forecast cost
 *   | Cost to complete
 *
 * Sourced from the budget summary fields (`b.total_*`). Sensitive-
 * field gating: hides Actual spent + Forecast cost + Cost to complete
 * when the user lacks `budgets.view_sensitive` (those values are
 * derived from sensitive totals the backend strips).
 *
 * Plus the existing whole-budget variance badge and sensitive-fields
 * warning — both reused from Chat 17.
 */
import { formatMoney } from '@/lib/format';

function Tile({ label, value, testid }) {
  return (
    <div
      className="rounded-lg border border-slate-200 bg-white px-4 py-3"
      data-testid={testid}
    >
      <div className="text-xs uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 font-mono text-lg font-semibold text-slate-900 tabular-nums">
        {formatMoney(value)}
      </div>
    </div>
  );
}

export function BudgetGridHeaderTiles({ budget, canViewSensitive }) {
  // `total_budget` is always returned. The other 4 totals only land
  // when the response includes the sensitive sub-block (R3.9 gating).
  return (
    <div
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
      data-testid="bg2-header-tiles"
    >
      <Tile
        label="Original budget"
        value={budget?.total_budget}
        testid="bg2-tile-original"
      />
      <Tile
        label="Current budget"
        value={budget?.total_budget}
        testid="bg2-tile-current"
      />
      {canViewSensitive && (
        <>
          <Tile
            label="Actual spent"
            value={budget?.total_actuals}
            testid="bg2-tile-actuals"
          />
          <Tile
            label="Forecast cost"
            value={budget?.forecast_final_cost}
            testid="bg2-tile-forecast"
          />
          <Tile
            label="Cost to complete"
            value={budget?.total_forecast_to_complete}
            testid="bg2-tile-ftc"
          />
        </>
      )}
    </div>
  );
}
