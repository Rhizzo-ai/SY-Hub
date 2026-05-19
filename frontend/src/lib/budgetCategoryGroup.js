/**
 * budgetCategoryGroup — Chat 23 R3.5.
 *
 * Group flat budget lines into category buckets keyed by cost-code
 * prefix. Each bucket carries the lines plus computed totals (used by
 * the group header row and group-level sort).
 *
 * Categories are derived from `cost_code.code.split('-')[0]`. The 9
 * canonical prefixes map to the operator-facing labels below. Any
 * unknown prefix falls under `— Uncategorised —` (or the prefix
 * itself if available).
 *
 * Future_Tasks: shift to a backend `GET /budgets/:id/category-summary`
 * endpoint once budgets cross 200+ lines. Client-side aggregation
 * becomes a perf concern past that.
 */
const CATEGORY_BY_PREFIX = {
  ACQ: { key: 'land_acquisition', label: '1 Land & Acquisition' },
  PLN: { key: 'planning',         label: '2 Planning' },
  PRO: { key: 'professional',     label: '3 Professional Fees' },
  CON: { key: 'construction',     label: '4 Construction' },
  INT: { key: 'internal',         label: '4 Internal Finishes' },
  EXT: { key: 'externals',        label: '5 Externals' },
  FIN: { key: 'finance',          label: '6 Finance & Holding' },
  SAL: { key: 'sales',            label: '7 Sales & Marketing' },
  CTG: { key: 'contingency',      label: '8 Contingency' },
};

const SUMMED_KEYS = [
  'original_budget', 'current_budget', 'actuals_to_date',
  'committed_value', 'forecast_final_cost', 'forecast_to_complete',
  'variance_value', 'approved_changes',
];

function computeTotals(lines) {
  const totals = {};
  for (const k of SUMMED_KEYS) {
    totals[k] = lines.reduce((acc, l) => acc + Number(l[k] ?? 0), 0);
  }
  return totals;
}

export function groupLinesByCategory(lines, costCodeMap) {
  const buckets = new Map();
  for (const line of lines) {
    const code = costCodeMap.get(line.cost_code_id)?.code ?? '';
    const prefix = code.split('-')[0].toUpperCase();
    const cat = CATEGORY_BY_PREFIX[prefix]
      ?? { key: `other_${prefix || 'na'}`, label: prefix || '— Uncategorised —' };
    if (!buckets.has(cat.key)) {
      buckets.set(cat.key, { ...cat, lines: [] });
    }
    buckets.get(cat.key).lines.push(line);
  }
  return Array.from(buckets.values()).map((bucket) => ({
    isGroup: true,
    groupKey: bucket.key,
    groupLabel: bucket.label,
    totals: computeTotals(bucket.lines),
    // The `subRows` shape feeds TanStack Table's expanding-rows API.
    // Chat 23 R4.5: lines do NOT carry items as flat sub-rows any
    // more. Items are rendered by BudgetGridDrilldown via a colspan
    // expansion row sitting directly under the parent line. This
    // keeps the drilldown panel (incl. Bills/POs/Variations) bound
    // to the same expand toggle as the breakdown.
    subRows: bucket.lines.map((line) => ({ ...line })),
  }));
}

export { CATEGORY_BY_PREFIX };
