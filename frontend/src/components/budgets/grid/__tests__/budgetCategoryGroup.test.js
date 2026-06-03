/**
 * Build Pack 2.6-FIX (Chat 39) §R5 — C-UNCAT grid-flash test.
 *
 * When the cost-code map is empty (or mid-refetch), the grouping
 * helper must NOT bucket lines that carry a valid `cost_code_id`
 * under "— Uncategorised —". §R2 C-UNCAT guards
 * groupLinesByCategory to return a single "Loading…" bucket so the
 * grid keeps a stable shape until the codes arrive.
 */
import { groupLinesByCategory } from '@/lib/budgetCategoryGroup';

const valLines = [
  { id: 'l1', cost_code_id: 'cc-1', current_budget: 100, actuals_to_date: 10 },
  { id: 'l2', cost_code_id: 'cc-2', current_budget: 200, actuals_to_date: 20 },
];

describe('groupLinesByCategory — C-UNCAT loading guard', () => {
  test('does not bucket valid lines as Uncategorised when codes are loading', () => {
    const emptyMap = new Map();
    const out = groupLinesByCategory(valLines, emptyMap);
    // ONE group only, labelled "Loading…" — NOT "— Uncategorised —"
    // and NOT split into the production category buckets.
    expect(out).toHaveLength(1);
    expect(out[0].groupKey).toBe('loading');
    expect(out[0].groupLabel).toBe('Loading…');
    expect(out[0].groupLabel).not.toMatch(/Uncategorised/i);
    // All lines remain visible inside the loading bucket.
    expect(out[0].subRows.map((r) => r.id)).toEqual(['l1', 'l2']);
    // Totals still sum across the lines so the header row renders sane.
    expect(out[0].totals.current_budget).toBe(300);
  });

  test('regression: with a populated map, the loading guard does not fire', () => {
    const populatedMap = new Map([
      ['cc-1', { id: 'cc-1', code: 'CON-001' }],
      ['cc-2', { id: 'cc-2', code: 'PRO-001' }],
    ]);
    const out = groupLinesByCategory(valLines, populatedMap);
    // Two real category buckets, no "Loading…".
    expect(out.map((b) => b.groupKey)).toEqual(['construction', 'professional']);
  });
});
