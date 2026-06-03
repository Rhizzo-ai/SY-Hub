/**
 * Build Pack 2.6-FIX (Chat 39) §R5 — B-DATA frontend test.
 *
 * <BudgetChangeDetail/> previously bound the cost-code cell to
 * `bl?.cost_code` — a field the backend never emits. The Build Pack
 * §R2 B-DATA fix routes the lookup through ``useCostCodes`` +
 * ``buildCostCodeMap`` exactly like ``BudgetGridColumns`` already
 * does. This test pins that resolution path.
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
jest.mock('../../../hooks/costCodes', () => ({
  useCostCodes: jest.fn(),
  buildCostCodeMap: jest.requireActual('../../../hooks/costCodes')
    .buildCostCodeMap,
}));
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
const { useCostCodes } = require('../../../hooks/costCodes');

function bcrFixture(overrides = {}) {
  return {
    id: 'bcr-1',
    reference: 'BCR-001',
    title: 'Test BCR',
    status: 'Draft',
    change_type: 'Adjustment',
    budget_id: IDS.BUDGET_ID,
    net_impact: '0',
    lines: [{ id: 'ln-1', budget_line_id: IDS.LINE_ID_1, delta: '1000' }],
    created_at: '2026-02-01T00:00:00Z',
    ...overrides,
  };
}

describe('<BudgetChangeDetail/> — Chat 39 cost-code resolution (B-DATA)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useAuth.mockReturnValue({
      me: mockMe([
        'budget_changes.view', 'budget_changes.create',
        'budget_changes.edit', 'budget_changes.submit',
      ]),
    });
  });

  test('resolves cost code via the cost-code map', () => {
    const costCodeId = 'cc-001';
    const line = mockLine({
      id: IDS.LINE_ID_1,
      cost_code_id: costCodeId,
      line_description: 'Concrete works',
      display_order: 0,
    });
    useBCR.mockReturnValue({
      data: bcrFixture(),
      isLoading: false,
      isError: false,
    });
    useBudget.mockReturnValue({
      data: {
        id: IDS.BUDGET_ID,
        project_id: IDS.PROJECT_ID,
        lines: [line],
      },
    });
    // Cost-code map carries the human-readable code keyed by
    // cost_code_id. Mirrors the production buildCostCodeMap key.
    useCostCodes.mockReturnValue({
      data: [
        { id: 'mapping-1', cost_code_id: costCodeId,
          code: 'CON-001', label: 'Concrete' },
      ],
    });

    renderWithProviders(<BudgetChangeDetail />);
    // The detail cell renders the resolved cost code, not '—'.
    expect(screen.getByText('CON-001')).toBeInTheDocument();
  });
});
