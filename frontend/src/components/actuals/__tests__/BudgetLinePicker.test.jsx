/**
 * BudgetLinePicker tests (Chat 19B §R6).
 */
import { screen, fireEvent } from '@testing-library/react';
import { BudgetLinePicker } from '../BudgetLinePicker';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { mockBudget, mockLine, IDS } from '../../../test/mocks/fixtures';

jest.mock('../../../hooks/budgets', () => ({
  useProjectBudgets: jest.fn(),
  useBudget: jest.fn(),
}));
const { useProjectBudgets, useBudget } = require('../../../hooks/budgets');

describe('BudgetLinePicker', () => {
  beforeEach(() => jest.clearAllMocks());

  test('renders the empty state when no Active/Locked budget exists', () => {
    useProjectBudgets.mockReturnValue({ data: { items: [] }, isLoading: false });
    useBudget.mockReturnValue({ data: undefined, isLoading: false });
    renderWithProviders(
      <BudgetLinePicker projectId={IDS.PROJECT_ID} value={null} onChange={() => {}} />,
    );
    expect(screen.getByTestId('budget-line-picker-empty')).toBeInTheDocument();
  });

  test('renders the line dropdown when an Active budget has lines', () => {
    const budget = mockBudget({
      status: 'Active',
      is_current: true,
      lines: [
        mockLine({ id: IDS.LINE_ID_1, line_description: 'Concrete' }),
        mockLine({ id: IDS.LINE_ID_2, line_description: 'Steel' }),
      ],
    });
    useProjectBudgets.mockReturnValue({
      data: { items: [budget] }, isLoading: false,
    });
    useBudget.mockReturnValue({ data: budget, isLoading: false });
    renderWithProviders(
      <BudgetLinePicker projectId={IDS.PROJECT_ID} value={null} onChange={() => {}} />,
    );
    expect(screen.getByTestId('budget-line-picker')).toBeInTheDocument();
    expect(screen.getByText('Concrete')).toBeInTheDocument();
    expect(screen.getByText('Steel')).toBeInTheDocument();
  });

  test('selecting a line fires onChange with that UUID', () => {
    const budget = mockBudget({
      status: 'Active',
      is_current: true,
      lines: [mockLine({ id: IDS.LINE_ID_2, line_description: 'Steel' })],
    });
    useProjectBudgets.mockReturnValue({ data: { items: [budget] }, isLoading: false });
    useBudget.mockReturnValue({ data: budget, isLoading: false });
    const onChange = jest.fn();
    renderWithProviders(
      <BudgetLinePicker projectId={IDS.PROJECT_ID} value={null} onChange={onChange} />,
    );
    fireEvent.change(screen.getByRole('combobox'), { target: { value: IDS.LINE_ID_2 } });
    expect(onChange).toHaveBeenCalledWith(IDS.LINE_ID_2);
  });
});
