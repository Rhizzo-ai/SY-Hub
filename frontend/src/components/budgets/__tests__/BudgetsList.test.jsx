/**
 * BudgetsList tests — empty state, no-perm, render with rows.
 */
import { screen } from '@testing-library/react';
import BudgetsList from '../../../pages/projects/BudgetsList';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { mockBudget, mockMe, IDS } from '../../../test/mocks/fixtures';
import { mockMatchMedia } from '../../../test/mockMatchMedia';

jest.mock('../../../context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('../../../hooks/budgets', () => ({
  useProjectBudgets: jest.fn(),
  useRefreshAttention: () => ({ mutate: jest.fn(), isPending: false }),
  useCreateBudgetFromAppraisal: () => ({
    mutate: jest.fn(),
    mutateAsync: jest.fn().mockResolvedValue({}),
    isPending: false,
  }),
}));
jest.mock('../../../hooks/appraisals', () => ({
  useApprovedAppraisals: () => ({ data: [], isLoading: false }),
}));
jest.mock('react-router-dom', () => {
  const actual = jest.requireActual('react-router-dom');
  return { ...actual, useParams: () => ({ projectId: '22222222-2222-2222-2222-222222222222' }) };
});

const { useAuth } = require('../../../context/AuthContext');
const { useProjectBudgets } = require('../../../hooks/budgets');

describe('BudgetsList', () => {
  test('blocks access when user lacks budgets.view (no-perm gate)', () => {
    useAuth.mockReturnValue({ me: mockMe([]) });
    useProjectBudgets.mockReturnValue({ data: undefined, isLoading: false });
    renderWithProviders(<BudgetsList />, { route: '/projects/p/budgets' });
    expect(screen.getByTestId('budgets-list-no-perm')).toBeInTheDocument();
  });

  test('renders empty state with brand-tealed Create button for an authed PM', () => {
    useAuth.mockReturnValue({
      me: mockMe(['budgets.view', 'budgets.create', 'budgets.edit']),
    });
    useProjectBudgets.mockReturnValue({
      data: { items: [] }, isLoading: false,
    });
    renderWithProviders(<BudgetsList />, { route: '/projects/p/budgets' });
    expect(screen.getByTestId('budgets-list-title')).toHaveTextContent('Budgets');
    expect(screen.getByTestId('budgets-table-empty')).toBeInTheDocument();
    const createBtn = screen.getByTestId('budgets-create-button');
    expect(createBtn).toBeInTheDocument();
    expect(createBtn.className).toMatch(/bg-sy-teal/);
    expect(createBtn.className).toMatch(/hover:brightness-110/);
    expect(createBtn.className).not.toMatch(/-hover/);
  });

  test('renders table with status badges per row', () => {
    useAuth.mockReturnValue({ me: mockMe(['budgets.view']) });
    useProjectBudgets.mockReturnValue({
      data: { items: [mockBudget({ id: IDS.BUDGET_ID, status: 'Active' })] },
      isLoading: false,
    });
    renderWithProviders(<BudgetsList />, { route: '/projects/p/budgets' });
    expect(screen.getByTestId('budgets-table')).toBeInTheDocument();
    expect(screen.getByTestId('budget-status-badge-Active')).toBeInTheDocument();
  });

  test('hides create button on mobile viewport', () => {
    mockMatchMedia(false);
    useAuth.mockReturnValue({
      me: mockMe(['budgets.view', 'budgets.create', 'budgets.edit']),
    });
    useProjectBudgets.mockReturnValue({ data: { items: [] }, isLoading: false });
    renderWithProviders(<BudgetsList />, { route: '/projects/p/budgets' });
    // The mobile banner appears, and the create button (gated behind md:flex)
    // is not visible. The data-testid is unconditionally rendered in markup,
    // but the parent has `hidden md:flex` so it's display:none on mobile.
    // We assert on the canCreate-gated render (which only fires on desktop).
    expect(screen.getByTestId('budgets-list-mobile-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('budgets-create-button')).toBeNull();
  });
});
