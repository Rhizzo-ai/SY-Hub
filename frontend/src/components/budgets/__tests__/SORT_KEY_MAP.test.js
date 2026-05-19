/**
 * SORT_KEY_MAP test — Chat 23 R3.8.
 *
 * Pins the column-id → backend-field translation. Silent bugs surface
 * here: any new sortable column added to BudgetGridColumns MUST be
 * added to SORT_KEY_MAP, otherwise applySort no-ops at runtime.
 */
import { SORT_KEY_MAP, computedLineValue } from '../grid/SORT_KEY_MAP';

describe('SORT_KEY_MAP', () => {
  test('every documented column id is present', () => {
    // Lock the exact key set so an accidental rename in BudgetGridColumns
    // (e.g. `committed` -> `committed_total`) shows up in CI rather
    // than silently breaking sort.
    expect(new Set(Object.keys(SORT_KEY_MAP))).toEqual(new Set([
      'current_budget', 'actual_spent', 'committed',
      'variance_to_budget', 'forecast_cost', 'cost_to_complete',
      'original_budget', 'pending_changes',
      // Computed columns map to null (group sort skipped).
      'variance_to_forecast', 'forecast_profit', 'forecast_margin_pct',
    ]));
  });

  test('computed columns map to null (group sort skip)', () => {
    expect(SORT_KEY_MAP.variance_to_forecast).toBeNull();
    expect(SORT_KEY_MAP.forecast_profit).toBeNull();
    expect(SORT_KEY_MAP.forecast_margin_pct).toBeNull();
  });

  test('standard columns map to a backend field', () => {
    expect(SORT_KEY_MAP.actual_spent).toBe('actuals_to_date');
    expect(SORT_KEY_MAP.committed).toBe('committed_value');
    expect(SORT_KEY_MAP.variance_to_budget).toBe('variance_value');
    expect(SORT_KEY_MAP.forecast_cost).toBe('forecast_final_cost');
  });
});

describe('computedLineValue', () => {
  const baseline = {
    forecast_final_cost: 120,
    original_budget: 100,
    _allocated_sale_price_provisional: 250,
  };

  test('variance_to_forecast = FFC - original_budget', () => {
    expect(computedLineValue(baseline, 'variance_to_forecast')).toBe(20);
  });

  test('forecast_profit = sale - FFC', () => {
    expect(computedLineValue(baseline, 'forecast_profit')).toBe(130);
  });

  test('forecast_margin_pct = (sale - FFC) / sale', () => {
    expect(computedLineValue(baseline, 'forecast_margin_pct')).toBeCloseTo(0.52);
  });

  test('forecast_margin_pct returns -Infinity when sale <= 0', () => {
    expect(computedLineValue(
      { ...baseline, _allocated_sale_price_provisional: 0 },
      'forecast_margin_pct',
    )).toBe(Number.NEGATIVE_INFINITY);
  });

  test('unknown column id returns null', () => {
    expect(computedLineValue(baseline, 'something_else')).toBeNull();
  });
});
