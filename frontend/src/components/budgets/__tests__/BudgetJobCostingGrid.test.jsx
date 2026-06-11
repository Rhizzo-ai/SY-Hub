/**
 * BudgetJobCostingGrid — component tests (B88 Pack 2 §R7.2 / Gate 2).
 *
 * Covers:
 *   - renders groups / subgroups / lines from a mocked grid payload
 *   - collapse / expand toggles row visibility
 *   - heat-map class applied per variance_status
 *   - column picker shows / hides + persists to localStorage
 *   - Tier-1-only columns absent on construction-scope payloads
 *   - empty state
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BudgetJobCostingGrid } from '@/components/budgets/BudgetJobCostingGrid';

jest.mock('@/hooks/budgets', () => ({
  useBudgetGrid: jest.fn(),
}));
import { useBudgetGrid } from '@/hooks/budgets';

function wrap(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>{ui}</QueryClientProvider>,
  );
}

function mockResp({ scope = 'full', withSubgroup = true, withLine = true,
                    varianceStatus = 'Green', tier1Allocations = false } = {}) {
  const lines = withLine ? [{
    id: 'line-1',
    cost_code_id: 'cc-1',
    cost_code: { id: 'cc-1', code: 'SUB-01', name: 'Demolition' },
    line_description: 'Test line',
    entity_id: 'ent-1',
    original_budget: '1000.00',
    approved_changes: '0.00',
    current_budget: '1000.00',
    committed_value: '0.00',
    invoiced_against_commitment: '0.00',
    committed_not_invoiced: '0.00',
    actuals_to_date: '100.00',
    actuals_this_period: '0.00',
    forecast_to_complete: '900.00',
    forecast_final_cost: '1000.00',
    variance_value: '0.00',
    variance_pct: '0.000',
    variance_status: varianceStatus,
    percentage_complete: '10.00',
    is_contingency: false,
    is_locked: false,
    requires_attention: false,
    display_order: 0,
    ...(tier1Allocations
      ? { _allocated_sale_price_provisional: '2500.00' }
      : {}),
  }] : [];
  const subgroup = withSubgroup ? {
    section_id: 'sg-1',
    code: '4.00',
    name: 'Facilitating Works',
    display_order: 1,
    included_in_construction_scope: true,
    subtotals: {
      current_budget: '1000.00',
      actuals_to_date: '100.00',
      forecast_final_cost: '1000.00',
      variance_value: '0.00',
      variance_pct: '0.000',
      variance_status: varianceStatus,
    },
    lines,
  } : null;
  return {
    budget: {
      id: 'b1', project_id: 'p1', version_number: 1, version_label: 'v1',
      is_current: true, status: 'Active', scope,
      totals: {
        current_budget: '1000.00',
        actuals_to_date: '100.00',
        forecast_final_cost: '1000.00',
        variance_value: '0.00',
        variance_pct: '0.000',
        variance_status: varianceStatus,
      },
    },
    groups: subgroup ? [{
      section_id: 'g-4',
      code: '4',
      name: 'Construction',
      display_order: 4,
      included_in_construction_scope: true,
      subtotals: subgroup.subtotals,
      subgroups: [subgroup],
      lines: [],
    }] : [],
  };
}

beforeEach(() => {
  useBudgetGrid.mockReset();
  localStorage.clear();
});

describe('BudgetJobCostingGrid', () => {
  test('renders groups, subgroups and lines from grid payload', () => {
    useBudgetGrid.mockReturnValue({ data: mockResp(), isLoading: false });
    wrap(<BudgetJobCostingGrid budgetId="b1" />);
    expect(screen.getByTestId('budget-grid')).toBeInTheDocument();
    expect(screen.getByTestId('budget-grid-group-g-4')).toBeInTheDocument();
    expect(screen.getByTestId('budget-grid-group-sg-1')).toBeInTheDocument();
    expect(screen.getByTestId('budget-grid-line-line-1')).toBeInTheDocument();
    expect(screen.getByTestId('budget-grid-totals')).toBeInTheDocument();
  });

  test('collapse toggle hides the children', () => {
    useBudgetGrid.mockReturnValue({ data: mockResp(), isLoading: false });
    wrap(<BudgetJobCostingGrid budgetId="b1" />);
    // Line is visible by default (groups default-open).
    expect(screen.getByTestId('budget-grid-line-line-1')).toBeInTheDocument();
    // Collapse the parent group.
    fireEvent.click(screen.getByTestId('budget-grid-group-toggle-g-4'));
    expect(screen.queryByTestId('budget-grid-line-line-1')).not.toBeInTheDocument();
  });

  test('heat-map class applied to variance cells per variance_status', () => {
    useBudgetGrid.mockReturnValue({
      data: mockResp({ varianceStatus: 'Red' }),
      isLoading: false,
    });
    wrap(<BudgetJobCostingGrid budgetId="b1" />);
    const cell = screen.getByTestId('budget-grid-cell-line-1-variance_value');
    expect(cell.className).toMatch(/bg-rose-50/);
  });

  test('column picker hides a column and persists to localStorage', () => {
    useBudgetGrid.mockReturnValue({ data: mockResp(), isLoading: false });
    wrap(<BudgetJobCostingGrid budgetId="b1" />);
    expect(screen.getByTestId('budget-grid-cell-line-1-actuals_to_date'))
      .toBeInTheDocument();
    fireEvent.click(screen.getByTestId('budget-grid-column-picker-toggle'));
    const checkbox = screen.getByTestId('budget-grid-column-picker-actuals_to_date');
    fireEvent.click(checkbox);
    expect(screen.queryByTestId('budget-grid-cell-line-1-actuals_to_date'))
      .not.toBeInTheDocument();
    // Persisted under the scope-keyed storage key.
    const stored = JSON.parse(localStorage.getItem('sy-hub.budget-grid.columns.full'));
    expect(stored).not.toContain('actuals_to_date');
  });

  test('Tier-1-only columns absent on construction scope responses', () => {
    useBudgetGrid.mockReturnValue({
      data: mockResp({ scope: 'construction' }),
      isLoading: false,
    });
    wrap(<BudgetJobCostingGrid budgetId="b1" scope="construction" />);
    fireEvent.click(screen.getByTestId('budget-grid-column-picker-toggle'));
    expect(
      screen.queryByTestId('budget-grid-column-picker-_allocated_sale_price_provisional')
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('budget-grid-column-picker-_projected_profit')
    ).not.toBeInTheDocument();
  });

  test('scope badge labels match the response scope', () => {
    useBudgetGrid.mockReturnValue({
      data: mockResp({ scope: 'construction' }),
      isLoading: false,
    });
    wrap(<BudgetJobCostingGrid budgetId="b1" scope="construction" />);
    expect(screen.getByTestId('budget-grid-scope-badge'))
      .toHaveTextContent('Construction Budget');
  });

  test('empty state when groups is empty', () => {
    useBudgetGrid.mockReturnValue({
      data: { budget: { scope: 'construction', totals: {} }, groups: [] },
      isLoading: false,
    });
    wrap(<BudgetJobCostingGrid budgetId="b1" />);
    expect(screen.getByTestId('budget-grid-empty')).toBeInTheDocument();
  });

  test('loading state renders the skeleton', () => {
    useBudgetGrid.mockReturnValue({ data: undefined, isLoading: true });
    wrap(<BudgetJobCostingGrid budgetId="b1" />);
    expect(screen.getByTestId('budget-grid-loading')).toBeInTheDocument();
  });

  test('projected profit + margin computed when allocation present (full scope)', () => {
    useBudgetGrid.mockReturnValue({
      data: mockResp({ tier1Allocations: true }),
      isLoading: false,
    });
    wrap(<BudgetJobCostingGrid budgetId="b1" />);
    // Enable the projected profit column from the picker first.
    fireEvent.click(screen.getByTestId('budget-grid-column-picker-toggle'));
    fireEvent.click(screen.getByTestId('budget-grid-column-picker-_projected_profit'));
    const cell = screen.getByTestId('budget-grid-cell-line-1-_projected_profit');
    // 2500 (alloc) − 1000 (ffc) = £1,500.00
    expect(cell).toHaveTextContent('£1,500.00');
  });
});
