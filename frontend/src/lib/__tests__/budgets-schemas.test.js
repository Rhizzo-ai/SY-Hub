/**
 * Schema tests — Build Pack §R8.4 TestSensitiveGating + C2 fix.
 *
 * Ensures the Zod schema treats sensitive fields as
 * `.nullable().optional()` so backend-stripped payloads still parse.
 */
import {
  BudgetDetailSchema, BudgetLineSchema, BudgetStatus,
} from '../../lib/schemas/budgets';
import { mockBudget, mockLine, stripSensitive } from '../../test/mocks/fixtures';

describe('schemas/budgets — BudgetDetailSchema', () => {
  test('parses a full payload with every sensitive field present', () => {
    const result = BudgetDetailSchema.safeParse(mockBudget());
    expect(result.success).toBe(true);
  });

  test('parses a sensitive-stripped payload without errors (C2)', () => {
    const stripped = stripSensitive(mockBudget());
    const result = BudgetDetailSchema.safeParse(stripped);
    if (!result.success) {
      // surface the diagnostic at the assertion site
      // eslint-disable-next-line no-console
      console.error(JSON.stringify(result.error.format(), null, 2));
    }
    expect(result.success).toBe(true);
  });

  test('rejects an unknown status value', () => {
    const bad = { ...mockBudget(), status: 'Bogus' };
    const result = BudgetDetailSchema.safeParse(bad);
    expect(result.success).toBe(false);
  });
});

describe('schemas/budgets — BudgetLineSchema', () => {
  test('accepts a fully-populated line', () => {
    const result = BudgetLineSchema.safeParse(mockLine());
    expect(result.success).toBe(true);
  });
});

describe('schemas/budgets — BudgetStatus enum', () => {
  test('covers all five lifecycle statuses', () => {
    const opts = BudgetStatus.options;
    expect(opts).toEqual(
      expect.arrayContaining(['Draft', 'Active', 'Locked', 'Closed', 'Superseded']),
    );
  });
});
