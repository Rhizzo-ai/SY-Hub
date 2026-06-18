/**
 * BudgetGridColumns — unbudgeted pill + gated clear button (B107 §3/§4,
 * §8.4 gating). We invoke the `line_description` column's cell renderer
 * directly with a minimal TanStack-style context, so we test the cell
 * gating without mounting the whole grid.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { makeColumns } from '@/components/budgets/grid/BudgetGridColumns';

function renderDescCell({ line, canClearUnbudgeted, floor = 1000 }) {
  const cols = makeColumns({
    costCodeMap: new Map(),
    canEdit: false,
    canViewSensitive: false,
    budgetId: 'b1',
    onOpenDrawer: () => {},
    floor,
    canClearUnbudgeted,
    onClearUnbudgeted: () => {},
  });
  const desc = cols.find((c) => c.id === 'line_description');
  return render(
    <table><tbody><tr><td>
      {desc.cell({ row: { original: line }, getValue: () => line.line_description })}
    </td></tr></tbody></table>,
  );
}

const blockingLine = {
  id: 'L1', isGroup: false, isItem: false, line_description: 'Demolition',
  is_unbudgeted: true, unbudgeted_cleared_at: null, committed_not_invoiced: '1500',
};
const flaggedLine = {
  id: 'L2', isGroup: false, isItem: false, line_description: 'Skips',
  is_unbudgeted: true, unbudgeted_cleared_at: null, committed_not_invoiced: '200',
};

describe('BudgetGridColumns — unbudgeted pill + clear gating', () => {
  test('blocking line shows the RED pill', () => {
    renderDescCell({ line: blockingLine, canClearUnbudgeted: true });
    expect(screen.getByTestId('unbudgeted-pill-blocking')).toBeInTheDocument();
  });

  test('clear button VISIBLE with permission on a blocking line', () => {
    renderDescCell({ line: blockingLine, canClearUnbudgeted: true });
    expect(screen.getByTestId('clear-unbudgeted-btn-L1')).toBeInTheDocument();
  });

  test('clear button HIDDEN without permission (pill still shows)', () => {
    renderDescCell({ line: blockingLine, canClearUnbudgeted: false });
    expect(screen.queryByTestId('clear-unbudgeted-btn-L1')).toBeNull();
    expect(screen.getByTestId('unbudgeted-pill-blocking')).toBeInTheDocument();
  });

  test('flagged (below floor) line shows AMBER pill and NO clear button', () => {
    renderDescCell({ line: flaggedLine, canClearUnbudgeted: true });
    expect(screen.getByTestId('unbudgeted-pill-flagged')).toBeInTheDocument();
    expect(screen.queryByTestId('clear-unbudgeted-btn-L2')).toBeNull();
  });
});
