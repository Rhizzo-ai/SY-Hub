/**
 * Zod schemas for the Budgets API (Prompt 2.4B-i §R3.2).
 *
 * Match the backend serialiser shape *exactly* (see
 * backend/app/routers/budgets.py::_serialise_*) — every field uses the
 * backend-canonical name. The Build Pack v2 §R3.2 schemas use invented
 * names ('description', 'position', 'unit_cost', 'ffc', 'cost_code_label',
 * 'version'...) that do not exist on the backend. We use the actual names.
 *
 *   Sensitive-field handling (D11 / Build Pack §R5):
 *     The backend strips sensitive fields from the payload depending
 *     on scope/permission. We mark every potentially-omitted field
 *     `.nullable().optional()` so Zod accepts both shapes. Render
 *     code shows "—" for omitted fields.
 *
 *   Sensitive field manifest (verified against routers/budgets.py
 *   @2026-02 — B88 Pack 2 / Chat 51):
 *
 *     Budget summary  → total_budget, total_actuals,
 *                       total_committed_not_invoiced,
 *                       total_forecast_to_complete, forecast_final_cost,
 *                       variance_vs_budget, variance_pct
 *                       (ALL OMITTED for construction-scope callers)
 *     Budget detail   → all of the above (no extra)
 *     Line summary    → actuals_to_date, committed_value,
 *                       invoiced_against_commitment,
 *                       committed_not_invoiced, forecast_final_cost,
 *                       variance_value, variance_pct
 *                       (line-level money keys: visible to ALL callers
 *                        on IN-SCOPE lines per D4. Still .optional()
 *                        because the same schema is also reused for
 *                        write-response shapes that may omit them.)
 *
 * Decimals come over the wire as strings (Decimal serialised) — we use
 * `z.coerce.number()` to convert. `null` is preserved for missing data.
 */
import { z } from 'zod';

// ──────────────────────────────────────────────────────────────────────
// Enums
// ──────────────────────────────────────────────────────────────────────

export const BudgetStatus = z.enum([
  'Draft', 'Active', 'Locked', 'Closed', 'Superseded',
]);

export const VarianceStatus = z.enum(['Green', 'Amber', 'Red']);

// FTC method enum — matches backend `budget_lines.ftc_method` column
// (CHECK constraint values, see backend/app/models/budgets.py FTC_METHODS).
export const FTCMethod = z.enum([
  'Manual', 'Budget_Remaining', 'Committed_Only', 'Percentage_Complete',
]);

// Decimal-as-string-or-number coercer: backend returns strings like "1234.56".
// Zod `coerce.number` handles both; null passes through.
const moneyNumber = z.preprocess(
  (v) => (v === null || v === undefined || v === '' ? null : Number(v)),
  z.number().nullable(),
);

// Required money (non-sensitive money fields the backend always returns)
const moneyRequired = z.preprocess(
  (v) => (v === null || v === undefined ? NaN : Number(v)),
  z.number(),
);

// ──────────────────────────────────────────────────────────────────────
// BudgetLineItem (R3.2)
// ──────────────────────────────────────────────────────────────────────

export const BudgetLineItemSchema = z.object({
  id: z.string().uuid(),
  budget_line_id: z.string().uuid(),
  description: z.string(),
  quantity: moneyNumber,
  unit: z.string().nullable(),
  rate: moneyNumber,                       // backend uses `rate`, not `unit_cost`
  amount: moneyRequired,
  notes: z.string().nullable(),
  display_order: z.number().int(),         // backend uses `display_order`, not `position`
});

// ──────────────────────────────────────────────────────────────────────
// BudgetLine — `cost_code_label` is JOINED client-side (no backend field).
// `version` and `ftc_value` do NOT exist on the backend; absent on purpose.
// ──────────────────────────────────────────────────────────────────────

export const BudgetLineSchema = z.object({
  id: z.string().uuid(),
  budget_id: z.string().uuid(),
  cost_code_id: z.string().uuid(),
  cost_code_subcategory_id: z.string().uuid().nullable(),
  entity_id: z.string().uuid(),
  line_description: z.string().nullable(),

  // Always present
  original_budget: moneyRequired,
  approved_changes: moneyRequired,
  current_budget: moneyRequired,
  forecast_to_complete: moneyRequired,
  ftc_method: FTCMethod,
  percentage_complete: z.preprocess(
    (v) => (v === null || v === undefined || v === '' ? null : Number(v)),
    z.number().min(0).max(100).nullable(),
  ),
  linked_programme_task_id: z.string().uuid().nullable(),
  is_locked: z.boolean(),
  requires_attention: z.boolean(),
  display_order: z.number().int(),
  notes: z.string().nullable(),
  variance_status: VarianceStatus,
  // Chat 39 §R2 B-CONTINGENCY: surfaces the contingency flag so the
  // ContingencyDrawdown source-line guard in CreateBudgetChangeDialog
  // sees a concrete boolean instead of `undefined` (which inverted to
  // truthy and blocked every drawdown attempt).
  is_contingency: z.boolean().default(false),
  // Timestamps (added in backend 2.4A.2 for §R7 refetch-on-save banner)
  created_at: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),

  // SENSITIVE — backend strips for users without budgets.view_sensitive
  actuals_to_date: moneyNumber.optional(),
  committed_value: moneyNumber.optional(),
  invoiced_against_commitment: moneyNumber.optional(),
  committed_not_invoiced: moneyNumber.optional(),
  forecast_final_cost: moneyNumber.optional(),
  variance_value: moneyNumber.optional(),
  variance_pct: moneyNumber.optional(),

  // Eager-loaded items (detail responses only)
  items: z.array(BudgetLineItemSchema).default([]),
});

// ──────────────────────────────────────────────────────────────────────
// BudgetSummary — returned by list endpoint (no `lines`)
// BudgetDetail  — returned by detail endpoint (with `lines`)
// ──────────────────────────────────────────────────────────────────────

const BudgetSummaryBase = z.object({
  id: z.string().uuid(),
  project_id: z.string().uuid(),
  source_appraisal_id: z.string().uuid(),
  version_number: z.number().int(),
  version_label: z.string(),
  is_current: z.boolean(),
  status: BudgetStatus,
  summary_refreshed_at: z.string().nullable(),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),

  // B88 Pack 2 §R5 (Chat 51) — cached header money keys are ALL
  // full-scope-only now. The backend OMITS the key entirely for
  // construction-scope callers (Tier 2). All seven are `.optional()`
  // so the parser accepts both shapes; render code shows "—" when
  // absent (see fmtMoney / format.js).
  total_budget: moneyNumber.optional(),
  total_actuals: moneyNumber.optional(),
  total_committed_not_invoiced: moneyNumber.optional(),
  total_forecast_to_complete: moneyNumber.optional(),
  forecast_final_cost: moneyNumber.optional(),
  variance_vs_budget: moneyNumber.optional(),
  variance_pct: moneyNumber.optional(),
});

export const BudgetSummarySchema = BudgetSummaryBase;

export const BudgetDetailSchema = BudgetSummaryBase.extend({
  notes: z.string().nullable(),
  locked_at: z.string().nullable(),
  locked_by_user_id: z.string().uuid().nullable(),
  closed_at: z.string().nullable(),
  closed_by_user_id: z.string().uuid().nullable(),
  created_by_user_id: z.string().uuid(),
  lines: z.array(BudgetLineSchema).default([]),
});

// List response: { project_id, items, count } — not a bare array
export const BudgetListResponseSchema = z.object({
  project_id: z.string().uuid(),
  items: z.array(BudgetSummarySchema),
  count: z.number().int(),
});

// ──────────────────────────────────────────────────────────────────────
// PATCH payloads — used to validate client-built bodies before send (H11)
// `version` is NOT a field on the backend, so absent here too.
// `description` → `line_description` (backend canonical).
// ──────────────────────────────────────────────────────────────────────

export const BudgetLinePatchSchema = z.object({
  line_description: z.string().max(2000).nullable().optional(),
  notes: z.string().max(5000).nullable().optional(),
  percentage_complete: z.preprocess(
    (v) => (v === null || v === undefined || v === '' ? null : Number(v)),
    z.number().min(0).max(100).nullable(),
  ).optional(),
  ftc_method: FTCMethod.optional(),
  forecast_to_complete: z.preprocess(
    (v) => (v === null || v === undefined || v === '' ? null : Number(v)),
    z.number().nullable(),
  ).optional(),
  cost_code_id: z.string().uuid().optional(),
  cost_code_subcategory_id: z.string().uuid().nullable().optional(),
  approved_changes: z.preprocess(
    (v) => (v === null || v === undefined || v === '' ? null : Number(v)),
    z.number().nullable(),
  ).optional(),
}).strict();

export const LineItemCreateSchema = z.object({
  description: z.string().min(1).max(500),
  quantity: z.coerce.number().min(0).nullable().optional(),
  unit: z.string().nullable().optional(),
  rate: z.coerce.number().min(0).nullable().optional(),  // NOT `unit_cost`
  amount: z.coerce.number().min(0),
  notes: z.string().max(2000).nullable().optional(),
  display_order: z.number().int().optional(),
}).strict();

export const LineItemPatchSchema = LineItemCreateSchema.partial().strict();

// Reorder body — `ordered_line_ids` (snake_case, matches backend Pydantic).
export const ReorderLinesSchema = z.object({
  budget_id: z.string().uuid(),
  ordered_line_ids: z.array(z.string().uuid()).min(1),
}).strict();
