/**
 * BudgetGridV2 — on-screen cost-code rendering pin (§R7.5 follow-up).
 *
 * The gap exposed by the §R7 operator spot-check: there was no Jest
 * test asserting that the visible Cost-code column actually carries
 * the resolved code label in rendered rows (not just headers and
 * not just inside CSV exports). The CSV-output pins didn't catch
 * on-screen rendering failure modes.
 *
 * This file pins:
 *   1. Production-shape cost-codes payload (rows carry BOTH `id`
 *      mapping-pk AND `cost_code_id` FK) — labels render in the rows
 *      keyed by `cost_code_id`.
 *   2. Test-fixture-shape cost-codes payload (rows carry only `id`,
 *      no `cost_code_id`) — labels still render because
 *      buildCostCodeMap falls back to `id`. Keeps existing component
 *      tests green.
 *   3. Unknown FK → cell renders the `—` placeholder, NOT the raw
 *      UUID. (Matches the on-screen behaviour the operator confirmed
 *      during R3.)
 *
 * Why fixed-data shapes for both rows AND map: production
 * `/api/projects/.../cost-codes` returns `ProjectCostCodeRead` whose
 * `id` is the project_cost_codes mapping-pk and `cost_code_id` is the
 * FK that `budget_lines.cost_code_id` targets. The map MUST be keyed
 * by `cost_code_id` for the cell renderer to resolve correctly.
 * Future_Tasks §11 documents this in detail.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

jest.mock('@/lib/api/userPreferences', () => ({
  getSurfaceSnapshot: jest.fn().mockResolvedValue({
    surface_key: 'budgets.grid.v2', current: {}, views: [],
  }),
  putCurrentPreference: jest.fn().mockResolvedValue({ id: '1', payload: {} }),
  createSavedView: jest.fn(),
  updateSavedView: jest.fn(),
  deleteSavedView: jest.fn(),
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

// Configurable cost-codes mock: tests set the rows + then import the
// component (one mock value per test via the helper below).
const __costCodesState = { rows: [] };
jest.mock('@/hooks/costCodes', () => {
  // eslint-disable-next-line global-require
  const actual = jest.requireActual('@/hooks/costCodes');
  return {
    ...actual,
    useCostCodes: () => ({ data: __costCodesState.rows }),
    // Keep the REAL buildCostCodeMap so the FK-vs-id contract is
    // exercised end-to-end (not mocked away).
    buildCostCodeMap: actual.buildCostCodeMap,
  };
});

// eslint-disable-next-line import/first
import { BudgetGridV2Desktop } from '../grid/BudgetGridV2Desktop';

function makeBudget(lines) {
  return {
    id: 'b1',
    status: 'Draft',
    total_budget: lines.reduce((a, l) => a + l.current_budget, 0),
    total_actuals: 0,
    total_committed_not_invoiced: 0,
    total_forecast_to_complete: 0,
    forecast_final_cost: 0,
    variance_vs_budget: 0,
    variance_pct: 0,
    lines: lines.map((l, i) => ({
      original_budget: l.current_budget,
      approved_changes: 0,
      actuals_to_date: 0,
      committed_value: 0,
      forecast_final_cost: l.current_budget,
      forecast_to_complete: l.current_budget,
      variance_value: 0,
      variance_pct: 0,
      variance_status: 'Green',
      notes: null,
      items: [],
      display_order: i,
      ...l,
    })),
  };
}

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

describe('BudgetGridV2Desktop — cost code rendering (on-screen pin)', () => {
  afterEach(() => {
    __costCodesState.rows = [];
  });

  test('production-shape cost-codes ({id, cost_code_id, code}) → labels render', async () => {
    // Mirrors `/api/projects/:projectId/cost-codes` ProjectCostCodeRead.
    __costCodesState.rows = [
      { id: 'mapping-pk-A', cost_code_id: 'cc-uuid-A', code: 'ACQ-01', name: 'Land', prefix: 'ACQ' },
      { id: 'mapping-pk-B', cost_code_id: 'cc-uuid-B', code: 'EXT-01', name: 'Drainage', prefix: 'EXT' },
    ];
    const budget = makeBudget([
      { id: 'l1', cost_code_id: 'cc-uuid-A', line_description: 'Site purchase' },
      { id: 'l2', cost_code_id: 'cc-uuid-B', line_description: 'Drainage works' },
    ]);

    wrap(<BudgetGridV2Desktop budget={budget} projectId="p1" />);
    await waitFor(() => screen.getByTestId('bg2-toolbar'));

    // Expand all groups so individual line rows mount.
    const expanders = await screen.findAllByTestId(/^bg2-expand-/);
    for (const exp of expanders) exp.click();

    // Each line row must carry its resolved cost code label
    // somewhere inside it (the cell wraps it in a font-mono span).
    const row1 = await screen.findByTestId('bg2-row-line-l1');
    expect(within(row1).getByText('ACQ-01')).toBeInTheDocument();
    const row2 = screen.getByTestId('bg2-row-line-l2');
    expect(within(row2).getByText('EXT-01')).toBeInTheDocument();

    // Hard negative: the raw FK UUID must NOT appear in the cell.
    expect(within(row1).queryByText('cc-uuid-A')).toBeNull();
    expect(within(row2).queryByText('cc-uuid-B')).toBeNull();
  });

  test('test-fixture-shape cost-codes ({id, code} only) → labels still render', async () => {
    // Minimal fixture shape used across existing component tests:
    // no `cost_code_id` field. buildCostCodeMap falls back to keying
    // by `id` so legacy tests keep passing.
    __costCodesState.rows = [
      { id: 'cc-1', code: 'ACQ-01', name: 'Land', prefix: 'ACQ' },
    ];
    const budget = makeBudget([
      { id: 'l1', cost_code_id: 'cc-1', line_description: 'Site purchase' },
    ]);

    wrap(<BudgetGridV2Desktop budget={budget} projectId="p1" />);
    await waitFor(() => screen.getByTestId('bg2-toolbar'));

    const expanders = await screen.findAllByTestId(/^bg2-expand-/);
    for (const exp of expanders) exp.click();

    const row = await screen.findByTestId('bg2-row-line-l1');
    expect(within(row).getByText('ACQ-01')).toBeInTheDocument();
  });

  test('unknown FK → cell renders "—" placeholder, NOT the raw UUID', async () => {
    __costCodesState.rows = [
      { id: 'pk-A', cost_code_id: 'cc-uuid-A', code: 'ACQ-01', name: 'Land', prefix: 'ACQ' },
    ];
    const budget = makeBudget([
      { id: 'l1', cost_code_id: 'cc-uuid-MISSING', line_description: 'Orphan line' },
    ]);

    wrap(<BudgetGridV2Desktop budget={budget} projectId="p1" />);
    await waitFor(() => screen.getByTestId('bg2-toolbar'));

    const expanders = await screen.findAllByTestId(/^bg2-expand-/);
    for (const exp of expanders) exp.click();

    const row = await screen.findByTestId('bg2-row-line-l1');
    // Scope to the cost-code cell specifically. The renderer wraps the
    // value in a `font-mono` span — other cells in the row may also
    // emit "—" (e.g. notes/variance) so a row-wide getByText('—') is
    // ambiguous. The first font-mono span in the row IS the cost-code
    // cell.
    const monoSpans = row.querySelectorAll('span.font-mono');
    expect(monoSpans.length).toBeGreaterThan(0);
    expect(monoSpans[0].textContent).toBe('—');
    // Hard negative: the raw missing-FK UUID must not appear anywhere
    // in the row.
    expect(within(row).queryByText('cc-uuid-MISSING')).toBeNull();
  });
});
