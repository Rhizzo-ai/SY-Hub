/**
 * Zod schemas for the Actuals API (Chat 19B §R1.1).
 *
 * Mirror the backend `_serialise_actual` response. Sensitive fields are
 * `.nullable().optional()` — a single schema parses both gated (full) and
 * ungated (stripped) responses (chat-17 E7 pattern). UI checks
 * `=== undefined` AND `=== null` and renders "—" in both cases. The
 * existing `lib/format.js::formatMoney(v)` already handles both — pass it
 * `null | undefined | "1234.56"` and it returns "—" / "—" / "£1,234.56".
 *
 * Decimals come over the wire as strings (backend Decimal → str). The
 * schema validates the pattern; render code converts only on display.
 */
import { z } from 'zod';

// Decimal-as-string for money. Backend serialises Decimal to string to avoid
// JS float drift. Up to 2 decimal places.
const moneyString = z
  .string()
  .regex(/^-?\d+(\.\d{1,2})?$/, 'money must be a decimal string with up to 2dp')
  .nullable();

const uuid = z.string().uuid();
const isoDateOrNull = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable();
const isoDateTimeOrNull = z.string().datetime({ offset: true }).nullable();

// ─── Enums ───────────────────────────────────────────────────────────
export const ActualStatusEnum = z.enum([
  'Draft', 'Posted', 'Paid', 'Disputed', 'Void',
]);

export const ActualSourceTypeEnum = z.enum([
  'Manual_Entry', 'Xero_Bill', 'Xero_Credit_Note', 'SC_Valuation',
  'Day_Rate_Timesheet', 'Expense_Claim', 'Journal', 'Internal_Recharge',
]);

// ─── Model ───────────────────────────────────────────────────────────
export const ActualSchema = z.object({
  id: uuid,
  project_id: uuid,
  budget_line_id: uuid,
  entity_id: uuid,
  source_type: ActualSourceTypeEnum,
  source_reference: z.string().nullable(),
  external_id: z.string().nullable(),
  transaction_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  posting_date: isoDateOrNull,
  description: z.string(),
  net_amount: moneyString,
  vat_amount: moneyString,
  gross_amount: moneyString,
  // Rates can be 3dp (e.g. CIS 12.345%) — no 2dp constraint.
  vat_rate_pct: z.string().nullable(),
  is_vat_recoverable: z.boolean(),
  currency: z.string().length(3),
  exchange_rate: z.string().nullable(),
  supplier_id: uuid.nullable(),
  supplier_name_snapshot: z.string(),
  supplier_invoice_ref: z.string().nullable(),
  is_cis_applicable: z.boolean(),
  retention_released: z.boolean(),
  linked_commitment_id: uuid.nullable(),
  related_subcontract_id: uuid.nullable(),
  is_reconciled_to_xero: z.boolean(),
  status: ActualStatusEnum,
  posted_at: isoDateTimeOrNull,
  paid_date: isoDateOrNull,
  payment_reference: z.string().nullable(),
  disputed_at: isoDateTimeOrNull,
  voided_at: isoDateTimeOrNull,
  created_at: isoDateTimeOrNull,
  updated_at: isoDateTimeOrNull,
  // Sensitive — present only when caller has actuals.view_sensitive
  cis_deduction_rate_pct: z.string().nullable().optional(),
  cis_labour_amount: moneyString.optional(),
  cis_materials_amount: moneyString.optional(),
  cis_deduction_amount: moneyString.optional(),
  retention_rate_pct: z.string().nullable().optional(),
  retention_amount: moneyString.optional(),
  retention_release_date: isoDateOrNull.optional(),
  reconciliation_variance: moneyString.optional(),
  dispute_reason: z.string().nullable().optional(),
  void_reason: z.string().nullable().optional(),
  ai_capture_metadata: z.record(z.unknown()).nullable().optional(),
});

export const ActualListResponseSchema = z.object({
  items: z.array(ActualSchema),
  count: z.number().int(),
  total: z.number().int(),
  limit: z.number().int().optional(),
  offset: z.number().int().optional(),
  // Present on /projects/:id/actuals only.
  project_id: uuid.optional(),
});

// ─── Change log ──────────────────────────────────────────────────────
export const ChangeLogEventSchema = z.object({
  id: uuid,
  actual_id: uuid,
  event_type: z.string(),
  actor_user_id: uuid.nullable(),
  event_payload: z.record(z.unknown()).nullable(),
  occurred_at: isoDateTimeOrNull,
});

export const ChangeLogResponseSchema = z.object({
  actual_id: uuid,
  items: z.array(ChangeLogEventSchema),
  count: z.number().int(),
});

// ─── Attachments ─────────────────────────────────────────────────────
export const AttachmentSchema = z.object({
  id: uuid,
  actual_id: uuid,
  original_filename: z.string(),
  file_type: z.string(),
  file_size_bytes: z.number().int(),
  source: z.enum(['Manual_Upload', 'Email_Capture', 'AI_Capture']),
  uploaded_by_user_id: uuid.nullable(),
  uploaded_at: isoDateTimeOrNull,
});

// ─── Request schemas — mirror backend Pydantic strictly ──────────────
export const CreateActualRequestSchema = z.object({
  project_id: uuid,
  budget_line_id: uuid,
  entity_id: uuid,
  source_type: ActualSourceTypeEnum,
  source_reference: z.string().max(10000).optional(),
  external_id: z.string().max(255).optional(),
  transaction_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  posting_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  description: z.string().min(1).max(10000),
  net_amount: z.string().regex(/^-?\d+(\.\d{1,2})?$/),
  vat_amount: z.string().regex(/^-?\d+(\.\d{1,2})?$/).default('0'),
  vat_rate_pct: z.string().regex(/^-?\d+(\.\d{1,3})?$/).default('20'),
  is_vat_recoverable: z.boolean().default(true),
  currency: z.string().length(3).default('GBP'),
  exchange_rate: z.string().optional(),
  supplier_id: uuid.optional(),
  supplier_name_snapshot: z.string().min(1).max(255),
  supplier_invoice_ref: z.string().max(100).optional(),
  is_cis_applicable: z.boolean().default(false),
  cis_deduction_rate_pct: z.string().optional(),
  cis_labour_amount: z.string().optional(),
  cis_materials_amount: z.string().optional(),
  retention_rate_pct: z.string().optional(),
  retention_amount: z.string().optional(),
  linked_commitment_id: uuid.optional(),
  related_subcontract_id: uuid.optional(),
});

export const MarkPaidRequestSchema = z.object({
  paid_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  payment_reference: z.string().min(1).max(255),
});

export const VoidActualRequestSchema = z.object({
  void_reason: z.string().min(3).max(10000),
});

export const DisputeActualRequestSchema = z.object({
  dispute_reason: z.string().min(3).max(10000),
});

export const UndisputeActualRequestSchema = z.object({
  notes: z.string().max(10000).optional(),
});

export const ReleaseRetentionRequestSchema = z.object({
  retention_release_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
});
