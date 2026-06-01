/**
 * <BudgetChangeDetail/> tests — Build Pack 2.6-FE-fix §R5.
 *
 * Asserts the fixes for the two defects affecting this page:
 *  - Bug 1: the detail page mounts without ReferenceError
 *           (DialogDescription is imported).
 *  - Bug 3: the detail line table renders the line label using
 *           `line_description` (the backend field) and falls
 *           back to `Line ${display_order ?? id.slice(0,8)}` when
 *           the description is missing.
 *
 * Note: the previous (pre-2.6-FE-fix) detail page read `bl.description`,
 * which the backend never emits, so every row collapsed to '(unlabelled)'.
 */
import { screen } from '@testing-library/react';
import BudgetChangeDetail from '../BudgetChangeDetail';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { mockLine, mockMe, IDS } from '../../../test/mocks/fixtures';

jest.mock('../../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../hooks/budgetChanges', () => ({
  useBCR: jest.fn(),
  usePatchBCR: () => ({ mutateAsync: jest.fn(), isPending: false }),
  useBCRTransition: () => ({ mutateAsync: jest.fn(), isPending: false }),
}));
jest.mock('../../../hooks/budgets', () => ({ useBudget: jest.fn() }));
jest.mock('../../../hooks/systemConfig', () => ({
  useBudgetSelfApprovalThreshold: () => ({ threshold: 10000 }),
}));
jest.mock('react-router-dom', () => {
  const actual = jest.requireActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ bcrId: 'bcr-1' }),
  };
});

const { useAuth } = require('../../../context/AuthContext');
const { useBCR } = require('../../../hooks/budgetChanges');
const { useBudget } = require('../../../hooks/budgets');

function bcrFixture(overrides = {}) {
  return {
    id: 'bcr-1',
    reference: 'BCR-001',
    title: 'Test BCR',
    status: 'Draft',
    change_type: 'Adjustment',
    budget_id: IDS.BUDGET_ID,
    net_impact: '0',
    lines: [],
    created_at: '2026-02-01T00:00:00Z',
    ...overrides,
  };
}

describe('<BudgetChangeDetail/> — 2.6-FE-fix', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({
      me: mockMe([
        'budget_changes.view', 'budget_changes.create',
        'budget_changes.edit', 'budget_changes.submit',
      ]),
    });
  });

  test('Bug 1: page mounts without ReferenceError (DialogDescription imported)', () => {
    useBCR.mockReturnValue({
      data: bcrFixture(), isLoading: false, isError: false,
    });
    useBudget.mockReturnValue({ data: { id: IDS.BUDGET_ID, lines: [] } });
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
    renderWithProviders(<BudgetChangeDetail />);
    expect(screen.getByTestId('bcr-detail')).toBeInTheDocument();
    const refErrors = spy.mock.calls
      .flat()
      .filter((arg) => typeof arg === 'string' && arg.includes('ReferenceError'));
    expect(refErrors).toEqual([]);
    spy.mockRestore();
  });

  test('Bug 3: detail line table uses line_description for labels', () => {
    const line = mockLine({
      id: IDS.LINE_ID_1,
      line_description: 'Concrete works',
      display_order: 0,
    });
    useBCR.mockReturnValue({
      data: bcrFixture({
        lines: [{ id: 'ln-1', budget_line_id: IDS.LINE_ID_1, delta: '1000' }],
      }),
      isLoading: false,
      isError: false,
    });
    useBudget.mockReturnValue({
      data: { id: IDS.BUDGET_ID, lines: [line] },
    });
    renderWithProviders(<BudgetChangeDetail />);
    expect(screen.getByText('Concrete works')).toBeInTheDocument();
  });

  test('Bug 3: detail line label falls back to "Line ${display_order}" when description is null', () => {
    const line = mockLine({
      id: IDS.LINE_ID_1,
      line_description: null,
      display_order: 4,
    });
    useBCR.mockReturnValue({
      data: bcrFixture({
        lines: [{ id: 'ln-1', budget_line_id: IDS.LINE_ID_1, delta: '1000' }],
      }),
      isLoading: false,
      isError: false,
    });
    useBudget.mockReturnValue({
      data: { id: IDS.BUDGET_ID, lines: [line] },
    });
    renderWithProviders(<BudgetChangeDetail />);
    expect(screen.getByText('Line 4')).toBeInTheDocument();
  });
});
