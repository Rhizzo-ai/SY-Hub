/**
 * LineDrawer — FTC method gate regression lock.
 *
 * B88 Pack 2 Gate 2 re-eyeball Defect 2: the legacy drawer hid
 * `ftc_method` behind a `view_sensitive` gate ("hidden — request
 * elevated access"). Per Build Pack §R5 / D4, `ftc_method` is NOT in
 * the sensitive set — it has always been returned by the backend to
 * every caller. The same applies to the Manual FTC value input.
 *
 * This test confirms: ftc_method renders for callers WITHOUT
 * `budgets.view_sensitive` AND for those WITH it; only the standard
 * edit gating (`budgets.edit` + budget status + desktop) disables
 * the controls.
 */
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LineDrawer } from '@/components/budgets/LineDrawer';

// Hard mocks to keep the test focused on the FTC gate.
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('@/lib/useIsDesktop', () => ({
  useIsDesktop: () => true,
}));
jest.mock('@/hooks/budgets', () => ({
  usePatchBudgetLine: () => ({ mutateAsync: jest.fn(), isPending: false }),
  useCreateLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  usePatchLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  useDeleteLineItem: () => ({ mutateAsync: jest.fn(), isPending: false }),
}));
jest.mock('@/hooks/costCodes', () => ({
  useCostCodes: () => ({ data: [], isLoading: false }),
  buildCostCodeMap: () => new Map(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
import { useAuth } from '@/context/AuthContext';

function wrap(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const ACTIVE_BUDGET = {
  id: 'b1',
  project_id: 'p1',
  status: 'Active',
  lines: [{
    id: 'line-1',
    line_description: 'Test line',
    cost_code_id: 'cc-1',
    notes: null,
    ftc_method: 'Manual',
    forecast_to_complete: '100.00',
    percentage_complete: null,
    updated_at: '2026-02-01T00:00:00Z',
  }],
};

beforeEach(() => {
  useAuth.mockReset();
});

describe('LineDrawer — FTC method gate (B88 Pack 2 Defect 2)', () => {
  test('FTC method visible without budgets.view_sensitive', () => {
    useAuth.mockReturnValue({
      me: { permissions: ['budgets.view', 'budgets.edit'] }, // no sensitive
    });
    wrap(
      <LineDrawer
        budget={ACTIVE_BUDGET}
        projectId="p1"
        lineId="line-1"
        focus={null}
        onClose={() => {}}
      />,
    );
    expect(screen.getByTestId('line-drawer-ftc-method')).toBeInTheDocument();
    // Manual FTC input also visible (was gated on canSensitive).
    expect(screen.getByTestId('line-drawer-ftc-value')).toBeInTheDocument();
    // The stale "(hidden — request elevated access)" label is gone.
    expect(screen.queryByText(/request elevated access/i))
      .not.toBeInTheDocument();
  });

  test('FTC method visible with budgets.view_sensitive', () => {
    useAuth.mockReturnValue({
      me: {
        permissions: [
          'budgets.view', 'budgets.edit', 'budgets.view_sensitive',
        ],
      },
    });
    wrap(
      <LineDrawer
        budget={ACTIVE_BUDGET}
        projectId="p1"
        lineId="line-1"
        focus={null}
        onClose={() => {}}
      />,
    );
    expect(screen.getByTestId('line-drawer-ftc-method')).toBeInTheDocument();
    expect(screen.getByTestId('line-drawer-ftc-value')).toBeInTheDocument();
  });
});
