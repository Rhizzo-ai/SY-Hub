/**
 * SORT_KEY_MAP — translation between TanStack Table column ids (UI
 * aliases like `actual_spent`) and the backend field names that the
 * line / group totals are keyed by (`actuals_to_date`, etc).
 *
 * Chat 23 R3.8 — sort at both levels:
 *   - Group-level sort uses `totals[backendKey]` from
 *     groupLinesByCategory().
 *   - Line-within-group sort uses `line[backendKey]` directly, or a
 *     computed value for the synthetic columns (variance_to_forecast,
 *     forecast_profit, forecast_margin_pct).
 *
 * If a column id is NOT in this map, the dev-mode console.warn in
 * BudgetGridV2Desktop fires; the sort silently no-ops. If a column id
 * maps to `null`, group order stays default but line sort still
 * applies (used for the 3 computed columns).
 */
export const SORT_KEY_MAP = {
  current_budget: 'current_budget',
  actual_spent: 'actuals_to_date',
  committed: 'committed_value',
  variance_to_budget: 'variance_value',
  forecast_cost: 'forecast_final_cost',
  cost_to_complete: 'forecast_to_complete',
  original_budget: 'original_budget',
  pending_changes: 'approved_changes',
  // Computed columns — group-level sort skipped (would require
  // re-walking lines on every render). Line-within-group sort handled
  // inline in the sorted-grouped useMemo.
  variance_to_forecast: null,
  forecast_profit: null,
  forecast_margin_pct: null,
};

/**
 * Compute the synthetic per-line value for the 3 columns that don't
 * map cleanly to a single backend field. Returned as a plain Number
 * (or Number.NEGATIVE_INFINITY for forecast_margin_pct when sale is 0
 * — sorts those rows to the bottom under desc, top under asc).
 */
export function computedLineValue(line, id) {
  if (id === 'variance_to_forecast') {
    return Number(line.forecast_final_cost ?? 0) - Number(line.original_budget ?? 0);
  }
  if (id === 'forecast_profit') {
    return Number(line._allocated_sale_price_provisional ?? 0)
      - Number(line.forecast_final_cost ?? 0);
  }
  if (id === 'forecast_margin_pct') {
    const sale = Number(line._allocated_sale_price_provisional ?? 0);
    if (sale <= 0) return Number.NEGATIVE_INFINITY;
    return (sale - Number(line.forecast_final_cost ?? 0)) / sale;
  }
  return null;
}
