/**
 * Bug-lock: Tier 2 (construction-scope) budget list + detail payloads
 * have all seven cached header money keys ABSENT — Zod must accept
 * those shapes and the consumer must render "—" gracefully.
 *
 * Regression report (Gate 2 eyeball, B88 Pack 2):
 *   "Failed to load budgets: Schema drift @ GET /projects/:id/budgets:
 *    items.0.total_budget: Expected number, received nan;
 *    items.1.total_budget: Expected number, received nan."
 *
 * Root cause: `total_budget` was required (`moneyRequired`) in the
 * client list/detail schemas. Backend §R5 now omits it for Tier 2.
 *
 * Build Pack §7.1 explicit requirement:
 *   "render gracefully when total_budget is absent — show '—', no
 *    NaN/undefined artefacts."
 */
import { formatMoney } from '@/lib/format';
import {
  BudgetListResponseSchema, BudgetDetailSchema, BudgetSummarySchema,
} from '@/lib/schemas/budgets';

const HEADER_MONEY_KEYS = [
  'total_budget', 'total_actuals', 'total_committed_not_invoiced',
  'total_forecast_to_complete', 'forecast_final_cost',
  'variance_vs_budget', 'variance_pct',
];

function summaryBase() {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    project_id: '00000000-0000-0000-0000-000000000002',
    source_appraisal_id: '00000000-0000-0000-0000-000000000003',
    version_number: 1,
    version_label: 'Original',
    is_current: true,
    status: 'Active',
    summary_refreshed_at: null,
    created_at: null,
    updated_at: null,
  };
}

describe('Tier 2 schema drift (B88 Pack 2 Gate 2 follow-up)', () => {
  test('budget summary parses when ALL header money keys are absent', () => {
    const t2Payload = summaryBase();
    // None of the seven cached header money keys present — matches the
    // construction-scope response shape from /api/v1/projects/:id/budgets.
    const parsed = BudgetSummarySchema.parse(t2Payload);
    for (const k of HEADER_MONEY_KEYS) {
      expect(parsed[k]).toBeUndefined();
    }
  });

  test('budget list response parses with multiple Tier-2 items', () => {
    const parsed = BudgetListResponseSchema.parse({
      project_id: '00000000-0000-0000-0000-000000000002',
      items: [
        summaryBase(),
        { ...summaryBase(), id: '00000000-0000-0000-0000-000000000099',
          version_number: 2 },
      ],
      count: 2,
    });
    expect(parsed.items).toHaveLength(2);
    expect(parsed.items[0].total_budget).toBeUndefined();
  });

  test('budget detail parses when header money keys are absent', () => {
    const parsed = BudgetDetailSchema.parse({
      ...summaryBase(),
      notes: null,
      locked_at: null, locked_by_user_id: null,
      closed_at: null, closed_by_user_id: null,
      created_by_user_id: '00000000-0000-0000-0000-000000000004',
      lines: [],
    });
    for (const k of HEADER_MONEY_KEYS) {
      expect(parsed[k]).toBeUndefined();
    }
  });

  test('formatMoney renders "—" for every absent header key', () => {
    const t2 = summaryBase();
    for (const k of HEADER_MONEY_KEYS) {
      expect(formatMoney(t2[k])).toBe('—');
    }
  });

  test('Tier 1 payload (all keys present) still parses', () => {
    const t1Payload = {
      ...summaryBase(),
      total_budget: '1225000.00',
      total_actuals: '614400.00',
      total_committed_not_invoiced: '0.00',
      total_forecast_to_complete: '410000.00',
      forecast_final_cost: '1024400.00',
      variance_vs_budget: '-200600.00',
      variance_pct: '-16.376',
    };
    const parsed = BudgetSummarySchema.parse(t1Payload);
    expect(parsed.total_budget).toBe(1225000);
    expect(parsed.forecast_final_cost).toBe(1024400);
  });
});
