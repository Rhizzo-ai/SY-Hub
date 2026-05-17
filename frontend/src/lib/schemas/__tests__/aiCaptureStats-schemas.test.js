// frontend/src/lib/schemas/__tests__/aiCaptureStats-schemas.test.js — Chat 20 §R5.2
import { CaptureStatsResponseSchema } from '@/lib/schemas/aiCaptureStats';

const validResponse = {
  period: { from_date: '2026-05-01', to_date: '2026-05-30', days: 30 },
  totals: {
    total_jobs: 12,
    total_cost_pence: 1234,
    avg_cost_pence: 103,
    total_prompt_tokens: 50000,
    total_completion_tokens: 12000,
  },
  daily_series: [
    { date: '2026-05-01', cost_pence: 100, job_count: 1 },
    { date: '2026-05-02', cost_pence: 0, job_count: 0 },
  ],
  by_status: [
    { status: 'Completed', cost_pence: 800, job_count: 9 },
    { status: 'Failed',    cost_pence: 300, job_count: 2 },
    { status: 'Discarded', cost_pence: 134, job_count: 1 },
  ],
};

describe('CaptureStatsResponseSchema', () => {
  test('parses valid response', () => {
    expect(() => CaptureStatsResponseSchema.parse(validResponse)).not.toThrow();
  });

  test('rejects negative cost_pence in totals', () => {
    const bad = { ...validResponse, totals: { ...validResponse.totals, total_cost_pence: -5 } };
    expect(CaptureStatsResponseSchema.safeParse(bad).success).toBe(false);
  });

  test('rejects unknown status in by_status', () => {
    const bad = {
      ...validResponse,
      by_status: [
        ...validResponse.by_status,
        { status: 'Queued', cost_pence: 0, job_count: 1 },
      ],
    };
    expect(CaptureStatsResponseSchema.safeParse(bad).success).toBe(false);
  });

  test('rejects non-integer cost_pence', () => {
    const bad = { ...validResponse, totals: { ...validResponse.totals, avg_cost_pence: 1.5 } };
    expect(CaptureStatsResponseSchema.safeParse(bad).success).toBe(false);
  });
});
