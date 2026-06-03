/**
 * Build Pack 2.6-FIX (Chat 39) §R5 — B-CONTINGENCY frontend tests.
 *
 * The contingency-drawdown guard in <CreateBudgetChangeDialog/>
 * (lines 80-89 of CreateBudgetChangeDialog.jsx) was rejecting every
 * source line because the backend never serialised `is_contingency`,
 * so the lookup returned `undefined` and `!undefined === true`. The
 * Build Pack §R2 B-CONTINGENCY fix exposes `is_contingency` on the
 * API + frontend Zod schema; these tests pin the validator against
 * both branches so the bug cannot silently regress.
 */
import { validateBeforeSubmit } from '../CreateBudgetChangeDialog';

const baseLines = [
  // Source (negative) line — drawn from the contingency bucket.
  { budget_line_id: 'CTG-1', delta: '-5000' },
  // Target (positive) line — receives the drawdown.
  { budget_line_id: 'TGT-1', delta: '5000' },
];

describe('CreateBudgetChangeDialog — ContingencyDrawdown source-line guard', () => {
  test('accepts a contingency-flagged source line', () => {
    const budgetLinesById = {
      'CTG-1': { id: 'CTG-1', is_contingency: true },
      'TGT-1': { id: 'TGT-1', is_contingency: false },
    };
    const err = validateBeforeSubmit({
      changeType: 'ContingencyDrawdown',
      title: 'Test drawdown',
      lines: baseLines,
      budgetLinesById,
    });
    expect(err).toBeNull();
  });

  test('still rejects a non-contingency source line', () => {
    const budgetLinesById = {
      // Source line NOT flagged contingency — should be refused.
      'CTG-1': { id: 'CTG-1', is_contingency: false },
      'TGT-1': { id: 'TGT-1', is_contingency: false },
    };
    const err = validateBeforeSubmit({
      changeType: 'ContingencyDrawdown',
      title: 'Bad drawdown',
      lines: baseLines,
      budgetLinesById,
    });
    expect(err).toMatch(/contingency drawdown.*is_contingency/i);
  });
});
