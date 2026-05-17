// frontend/src/lib/schemas/aiCaptureStats.js — Chat 20 §R2.1
//
// Mirrors compute_capture_stats response shape exactly. All monetary
// fields are integer pence (NOT pounds, NOT floats). See L8 / D7.
import { z } from 'zod';

export const CaptureStatsPeriodSchema = z.object({
  from_date: z.string(),  // YYYY-MM-DD
  to_date: z.string(),
  days: z.number().int().positive(),
});

export const CaptureStatsTotalsSchema = z.object({
  total_jobs: z.number().int().nonnegative(),
  total_cost_pence: z.number().int().nonnegative(),
  avg_cost_pence: z.number().int().nonnegative(),
  total_prompt_tokens: z.number().int().nonnegative(),
  total_completion_tokens: z.number().int().nonnegative(),
});

export const CaptureStatsDailyPointSchema = z.object({
  date: z.string(),
  cost_pence: z.number().int().nonnegative(),
  job_count: z.number().int().nonnegative(),
});

export const CaptureStatsByStatusSchema = z.object({
  status: z.enum(['Completed', 'Failed', 'Discarded']),
  cost_pence: z.number().int().nonnegative(),
  job_count: z.number().int().nonnegative(),
});

export const CaptureStatsResponseSchema = z.object({
  period: CaptureStatsPeriodSchema,
  totals: CaptureStatsTotalsSchema,
  daily_series: z.array(CaptureStatsDailyPointSchema),
  by_status: z.array(CaptureStatsByStatusSchema),
});
