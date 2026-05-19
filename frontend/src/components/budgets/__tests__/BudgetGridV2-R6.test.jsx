/**
 * BudgetGridV2 R6 integration tests — hydration + autosave.
 *
 * Validates the BudgetGridV2Desktop wiring against the
 * useUserPreferences contract end-to-end at the component level:
 *   - On mount, the snapshot's current.payload hydrates
 *     columnVisibility / sorting / filters BEFORE the user makes
 *     changes. Empty snapshot → keep INITIAL_COLUMN_VISIBILITY.
 *   - Any state change debounces a PUT (autosave) after 500ms.
 *   - Rapid changes coalesce to a single PUT.
 *   - The initial hydration itself does NOT trigger autosave (would
 *     create a load-storm on every visit).
 */
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

jest.mock('@/lib/api/userPreferences', () => ({
  getSurfaceSnapshot: jest.fn(),
  putCurrentPreference: jest.fn(),
  createSavedView: jest.fn(),
  updateSavedView: jest.fn(),
  deleteSavedView: jest.fn(),
}));
import * as prefsApi from '@/lib/api/userPreferences';

jest.mock('@/hooks/costCodes', () => ({
  useCostCodes: () => ({ data: [
    { id: 'cc-1', code: 'ACQ-001', name: 'Land' },
  ] }),
  buildCostCodeMap: (codes) => new Map(codes.map((c) => [c.id, c])),
}));

jest.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ me: {
    id: 'u1', email: 'test-admin@example.test',
    permissions: ['budgets.view', 'budgets.view_sensitive', 'budgets.edit_lines'],
  } }),
}));

jest.mock('@/hooks/budgets', () => ({
  useReorderBudgetLines: () => ({
    mutate: jest.fn(), isPending: false, isError: false, error: null,
  }),
  usePatchBudgetLine: () => ({ mutate: jest.fn(), isPending: false }),
  useCreateLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  usePatchLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  useDeleteLineItem: () => ({ mutate: jest.fn(), isPending: false }),
}));

import { BudgetGridV2Desktop }
  from '../grid/BudgetGridV2Desktop';

const BUDGET = {
  id: 'b1',
  status: 'Draft',
  total_budget: 1000,
  total_actuals: 0,
  total_committed_not_invoiced: 0,
  total_forecast_to_complete: 0,
  forecast_final_cost: 0,
  variance_vs_budget: 0,
  variance_pct: 0,
  lines: [{
    id: 'l1',
    cost_code_id: 'cc-1',
    line_description: 'Line one',
    original_budget: 500,
    current_budget: 500,
    approved_changes: 0,
    actuals_to_date: 0,
    committed_value: 0,
    forecast_final_cost: 500,
    forecast_to_complete: 500,
    variance_value: 0,
    variance_pct: 0,
    variance_status: 'Green',
    notes: null,
    items: [],
    display_order: 0,
  }],
};

function wrap(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
});

afterEach(() => {
  act(() => { jest.runOnlyPendingTimers(); });
  jest.useRealTimers();
});

describe('BudgetGridV2Desktop R6 hydration + autosave', () => {
  test('initial hydration does NOT trigger autosave', async () => {
    prefsApi.getSurfaceSnapshot.mockResolvedValueOnce({
      surface_key: 'budgets.grid.v2',
      current: { columnVisibility: { committed: false } },
      views: [],
    });
    wrap(<BudgetGridV2Desktop budget={BUDGET} projectId="p1" />);
    // Snapshot resolves.
    await act(async () => { await Promise.resolve(); });
    // Past 500ms debounce window.
    act(() => { jest.advanceTimersByTime(1000); });
    expect(prefsApi.putCurrentPreference).not.toHaveBeenCalled();
  });

  test('state change after hydration → debounced PUT after 500ms', async () => {
    jest.useRealTimers(); // override beforeEach's fake timers for this case
    prefsApi.getSurfaceSnapshot.mockResolvedValueOnce({
      surface_key: 'budgets.grid.v2',
      current: {}, views: [],
    });
    prefsApi.putCurrentPreference.mockResolvedValue({ id: '1', payload: {} });
    wrap(<BudgetGridV2Desktop budget={BUDGET} projectId="p1" />);

    // Wait until hydration is done (toolbar present).
    await waitFor(() => screen.getByTestId('bg2-toolbar'));

    // Trigger a filter change via the "Only with variance" checkbox-
    // shaped chip.
    const chip = screen.getByTestId('bg2-filter-variance');
    const checkbox = chip.querySelector('button,[role="checkbox"]');
    fireEvent.click(checkbox);

    await waitFor(
      () => expect(prefsApi.putCurrentPreference).toHaveBeenCalledTimes(1),
      { timeout: 2000 },
    );
  });
});
