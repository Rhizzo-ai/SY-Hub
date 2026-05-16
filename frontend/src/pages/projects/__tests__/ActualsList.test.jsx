/**
 * ActualsList tests (Chat 19B §R6).
 */
import { screen } from '@testing-library/react';
import ActualsList from '../ActualsList';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { mockMe } from '../../../test/mocks/fixtures';

jest.mock('../../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../hooks/actuals', () => ({
  useProjectActuals: jest.fn(),
}));
jest.mock('../../../hooks/budgets', () => ({
  useProjectBudgets: jest.fn(),
  useBudget: jest.fn(),
}));
jest.mock('react-router-dom', () => {
  const actual = jest.requireActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ projectId: '22222222-2222-4222-8222-222222222222' }),
    useNavigate: () => jest.fn(),
  };
});
// CreateActualSheet pulls in react-dropzone + many subcomponents; stub it.
jest.mock('../../../components/actuals/CreateActualSheet', () => ({
  CreateActualSheet: () => null,
}));

const { useAuth } = require('../../../context/AuthContext');
const { useProjectActuals } = require('../../../hooks/actuals');
const { useProjectBudgets, useBudget } = require('../../../hooks/budgets');

describe('ActualsList', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useProjectBudgets.mockReturnValue({ data: { items: [] }, isLoading: false });
    useBudget.mockReturnValue({ data: undefined, isLoading: false });
  });

  test('no-perm user sees the no-permission notice', () => {
    useAuth.mockReturnValue({ me: mockMe([]) });
    useProjectActuals.mockReturnValue({ data: undefined, isLoading: false });
    renderWithProviders(<ActualsList />);
    expect(screen.getByTestId('actuals-list-no-perm')).toBeInTheDocument();
  });

  test('loading state renders "Loading actuals…"', () => {
    useAuth.mockReturnValue({ me: mockMe(['actuals.view']) });
    useProjectActuals.mockReturnValue({ data: undefined, isLoading: true });
    renderWithProviders(<ActualsList />);
    expect(screen.getByTestId('actuals-list-loading')).toBeInTheDocument();
  });

  test('empty state appears with a "Clear filters" link', () => {
    useAuth.mockReturnValue({ me: mockMe(['actuals.view']) });
    useProjectActuals.mockReturnValue({
      data: { items: [], count: 0, total: 0 }, isLoading: false,
    });
    renderWithProviders(<ActualsList />);
    expect(screen.getByTestId('actuals-empty-state')).toBeInTheDocument();
    expect(screen.getByText('Clear filters')).toBeInTheDocument();
  });
});
