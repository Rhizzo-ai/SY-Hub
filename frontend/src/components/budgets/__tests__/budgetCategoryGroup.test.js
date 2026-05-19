/**
 * budgetCategoryGroup test — Chat 23 R3.5.
 *
 * Pins the cost-code prefix → category bucket mapping + totals shape.
 */
import { groupLinesByCategory } from '@/lib/budgetCategoryGroup';

const ccMap = new Map([
  ['cc-1', { id: 'cc-1', code: 'ACQ-001' }],
  ['cc-2', { id: 'cc-2', code: 'ACQ-002' }],
  ['cc-3', { id: 'cc-3', code: 'CON-001' }],
  ['cc-4', { id: 'cc-4', code: 'XYZ-001' }],
]);

const lines = [
  { id: 'l1', cost_code_id: 'cc-1', current_budget: 100, actuals_to_date: 50,
    items: [{ id: 'i1', description: 'Materials', amount: 0 }] },
  { id: 'l2', cost_code_id: 'cc-2', current_budget: 200, actuals_to_date: 25 },
  { id: 'l3', cost_code_id: 'cc-3', current_budget: 500, actuals_to_date: 100 },
  { id: 'l4', cost_code_id: 'cc-4', current_budget: 999, actuals_to_date: 0 },
];

describe('groupLinesByCategory', () => {
  test('buckets ACQ + CON + unknown prefix', () => {
    const out = groupLinesByCategory(lines, ccMap);
    const keys = out.map((b) => b.groupKey);
    expect(keys).toEqual(['land_acquisition', 'construction', 'other_XYZ']);
  });

  test('group label matches CATEGORY_BY_PREFIX', () => {
    const out = groupLinesByCategory(lines, ccMap);
    expect(out[0].groupLabel).toBe('1 Land & Acquisition');
    expect(out[1].groupLabel).toBe('4 Construction');
    // Unknown prefix falls back to the prefix itself.
    expect(out[2].groupLabel).toBe('XYZ');
  });

  test('totals sum across lines in a bucket', () => {
    const out = groupLinesByCategory(lines, ccMap);
    expect(out[0].totals.current_budget).toBe(300);
    expect(out[0].totals.actuals_to_date).toBe(75);
    expect(out[1].totals.current_budget).toBe(500);
  });

  test('isGroup flag is true on bucket; lines retain ids as subRows', () => {
    const out = groupLinesByCategory(lines, ccMap);
    expect(out[0].isGroup).toBe(true);
    expect(out[0].subRows.map((r) => r.id)).toEqual(['l1', 'l2']);
  });

  test('items become subRows of their parent line with isItem=true', () => {
    // Chat 23 R4.5 — items no longer attached as TanStack subRows.
    // The drilldown panel renders items separately. This test now
    // asserts the lack of nested subRows on the line so a future
    // refactor that re-introduces them surfaces in CI.
    const out = groupLinesByCategory(lines, ccMap);
    const firstLine = out[0].subRows[0];
    expect(firstLine.subRows).toBeUndefined();
    // The raw `items` array is still carried — drilldown reads it.
    expect(firstLine.items?.[0]?.description).toBe('Materials');
  });

  test('empty lines produce no groups', () => {
    expect(groupLinesByCategory([], ccMap)).toEqual([]);
  });

  test('cost code missing from map -> "— Uncategorised —"', () => {
    const out = groupLinesByCategory(
      [{ id: 'lx', cost_code_id: 'missing', current_budget: 1 }],
      new Map(),
    );
    expect(out[0].groupLabel).toBe('— Uncategorised —');
  });
});
