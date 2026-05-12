/**
 * LifecycleActions tests — status × perm × desktop gate matrix.
 */
import { screen } from '@testing-library/react';
import { LifecycleActions } from '../LifecycleActions';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { mockBudget, mockMe } from '../../../test/mocks/fixtures';
import { mockMatchMedia } from '../../../test/mockMatchMedia';

jest.mock('../../../context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('../../../hooks/budgets', () => {
  const stub = () => ({ mutate: jest.fn(), mutateAsync: jest.fn(), isPending: false });
  return {
    useActivateBudget: stub,
    useLockBudget: stub,
    useUnlockBudget: stub,
    useCloseBudget: stub,
    useCreateNewBudgetVersion: stub,
  };
});

const { useAuth } = require('../../../context/AuthContext');

const PM_PERMS    = ['budgets.view', 'budgets.edit', 'budgets.view_sensitive'];
const ADMIN_PERMS = [...PM_PERMS, 'budgets.admin'];

describe('LifecycleActions', () => {
  test('renders nothing on mobile (read-only floor)', () => {
    mockMatchMedia(false);
    useAuth.mockReturnValue({ me: mockMe(PM_PERMS) });
    const { container } = renderWithProviders(
      <LifecycleActions budget={mockBudget({ status: 'Draft' })} projectId="p" />,
    );
    expect(container.querySelector('[data-testid="lifecycle-actions"]')).toBeNull();
  });

  test('Activate button visible only when status=Draft', () => {
    useAuth.mockReturnValue({ me: mockMe(PM_PERMS) });
    renderWithProviders(
      <LifecycleActions budget={mockBudget({ status: 'Draft' })} projectId="p" />,
    );
    expect(screen.getByTestId('lifecycle-activate')).toBeInTheDocument();
  });

  test('Activate button hidden when status=Active', () => {
    useAuth.mockReturnValue({ me: mockMe(PM_PERMS) });
    renderWithProviders(
      <LifecycleActions budget={mockBudget({ status: 'Active' })} projectId="p" />,
    );
    expect(screen.queryByTestId('lifecycle-activate')).toBeNull();
    expect(screen.getByTestId('lifecycle-lock')).toBeInTheDocument();
  });

  test('Unlock button requires budgets.admin (PM cannot see it)', () => {
    useAuth.mockReturnValue({ me: mockMe(PM_PERMS) });
    renderWithProviders(
      <LifecycleActions budget={mockBudget({ status: 'Locked' })} projectId="p" />,
    );
    expect(screen.queryByTestId('lifecycle-unlock')).toBeNull();
    // PM still sees Close + NewVersion on Locked (both use budgets.edit).
    expect(screen.getByTestId('lifecycle-close')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-newver')).toBeInTheDocument();
  });

  test('Admin sees Unlock + Close + NewVersion on Locked status', () => {
    useAuth.mockReturnValue({ me: mockMe(ADMIN_PERMS) });
    renderWithProviders(
      <LifecycleActions budget={mockBudget({ status: 'Locked' })} projectId="p" />,
    );
    expect(screen.getByTestId('lifecycle-unlock')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-close')).toBeInTheDocument();
    expect(screen.getByTestId('lifecycle-newver')).toBeInTheDocument();
  });
});
