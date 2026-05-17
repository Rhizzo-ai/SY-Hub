/**
 * Test fixtures — Prompt 2.4B-i §R8.2 (E7-aligned).
 *
 * Field names match the live backend serialiser, NOT the original
 * Build Pack draft. See errata E7 in
 * /app/docs/SY_Hub_Prompt_2_4B_i_Frontend_Build_Pack_v2.md.
 *
 * Money values are numbers (matches the backend's Decimal → JSON
 * coercion as observed; Zod schemas accept either since they coerce).
 */

const BUDGET_ID    = '11111111-1111-1111-1111-111111111111';
const PROJECT_ID   = '22222222-2222-2222-2222-222222222222';
const ENTITY_ID    = '44444444-4444-4444-4444-444444444444';
const APPRAISAL_ID = '55555555-5555-5555-5555-555555555555';
const COST_CODE_ID = '66666666-6666-6666-6666-666666666666';
const LINE_ID_1    = '77777777-7777-7777-7777-777777777777';
const LINE_ID_2    = '88888888-8888-8888-8888-888888888888';
const LINE_ID_3    = '99999999-9999-9999-9999-999999999999';
const ITEM_ID      = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

export const IDS = {
  BUDGET_ID, PROJECT_ID, ENTITY_ID, APPRAISAL_ID,
  COST_CODE_ID, LINE_ID_1, LINE_ID_2, LINE_ID_3, ITEM_ID,
};

export function mockLine(overrides = {}) {
  return {
    id: LINE_ID_1,
    budget_id: BUDGET_ID,
    cost_code_id: COST_CODE_ID,
    cost_code_subcategory_id: null,
    entity_id: ENTITY_ID,
    line_description: 'Test line',
    display_order: 0,
    is_locked: false,
    requires_attention: false,
    original_budget: 100000,
    approved_changes: 0,
    current_budget: 100000,
    actuals_to_date: 30000,
    committed_not_invoiced: 20000,
    committed_value: 20000,
    invoiced_against_commitment: 0,
    ftc_method: 'Budget_Remaining',
    forecast_to_complete: 50000,
    forecast_final_cost: 100000,
    variance_value: 0,
    variance_pct: 0,
    variance_status: 'Green',
    percentage_complete: 30,
    linked_programme_task_id: null,
    notes: null,
    items: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    ...overrides,
  };
}

export function mockItem(overrides = {}) {
  return {
    id: ITEM_ID,
    budget_line_id: LINE_ID_1,
    description: 'Cement 25kg bag',
    quantity: '100.0000',
    unit: 'bag',
    rate: '8.5000',
    amount: '850.00',
    notes: null,
    display_order: 0,
    ...overrides,
  };
}

export function mockBudget(overrides = {}) {
  const lines = overrides.lines ?? [
    mockLine({ id: LINE_ID_1, display_order: 0 }),
    mockLine({
      id: LINE_ID_2,
      display_order: 1,
      line_description: 'Steel frame',
      original_budget: 250000, current_budget: 250000,
      forecast_to_complete: 200000, forecast_final_cost: 250000,
      variance_status: 'Green',
    }),
    mockLine({
      id: LINE_ID_3,
      display_order: 2,
      line_description: 'Cladding',
      variance_status: 'Amber',
      variance_value: 5000,
      variance_pct: 4.0,
    }),
  ];
  const total_budget   = lines.reduce((s, l) => s + l.current_budget, 0);
  const total_actuals  = lines.reduce((s, l) => s + l.actuals_to_date, 0);
  const total_cni      = lines.reduce((s, l) => s + l.committed_not_invoiced, 0);
  const total_ftc      = lines.reduce((s, l) => s + l.forecast_to_complete, 0);
  const total_ffc      = lines.reduce((s, l) => s + l.forecast_final_cost, 0);
  const variance_v     = total_ffc - total_budget;
  return {
    id: BUDGET_ID,
    project_id: PROJECT_ID,
    source_appraisal_id: APPRAISAL_ID,
    version_number: 1,
    version_label: 'v1 — opening',
    is_current: true,
    status: 'Active',
    total_budget,
    total_actuals,
    total_committed_not_invoiced: total_cni,
    total_forecast_to_complete: total_ftc,
    forecast_final_cost: total_ffc,
    variance_vs_budget: variance_v,
    variance_pct: total_budget === 0 ? 0 : (variance_v / total_budget) * 100,
    notes: 'Demo',
    closed_at: null,
    closed_by_user_id: null,
    locked_at: null,
    locked_by_user_id: null,
    summary_refreshed_at: '2026-05-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    created_by_user_id: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
    updated_at: '2026-05-01T00:00:00Z',
    lines,
    ...overrides,
  };
}

/**
 * Strip sensitive fields — emulates backend behaviour for users
 * lacking `budgets.view_sensitive`. Only the truly sensitive lookalikes
 * are stripped; non-sensitive money / status / FTC method / notes
 * remain. The Zod schema declares the sensitive money fields as
 * `.nullable().optional()` so the stripped payload still parses.
 */
export function stripSensitive(budget) {
  return {
    ...budget,
    total_actuals: undefined,
    total_committed_not_invoiced: undefined,
    total_forecast_to_complete: undefined,
    forecast_final_cost: undefined,
    variance_vs_budget: undefined,
    variance_pct: undefined,
    lines: budget.lines?.map(
      ({
        actuals_to_date, committed_not_invoiced, committed_value,
        invoiced_against_commitment,
        forecast_final_cost,
        variance_value, variance_pct,
        ...rest
      }) => rest,
    ),
  };
}

/**
 * Identity helper for AuthContext mocks. Permissions list mirrors
 * backend role payloads (e.g. PM has view+view_sensitive+create+edit;
 * Director has admin).
 */
export function mockMe(perms = ['budgets.view']) {
  return {
    id: 'me-uuid',
    email: 'tester@example.test',
    name: 'Tester',
    permissions: perms,
  };
}


// ─── Actuals fixtures (Chat 19B §R6) ─────────────────────────────────
export const makePostedActual = (overrides = {}) => ({
  id: '11111111-1111-4111-8111-111111111111',
  project_id: '22222222-2222-4222-8222-222222222222',
  budget_line_id: '33333333-3333-4333-8333-333333333333',
  entity_id: '44444444-4444-4444-8444-444444444444',
  source_type: 'Manual_Entry',
  source_reference: null,
  external_id: null,
  transaction_date: '2026-05-15',
  posting_date: '2026-05-15',
  description: 'Test bill',
  net_amount: '1000.00',
  vat_amount: '200.00',
  gross_amount: '1200.00',
  vat_rate_pct: '20',
  is_vat_recoverable: true,
  currency: 'GBP',
  exchange_rate: null,
  supplier_id: null,
  supplier_name_snapshot: 'ACME Ltd',
  supplier_invoice_ref: 'INV-001',
  is_cis_applicable: false,
  retention_released: false,
  linked_commitment_id: null,
  related_subcontract_id: null,
  is_reconciled_to_xero: false,
  status: 'Posted',
  posted_at: '2026-05-15T10:00:00+00:00',
  paid_date: null,
  payment_reference: null,
  disputed_at: null,
  voided_at: null,
  created_at: '2026-05-15T09:00:00+00:00',
  updated_at: '2026-05-15T10:00:00+00:00',
  ...overrides,
});

export const makeDraftActual = (overrides = {}) =>
  makePostedActual({ status: 'Draft', posted_at: null, ...overrides });

export const makePaidActual = (overrides = {}) =>
  makePostedActual({
    status: 'Paid',
    paid_date: '2026-05-20',
    payment_reference: 'BACS-20260520-abcdef',
    ...overrides,
  });


// ---------------------------------------------------------------------------
// AI capture job fixtures — Chat 19C §R6.8
// ---------------------------------------------------------------------------

export function makeQueuedJob(overrides = {}) {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    inbound_email_message_id: '00000000-0000-0000-0000-000000000010',
    attachment_path: '/var/attachments/test.pdf',
    status: 'Queued',
    attempts: 0,
    last_attempted_at: null,
    last_error_message: null,
    extracted_data: null,
    confidence_scores: null,
    suggested_entity_id: null,
    suggested_project_id: null,
    suggested_cost_code_id: null,
    target_actual_id: null,
    model_used: null,
    prompt_tokens: null,
    completion_tokens: null,
    cost_pence: null,
    created_at: '2026-05-16T10:00:00Z',
    updated_at: '2026-05-16T10:00:00Z',
    ...overrides,
  };
}

export function makeAwaitingReviewJob(overrides = {}) {
  return {
    ...makeQueuedJob(),
    status: 'Awaiting_Review',
    attempts: 1,
    last_attempted_at: '2026-05-16T10:01:00Z',
    extracted_data: {
      supplier_name: 'Acme Supplies Ltd',
      supplier_invoice_ref: 'INV-001',
      invoice_date: '2026-04-01',
      description: 'Stub: materials delivery',
      net_amount: '100.00',
      vat_amount: '20.00',
      gross_amount: '120.00',
      vat_rate_pct: '20.00',
    },
    confidence_scores: {
      supplier_name: 0.95,
      supplier_invoice_ref: 0.90,
      invoice_date: 0.85,
      net_amount: 0.99,
      vat_amount: 0.99,
      gross_amount: 0.99,
      overall: 0.93,
    },
    model_used: 'test-stub',
    ...overrides,
  };
}

export function makeFailedJob(overrides = {}) {
  return {
    ...makeQueuedJob(),
    status: 'Failed',
    attempts: 3,
    last_attempted_at: '2026-05-16T10:05:00Z',
    last_error_message: 'Anthropic returned 500',
    ...overrides,
  };
}

export function makeCompletedJob(overrides = {}) {
  return {
    ...makeAwaitingReviewJob(),
    status: 'Completed',
    target_actual_id: '00000000-0000-0000-0000-0000000000aa',
    ...overrides,
  };
}
