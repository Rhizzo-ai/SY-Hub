/**
 * BudgetLineage tests — prev/next computed from sibling list (E10).
 */
import { screen } from '@testing-library/react';
import { BudgetLineage } from '../BudgetLineage';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { mockBudget, IDS } from '../../../test/mocks/fixtures';

jest.mock('../../../hooks/budgets', () => ({
  useProjectBudgets: jest.fn(),
}));

const { useProjectBudgets } = require('../../../hooks/budgets');

const v1 = { id: 'v1-id', version_number: 1, status: 'Superseded' };
const v2 = { id: 'v2-id', version_number: 2, status: 'Superseded' };
const v3 = { id: 'v3-id', version_number: 3, status: 'Draft', is_current: true };

describe('BudgetLineage', () => {
  test('renders nothing when only one budget in project', () => {
    useProjectBudgets.mockReturnValue({ data: { items: [v1] } });
    const { container } = renderWithProviders(
      <BudgetLineage budget={mockBudget({ id: 'v1-id', version_number: 1 })}
                     projectId={IDS.PROJECT_ID} />,
    );
    expect(container.querySelector('[data-testid="budget-lineage"]')).toBeNull();
  });

  test('renders only prev link when on the latest version', () => {
    useProjectBudgets.mockReturnValue({ data: { items: [v1, v2, v3] } });
    renderWithProviders(
      <BudgetLineage budget={mockBudget({ id: 'v3-id', version_number: 3 })}
                     projectId={IDS.PROJECT_ID} />,
    );
    expect(screen.getByTestId('budget-lineage-prev')).toHaveTextContent('v2');
    expect(screen.queryByTestId('budget-lineage-next')).toBeNull();
  });

  test('renders only next link when on the earliest version', () => {
    useProjectBudgets.mockReturnValue({ data: { items: [v1, v2, v3] } });
    renderWithProviders(
      <BudgetLineage budget={mockBudget({ id: 'v1-id', version_number: 1 })}
                     projectId={IDS.PROJECT_ID} />,
    );
    expect(screen.getByTestId('budget-lineage-next')).toHaveTextContent('v2');
    expect(screen.queryByTestId('budget-lineage-prev')).toBeNull();
  });

  test('renders both prev and next when budget is in the middle (sibling-present case)', () => {
    useProjectBudgets.mockReturnValue({ data: { items: [v1, v2, v3] } });
    renderWithProviders(
      <BudgetLineage budget={mockBudget({ id: 'v2-id', version_number: 2 })}
                     projectId={IDS.PROJECT_ID} />,
    );
    expect(screen.getByTestId('budget-lineage-prev')).toHaveTextContent('v1');
    expect(screen.getByTestId('budget-lineage-next')).toHaveTextContent('v3');
  });
});
