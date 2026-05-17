// frontend/src/lib/schemas/aiCapture.js — Chat 19C §R1.1
//
// Zod schemas mirroring the backend `_serialise_job` shape (router
// ai_capture.py) and the request payloads (PromoteCaptureToActualRequest,
// DiscardCaptureRequest, RetryCaptureRequest in app/schemas/actuals.py).
//
// Owns the AI_CAPTURE_STATUSES enum that the badge + capability layer
// keys on so a future status addition only needs editing here.
import { z } from 'zod';

// Status enum — mirrors backend AI_CAPTURE_STATUSES tuple
export const AI_CAPTURE_STATUSES = [
  'Queued',
  'Extracting',
  'Awaiting_Review',
  'Completed',
  'Failed',
  'Discarded',
];

export const CaptureStatusSchema = z.enum(AI_CAPTURE_STATUSES);

// AI's invoice extraction payload (JSONB on the job row)
export const ExtractedDataSchema = z.object({
  supplier_name: z.string().nullable().optional(),
  supplier_invoice_ref: z.string().nullable().optional(),
  invoice_date: z.string().nullable().optional(), // YYYY-MM-DD
  description: z.string().nullable().optional(),
  net_amount: z.string().nullable().optional(),    // decimal-as-string
  vat_amount: z.string().nullable().optional(),
  gross_amount: z.string().nullable().optional(),
  vat_rate_pct: z.string().nullable().optional(),
}).nullable().optional();

// Per-field confidence + overall (JSONB on the job row)
export const ConfidenceScoresSchema = z.object({
  supplier_name: z.number().min(0).max(1).nullable().optional(),
  supplier_invoice_ref: z.number().min(0).max(1).nullable().optional(),
  invoice_date: z.number().min(0).max(1).nullable().optional(),
  net_amount: z.number().min(0).max(1).nullable().optional(),
  vat_amount: z.number().min(0).max(1).nullable().optional(),
  gross_amount: z.number().min(0).max(1).nullable().optional(),
  overall: z.number().min(0).max(1).nullable().optional(),
}).nullable().optional();

// Full job shape — matches `_serialise_job` in backend router
export const AICaptureJobSchema = z.object({
  id: z.string().uuid(),
  inbound_email_message_id: z.string().uuid(),
  attachment_path: z.string(),
  status: CaptureStatusSchema,
  attempts: z.number().int().nonnegative(),
  last_attempted_at: z.string().nullable(),
  last_error_message: z.string().nullable(),
  extracted_data: ExtractedDataSchema,
  confidence_scores: ConfidenceScoresSchema,
  suggested_entity_id: z.string().uuid().nullable(),
  suggested_project_id: z.string().uuid().nullable(),
  suggested_cost_code_id: z.string().uuid().nullable(),
  target_actual_id: z.string().uuid().nullable(),
  model_used: z.string().nullable(),
  prompt_tokens: z.number().int().nullable(),
  completion_tokens: z.number().int().nullable(),
  cost_pence: z.number().int().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const CaptureJobsListResponseSchema = z.object({
  items: z.array(AICaptureJobSchema),
  count: z.number().int(),
  total: z.number().int(),
});

// ---- Request schemas ----

// Mirrors backend PromoteCaptureToActualRequest exactly.
// CRITICAL: useForm.defaultValues MUST seed every field listed as required here.
// E8 lesson — non-negotiable. See §R3.2 I5.
export const PromoteCaptureToActualRequestSchema = z.object({
  project_id: z.string().uuid({ message: 'Project is required' }),
  budget_line_id: z.string().uuid({ message: 'Budget line is required' }),
  entity_id: z.string().uuid({ message: 'Entity is required' }),
  transaction_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, {
    message: 'Date must be YYYY-MM-DD',
  }),
  description: z.string().min(1, 'Description required').max(10000),
  net_amount: z.string().regex(/^-?\d+(\.\d{1,2})?$/, {
    message: 'Net amount must be a decimal',
  }),
  vat_amount: z.string().regex(/^-?\d+(\.\d{1,2})?$/).default('0'),
  vat_rate_pct: z.string().regex(/^\d+(\.\d{1,2})?$/).default('20'),
  supplier_name_snapshot: z.string().min(1).max(255),
  supplier_invoice_ref: z.string().max(100).nullable().optional(),
  is_cis_applicable: z.boolean().default(false),
  cis_deduction_rate_pct: z.string().regex(/^\d+(\.\d{1,2})?$/).nullable().optional(),
  cis_labour_amount: z.string().regex(/^-?\d+(\.\d{1,2})?$/).nullable().optional(),
  cis_materials_amount: z.string().regex(/^-?\d+(\.\d{1,2})?$/).nullable().optional(),
  retention_rate_pct: z.string().regex(/^\d+(\.\d{1,2})?$/).nullable().optional(),
  retention_amount: z.string().regex(/^-?\d+(\.\d{1,2})?$/).nullable().optional(),
});

export const DiscardCaptureRequestSchema = z.object({
  reason: z.string().min(1, 'Reason is required').max(10000),
});

export const RetryCaptureRequestSchema = z.object({});

// List filters (URL params)
export const CaptureJobsListFiltersSchema = z.object({
  status: CaptureStatusSchema.nullable().optional(),
  limit: z.number().int().min(1).max(500).default(100),
  offset: z.number().int().nonnegative().default(0),
});
