// frontend/src/lib/schemas/__tests__/aiCapture-schemas.test.js — Chat 19C §R6.2
import {
  AICaptureJobSchema,
  PromoteCaptureToActualRequestSchema,
  DiscardCaptureRequestSchema,
  CaptureJobsListResponseSchema,
} from '@/lib/schemas/aiCapture';
import {
  makeAwaitingReviewJob, makeFailedJob, makeQueuedJob,
} from '@/test/mocks/fixtures';

describe('aiCapture schemas', () => {
  test('AICaptureJobSchema parses Awaiting_Review fixture', () => {
    expect(() => AICaptureJobSchema.parse(makeAwaitingReviewJob())).not.toThrow();
  });
  test('AICaptureJobSchema parses Failed fixture (last_error_message present)', () => {
    expect(() => AICaptureJobSchema.parse(makeFailedJob())).not.toThrow();
  });
  test('AICaptureJobSchema parses Queued (no extracted_data yet)', () => {
    expect(() => AICaptureJobSchema.parse(makeQueuedJob())).not.toThrow();
  });
  test('PromoteCaptureToActualRequestSchema rejects missing project_id', () => {
    const r = PromoteCaptureToActualRequestSchema.safeParse({
      budget_line_id: '00000000-0000-0000-0000-000000000001',
      entity_id:      '00000000-0000-0000-0000-000000000002',
      transaction_date: '2026-05-01',
      description: 'x',
      net_amount: '100.00',
      supplier_name_snapshot: 'Acme',
    });
    expect(r.success).toBe(false);
  });
  test('DiscardCaptureRequestSchema requires reason >= 1 char', () => {
    expect(DiscardCaptureRequestSchema.safeParse({ reason: '' }).success).toBe(false);
    expect(DiscardCaptureRequestSchema.safeParse({ reason: 'x' }).success).toBe(true);
  });
  test('CaptureJobsListResponseSchema parses empty list', () => {
    expect(() => CaptureJobsListResponseSchema.parse({
      items: [], count: 0, total: 0,
    })).not.toThrow();
  });
});
