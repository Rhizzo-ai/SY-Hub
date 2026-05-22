/**
 * R7.1 — Project-Detail budgets tab-link tests.
 *
 * Asserts:
 *   1. Tab renders for users with `budgets.view`.
 *   2. Tab is hidden for users without `budgets.view` (and not super-admin).
 *   3. Super-admin bypass mirrors the actuals tab pattern.
 *   4. Sibling tabs (cost-codes, appraisals, actuals) still render.
 */
import { screen, waitFor } from '@testing-library/react';
import ProjectDetail from '../ProjectDetail';
import { renderWithProviders } from '../../test/renderWithProviders';
import { mockMe } from '../../test/mocks/fixtures';

jest.mock('../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../components/appraisal/NudgeBanner', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('../../lib/api', () => ({
  api: {
    get: jest.fn(),
    post: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
  },
}));
jest.mock('react-router-dom', () => {
  const actual = jest.requireActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: 'proj-1' }),
    useNavigate: () => jest.fn(),
  };
});

const { useAuth } = require('../../context/AuthContext');
const { api } = require('../../lib/api');

const PROJECT_FIXTURE = {
  id: 'proj-1',
  project_code: 'P-001',
  name: 'Test Project',
  current_stage: 'Lead',
  stage_entered_at: '2026-01-01T00:00:00Z',
  status: 'Active',
};


describe('ProjectDetail — R7.1 budgets tab-link', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    api.get.mockResolvedValue({ data: PROJECT_FIXTURE });
  });

  test('user with budgets.view sees the Budgets tab linked to /projects/:id/budgets', async () => {
    useAuth.mockReturnValue({ me: mockMe(['budgets.view']) });
    renderWithProviders(<ProjectDetail />);
    await waitFor(() => expect(screen.getByTestId('project-detail-page')).toBeInTheDocument());
    const link = screen.getByTestId('tab-budgets');
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/projects/proj-1/budgets');
    expect(link).toHaveTextContent(/budgets/i);
  });

  test('user without budgets.view (and not super-admin) does not see the Budgets tab', async () => {
    useAuth.mockReturnValue({ me: mockMe(['projects.view']) });
    renderWithProviders(<ProjectDetail />);
    await waitFor(() => expect(screen.getByTestId('project-detail-page')).toBeInTheDocument());
    expect(screen.queryByTestId('tab-budgets')).not.toBeInTheDocument();
  });

  test('super-admin sees Budgets tab even without explicit budgets.view perm', async () => {
    useAuth.mockReturnValue({
      me: { ...mockMe([]), is_super_admin: true },
    });
    renderWithProviders(<ProjectDetail />);
    await waitFor(() => expect(screen.getByTestId('project-detail-page')).toBeInTheDocument());
    expect(screen.getByTestId('tab-budgets')).toBeInTheDocument();
  });

  test('sibling tab-links (cost-codes, appraisals) still render alongside budgets', async () => {
    useAuth.mockReturnValue({ me: mockMe(['budgets.view', 'actuals.view']) });
    renderWithProviders(<ProjectDetail />);
    await waitFor(() => expect(screen.getByTestId('project-detail-page')).toBeInTheDocument());
    expect(screen.getByTestId('tab-cost-codes')).toBeInTheDocument();
    expect(screen.getByTestId('tab-appraisals')).toBeInTheDocument();
    expect(screen.getByTestId('tab-budgets')).toBeInTheDocument();
    expect(screen.getByTestId('tab-actuals')).toBeInTheDocument();
  });
});
