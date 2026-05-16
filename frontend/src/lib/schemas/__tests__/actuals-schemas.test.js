/**
 * Zod schema tests — lib/schemas/actuals.js (Chat 19B §R6).
 */
import {
  ActualSchema, CreateActualRequestSchema, MarkPaidRequestSchema,
  VoidActualRequestSchema,
} from '../actuals';
import { makePostedActual } from '../../../test/mocks/fixtures';

describe('ActualSchema', () => {
  test('parses a minimal Posted-state response (no sensitive fields)', () => {
    const ok = ActualSchema.safeParse(makePostedActual());
    expect(ok.success).toBe(true);
  });

  test('parses a full sensitive response (CIS + retention amounts)', () => {
    const full = makePostedActual({
      is_cis_applicable: true,
      cis_deduction_rate_pct: '20',
      cis_labour_amount: '500.00',
      cis_materials_amount: '500.00',
      cis_deduction_amount: '100.00',
      retention_rate_pct: '5',
      retention_amount: '60.00',
      retention_release_date: null,
    });
    const ok = ActualSchema.safeParse(full);
    expect(ok.success).toBe(true);
  });

  test('rejects bad money string (3dp fails the 2dp pattern)', () => {
    const bad = makePostedActual({ net_amount: '12.345' });
    const result = ActualSchema.safeParse(bad);
    expect(result.success).toBe(false);
  });
});

describe('CreateActualRequestSchema', () => {
  test('requires description, net_amount, supplier_name_snapshot', () => {
    const result = CreateActualRequestSchema.safeParse({
      project_id: '22222222-2222-4222-8222-222222222222',
      budget_line_id: '33333333-3333-4333-8333-333333333333',
      entity_id: '44444444-4444-4444-8444-444444444444',
      source_type: 'Manual_Entry',
      transaction_date: '2026-05-15',
      // missing description / net_amount / supplier_name_snapshot
    });
    expect(result.success).toBe(false);
    const fields = result.error.issues.map((i) => i.path.join('.'));
    expect(fields).toEqual(
      expect.arrayContaining(['description', 'net_amount', 'supplier_name_snapshot']),
    );
  });
});

describe('MarkPaidRequestSchema', () => {
  test('requires both paid_date and payment_reference', () => {
    expect(MarkPaidRequestSchema.safeParse({ paid_date: '2026-05-20' }).success).toBe(false);
    expect(MarkPaidRequestSchema.safeParse({ payment_reference: 'BACS-1' }).success).toBe(false);
    expect(
      MarkPaidRequestSchema.safeParse({
        paid_date: '2026-05-20',
        payment_reference: 'BACS-1',
      }).success,
    ).toBe(true);
  });
});

describe('VoidActualRequestSchema', () => {
  test('requires void_reason ≥3 chars', () => {
    expect(VoidActualRequestSchema.safeParse({ void_reason: 'ab' }).success).toBe(false);
    expect(VoidActualRequestSchema.safeParse({ void_reason: 'oops' }).success).toBe(true);
    expect(VoidActualRequestSchema.safeParse({}).success).toBe(false);
  });
});
