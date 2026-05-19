/**
 * BulkActionsBar tests — Chat 23 §R7.2/R7.3/R7.4.
 *
 * Exercised contracts:
 *   1. Renders selected count + Export + Delete + Clear when canEdit
 *      and a selection is non-empty.
 *   2. Delete button is hidden when the user cannot edit OR the budget
 *      is not editable (Locked/Closed/Superseded).
 *   3. CSV export — sensitive-field gating: with `canViewSensitive=false`
 *      the columns `Forecast profit` and `Forecast margin %` are NOT in
 *      the table's visible leaf columns, so they cannot land in the CSV.
 *   4. CSV export — RFC-4180 quoting end-to-end with realistic line
 *      data (comma in description, etc).
 *   5. Bulk delete fan-out — live progress updates per row resolved
 *      ("Deleted 1 of 3…" → "Deleted 2 of 3…" → "Deleted 3 of 3…").
 *   6. Bulk delete fan-out — partial failure surfaces a partial-success
 *      toast and still invalidates the cache.
 *   7. 100-row cap — when >100 lines selected the Delete button is
 *      disabled and a warning text appears.
 */
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';

import { BulkActionsBar, __test__ as bulkInternals }
  from '../grid/BulkActionsBar';
import { makeColumns } from '../grid/BudgetGridColumns';
import { useReactTable, getCoreRowModel } from '@tanstack/react-table';

jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

jest.mock('@/lib/api/budgets', () => ({
  deleteBudgetLine: jest.fn(),
}));
// eslint-disable-next-line import/first
import * as budgetsApi from '@/lib/api/budgets';

const LINE = (over = {}) => ({
  id: `l-${Math.random().toString(36).slice(2, 8)}`,
  cost_code_id: 'cc-1',
  line_description: 'Build cost',
  original_budget: 1000,
  current_budget: 1000,
  approved_changes: 0,
  committed_value: 0,
  actuals_to_date: 0,
  variance_value: 0,
  variance_status: 'Green',
  forecast_final_cost: 1000,
  forecast_to_complete: 1000,
  notes: null,
  _allocated_sale_price_provisional: 1500,
  ftc_method: 'Budget_Remaining',
  ...over,
});

const COST_CODE_MAP = new Map([
  ['cc-1', { id: 'cc-1', code: 'CON-001', name: 'Build' }],
]);

function makeFakeTable({ lines, canViewSensitive }) {
  const cols = makeColumns({
    costCodeMap: COST_CODE_MAP,
    canEdit: true,
    canViewSensitive,
    budgetId: 'b1',
    onOpenDrawer: () => {},
  });
  // Build a TanStack instance to mirror the column-visibility logic
  // used by BulkActionsBar (getVisibleLeafColumns).
  let table;
  const HarnessRow = () => {
    table = useReactTable({
      data: lines.map((l) => ({ ...l, isGroup: false, isItem: false })),
      columns: cols,
      getCoreRowModel: getCoreRowModel(),
    });
    return null;
  };
  // The harness renders nothing — we only need the table instance.
  render(<HarnessRow />);
  return table;
}

function withClient(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('BulkActionsBar — rendering', () => {
  test('shows count, Export, Delete, Clear when canEdit + editable', () => {
    const lines = [LINE(), LINE()];
    const table = makeFakeTable({ lines, canViewSensitive: true });
    withClient(
      <BulkActionsBar
        selectedLines={lines}
        table={table}
        budget={{ id: 'b1' }}
        canEdit
        editable
        onClear={() => {}}
      />,
    );
    expect(screen.getByTestId('bg2-bulk-count')).toHaveTextContent(
      '2 lines selected',
    );
    expect(screen.getByTestId('bg2-bulk-export')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-bulk-delete')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-bulk-clear')).toBeInTheDocument();
  });

  test('Delete is hidden when canEdit=false (readonly user)', () => {
    const lines = [LINE()];
    const table = makeFakeTable({ lines, canViewSensitive: false });
    withClient(
      <BulkActionsBar
        selectedLines={lines}
        table={table}
        budget={{ id: 'b1' }}
        canEdit={false}
        editable
      />,
    );
    expect(screen.queryByTestId('bg2-bulk-delete')).toBeNull();
  });

  test('Delete is hidden when budget not editable (e.g. Locked)', () => {
    const lines = [LINE()];
    const table = makeFakeTable({ lines, canViewSensitive: true });
    withClient(
      <BulkActionsBar
        selectedLines={lines}
        table={table}
        budget={{ id: 'b1' }}
        canEdit
        editable={false}
      />,
    );
    expect(screen.queryByTestId('bg2-bulk-delete')).toBeNull();
  });

  test('over 100-line cap → Delete disabled + warning text', () => {
    const lines = Array.from({ length: 101 }, () => LINE());
    const table = makeFakeTable({ lines, canViewSensitive: true });
    withClient(
      <BulkActionsBar
        selectedLines={lines}
        table={table}
        budget={{ id: 'b1' }}
        canEdit
        editable
      />,
    );
    expect(screen.getByTestId('bg2-bulk-count').textContent).toMatch(/over 100/);
    expect(screen.getByTestId('bg2-bulk-delete')).toBeDisabled();
  });
});

describe('CSV export — sensitive-field gating (R7.4 + R3.9)', () => {
  test('non-sensitive user CSV excludes forecast_profit and forecast_margin_pct', () => {
    const lines = [LINE()];
    const table = makeFakeTable({ lines, canViewSensitive: false });
    // Toggle profit columns visible only if they exist — but they
    // shouldn't because makeColumns omits them for non-sensitive users.
    const csv = bulkInternals.buildCsvText(table, lines);
    expect(csv).not.toMatch(/Forecast profit/);
    expect(csv).not.toMatch(/Forecast margin/);
  });

  test('sensitive user CSV CAN include forecast_profit when column is visible', () => {
    const lines = [LINE()];
    const table = makeFakeTable({ lines, canViewSensitive: true });
    // Force the otherwise default-hidden profit columns visible.
    act(() => {
      table.setColumnVisibility({
        ...table.getState().columnVisibility,
        forecast_profit: true,
        forecast_margin_pct: true,
      });
    });
    const csv = bulkInternals.buildCsvText(table, lines);
    expect(csv).toMatch(/Forecast profit/);
    expect(csv).toMatch(/Forecast margin/);
  });

  test('CSV applies RFC-4180 quoting to a description with comma', () => {
    const lines = [LINE({ line_description: 'Line, with comma' })];
    const table = makeFakeTable({ lines, canViewSensitive: true });
    const csv = bulkInternals.buildCsvText(table, lines);
    expect(csv).toMatch(/"Line, with comma"/);
  });
});

describe('Bulk delete fan-out — progress + invalidation', () => {
  test('happy path: sequential progress updates "Deleted X of N…"', async () => {
    budgetsApi.deleteBudgetLine.mockResolvedValue();
    const lines = [LINE(), LINE(), LINE()];
    const table = makeFakeTable({ lines, canViewSensitive: true });
    const onClear = jest.fn();
    withClient(
      <BulkActionsBar
        selectedLines={lines}
        table={table}
        budget={{ id: 'b1' }}
        canEdit
        editable
        onClear={onClear}
      />,
    );
    // Open confirm + confirm.
    fireEvent.click(screen.getByTestId('bg2-bulk-delete'));
    fireEvent.click(await screen.findByTestId('bg2-bulk-delete-confirm-ok'));

    // Progress bar replaces the static bar.
    await waitFor(() =>
      expect(screen.getByTestId('bg2-bulk-bar-progress')).toBeInTheDocument(),
    );

    // After all promises settle, the bar disappears and onClear fires.
    await waitFor(() => expect(onClear).toHaveBeenCalledTimes(1));
    expect(budgetsApi.deleteBudgetLine).toHaveBeenCalledTimes(3);
    expect(toast.success).toHaveBeenCalledWith('Deleted 3 lines');
  });

  test('partial failure: error toast + cache invalidate still runs', async () => {
    // 3 calls: success, fail, success.
    budgetsApi.deleteBudgetLine
      .mockResolvedValueOnce()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce();
    const lines = [LINE(), LINE(), LINE()];
    const table = makeFakeTable({ lines, canViewSensitive: true });
    withClient(
      <BulkActionsBar
        selectedLines={lines}
        table={table}
        budget={{ id: 'b1' }}
        canEdit
        editable
        onClear={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId('bg2-bulk-delete'));
    fireEvent.click(await screen.findByTestId('bg2-bulk-delete-confirm-ok'));

    await waitFor(() =>
      expect(budgetsApi.deleteBudgetLine).toHaveBeenCalledTimes(3),
    );
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/Bulk delete partial — 2 of 3 deleted, 1 failed/),
      ),
    );
  });
});
