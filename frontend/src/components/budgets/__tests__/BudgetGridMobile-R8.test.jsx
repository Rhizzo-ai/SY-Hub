/**
 * BudgetGridMobileReadOnly tests — Chat 23 §R8.1 / §R8.2.
 *
 * Pins (per Build Pack A locked decisions):
 *   1. `BudgetGridV2` routes mobile users (useIsDesktop → false) to
 *      `BudgetGridMobileReadOnly` — NOT the desktop grid.
 *   2. Mobile surface renders header tiles (stacked) + a search input
 *      + a card list of lines with code + budget + variance badge.
 *   3. Search filters by BOTH cost code AND description (case-insensitive).
 *   4. NO bulk actions on mobile (no checkboxes, no Export/Delete/Clear
 *      bar, no `BulkActionsBar` mount).
 *   5. NO column-visibility / saved-views / presets toolbar on mobile.
 *   6. Tapping a card opens `MobileLineDetailDrawer` showing all line
 *      fields read-only EXCEPT Notes.
 *   7. `NotesCell` inside the drawer receives `canEdit=true` for users
 *      with `budgets.edit` (mobile-editable per the §R8.2 follow-up).
 *   8. Read-only users (no `budgets.edit`) see Notes as read-only.
 *   9. Sensitive-field gating: drawer hides actuals / FFC / FTC /
 *      committed for users without `budgets.view_sensitive`.
 */
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// ─── mocks ────────────────────────────────────────────────────────────
jest.mock('@/lib/useIsDesktop', () => ({
  useIsDesktop: jest.fn(),
}));
// eslint-disable-next-line import/first
import { useIsDesktop } from '@/lib/useIsDesktop';

const __authState = { me: null };
jest.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ me: __authState.me }),
}));

const __costCodesState = { rows: [] };
jest.mock('@/hooks/costCodes', () => {
  // eslint-disable-next-line global-require
  const actual = jest.requireActual('@/hooks/costCodes');
  return {
    ...actual,
    useCostCodes: () => ({ data: __costCodesState.rows }),
    buildCostCodeMap: actual.buildCostCodeMap,
  };
});

// Drilldown sub-components fan out into hooks/network that we don't
// care to exercise here — stub the drilldown wholesale so the drawer
// test stays focused on the §R8 contract. (R6: the drilldown was
// replaced by BudgetLineExpandedRow.)
jest.mock(
  '../grid/PerLineTransactionDrilldown/BudgetLineExpandedRow',
  () => ({
    BudgetLineExpandedRow: ({ line }) => (
      <div data-testid={`bg2-drilldown-${line.id}`}>drilldown-stub</div>
    ),
  }),
);

// Real NotesCell would patch the line on debounce — silence the network.
// Provide enough surface for the Desktop path's mutation hooks too so the
// `isDesktop=true` routing test doesn't fall over inside the Desktop tree.
jest.mock('@/hooks/budgets', () => ({
  usePatchBudgetLine: () => ({ mutate: jest.fn(), isPending: false }),
  useReorderBudgetLines: () => ({
    mutate: jest.fn(), isPending: false, isError: false, error: null,
  }),
  useCreateLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  usePatchLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  useDeleteLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  budgetsKeys: { detail: (id) => ['budgets', 'detail', id], all: ['budgets'] },
}));

// Desktop loads userPreferences on mount. Stub the snapshot fetch so the
// desktop-routing test doesn't blow up trying to network.
jest.mock('@/lib/api/userPreferences', () => ({
  getSurfaceSnapshot: jest.fn().mockResolvedValue({
    surface_key: 'budgets.grid.v2', current: {}, views: [],
  }),
  putCurrentPreference: jest.fn().mockResolvedValue({ id: '1', payload: {} }),
  createSavedView: jest.fn(),
  updateSavedView: jest.fn(),
  deleteSavedView: jest.fn(),
}));

// eslint-disable-next-line import/first
import { BudgetGridV2 } from '../grid/BudgetGridV2';

// ─── fixtures ─────────────────────────────────────────────────────────
const COST_CODES = [
  { id: 'pk-A', cost_code_id: 'cc-acq', code: 'ACQ-01', name: 'Land', prefix: 'ACQ' },
  { id: 'pk-B', cost_code_id: 'cc-ext', code: 'EXT-01', name: 'Drainage', prefix: 'EXT' },
  { id: 'pk-C', cost_code_id: 'cc-fin', code: 'FIN-01', name: 'Senior debt', prefix: 'FIN' },
];

function makeBudget(overrides = {}) {
  return {
    id: 'b1',
    status: 'Active',
    total_budget: 1000,
    total_actuals: 250,
    total_committed_not_invoiced: 0,
    total_forecast_to_complete: 750,
    forecast_final_cost: 1050,
    variance_vs_budget: 50,
    variance_pct: 5,
    lines: [
      {
        id: 'l-land',
        cost_code_id: 'cc-acq',
        line_description: 'Site purchase price',
        original_budget: 400, current_budget: 400,
        approved_changes: 0, actuals_to_date: 0,
        committed_value: 0,
        forecast_final_cost: 400, forecast_to_complete: 400,
        variance_value: 0, variance_pct: 0, variance_status: 'Green',
        notes: null, items: [], display_order: 0,
      },
      {
        id: 'l-drainage',
        cost_code_id: 'cc-ext',
        line_description: 'Externals — drainage overrun',
        original_budget: 100, current_budget: 100,
        approved_changes: 0, actuals_to_date: 80,
        committed_value: 0,
        forecast_final_cost: 120, forecast_to_complete: 40,
        variance_value: 20, variance_pct: 20, variance_status: 'Red',
        notes: 'Hit rock', items: [], display_order: 1,
      },
      {
        id: 'l-finance',
        cost_code_id: 'cc-fin',
        line_description: 'Senior debt interest',
        original_budget: 200, current_budget: 200,
        approved_changes: 0, actuals_to_date: 50,
        committed_value: 0,
        forecast_final_cost: 220, forecast_to_complete: 170,
        variance_value: 20, variance_pct: 10, variance_status: 'Amber',
        notes: null, items: [], display_order: 2,
      },
    ],
    ...overrides,
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

beforeEach(() => {
  __costCodesState.rows = COST_CODES;
  __authState.me = {
    id: 'u1', email: 'test-pm@example.test',
    permissions: ['budgets.view', 'budgets.view_sensitive', 'budgets.edit'],
  };
});

afterEach(() => { jest.clearAllMocks(); });

// ─── tests ────────────────────────────────────────────────────────────
describe('useIsDesktop routing (BudgetGridV2)', () => {
  test('isDesktop=false → renders BudgetGridMobileReadOnly, NOT Desktop', () => {
    useIsDesktop.mockReturnValue(false);
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    expect(screen.getByTestId('bg2-mobile')).toBeInTheDocument();
    expect(screen.queryByTestId('bg2-toolbar')).toBeNull();
    expect(screen.queryByTestId('bg2-table')).toBeNull();
  });

  test('isDesktop=true → routes away from mobile (no bg2-mobile mount)', () => {
    useIsDesktop.mockReturnValue(true);
    // The desktop path imports a long dependency chain we don't need to
    // exercise here — settle for asserting the mobile container is
    // absent under desktop routing.
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    expect(screen.queryByTestId('bg2-mobile')).toBeNull();
  });
});

describe('Mobile surface — structure & non-features', () => {
  beforeEach(() => useIsDesktop.mockReturnValue(false));

  test('renders header tiles (stacked), search, list of 3 cards', () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    expect(screen.getByTestId('bg2-header-tiles')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-search')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-list')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-line-l-land')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-line-l-drainage')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-line-l-finance')).toBeInTheDocument();
  });

  test('NO bulk actions on mobile (no bg2-bulk-bar, no select column)', () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    expect(screen.queryByTestId('bg2-bulk-bar')).toBeNull();
    expect(screen.queryByTestId('bg2-bulk-export')).toBeNull();
    expect(screen.queryByTestId('bg2-bulk-delete')).toBeNull();
    expect(screen.queryByTestId('bg2-bulk-clear')).toBeNull();
  });

  test('NO column-visibility / saved-views / presets toolbar', () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    expect(screen.queryByTestId('bg2-toolbar')).toBeNull();
    expect(screen.queryByTestId('bg2-views-dropdown')).toBeNull();
    expect(screen.queryByTestId('bg2-columns-menu')).toBeNull();
  });

  test('card shows code + budget + variance badge', () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    const card = screen.getByTestId('bg2-mobile-line-l-drainage');
    expect(within(card).getByTestId('bg2-mobile-line-l-drainage-code'))
      .toHaveTextContent('EXT-01');
    expect(within(card).getByTestId('bg2-mobile-line-l-drainage-budget'))
      .toHaveTextContent(/£100/);
    expect(within(card).getByTestId('variance-badge-Red')).toBeInTheDocument();
  });
});

describe('Mobile search — case-insensitive over code + description', () => {
  beforeEach(() => useIsDesktop.mockReturnValue(false));

  test('search by code prefix narrows the list', () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    fireEvent.change(screen.getByTestId('bg2-mobile-search'), {
      target: { value: 'ext' },
    });
    expect(screen.queryByTestId('bg2-mobile-line-l-land')).toBeNull();
    expect(screen.getByTestId('bg2-mobile-line-l-drainage')).toBeInTheDocument();
    expect(screen.queryByTestId('bg2-mobile-line-l-finance')).toBeNull();
  });

  test('search by description (case-insensitive) narrows the list', () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    fireEvent.change(screen.getByTestId('bg2-mobile-search'), {
      target: { value: 'DRAIN' },
    });
    expect(screen.getByTestId('bg2-mobile-line-l-drainage')).toBeInTheDocument();
    expect(screen.queryByTestId('bg2-mobile-line-l-finance')).toBeNull();
  });

  test('zero matches → empty-state message', () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    fireEvent.change(screen.getByTestId('bg2-mobile-search'), {
      target: { value: 'zzzz' },
    });
    expect(screen.getByTestId('bg2-mobile-empty'))
      .toHaveTextContent(/No matches/);
  });
});

describe('Mobile line drawer — tap → drawer → editable Notes only', () => {
  beforeEach(() => useIsDesktop.mockReturnValue(false));

  test('tap card opens drawer with line fields + drilldown', async () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    fireEvent.click(screen.getByTestId('bg2-mobile-line-l-drainage'));

    await waitFor(() =>
      expect(screen.getByTestId('bg2-mobile-drawer')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('bg2-mobile-drawer-code'))
      .toHaveTextContent('EXT-01');
    expect(screen.getByTestId('bg2-mobile-drawer-fields')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-drawer-notes')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-drilldown-l-drainage')).toBeInTheDocument();
  });

  test('drawer fields are read-only — no input/budget edit affordance', async () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    fireEvent.click(screen.getByTestId('bg2-mobile-line-l-drainage'));

    await waitFor(() =>
      expect(screen.getByTestId('bg2-mobile-drawer')).toBeInTheDocument(),
    );
    const fields = screen.getByTestId('bg2-mobile-drawer-fields');
    // No editable controls on the read-only field grid — the only
    // <input>/<textarea> in the drawer should be NotesCell's textarea
    // (rendered inside `bg2-mobile-drawer-notes`, NOT in the fields
    // section).
    expect(within(fields).queryByRole('textbox')).toBeNull();
    expect(within(fields).queryByRole('spinbutton')).toBeNull();
    expect(within(fields).queryByRole('combobox')).toBeNull();
  });

  test('NotesCell in drawer is EDITABLE for users with budgets.edit', async () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    fireEvent.click(screen.getByTestId('bg2-mobile-line-l-land')); // notes=null
    await waitFor(() =>
      expect(screen.getByTestId('bg2-mobile-drawer-notes')).toBeInTheDocument(),
    );
    // NotesCell's editable affordance: an "Add note" button or
    // a textarea visible. Easiest pin: the notes section is NOT
    // rendered as the canEdit=false branch (which emits a plain
    // <span> with no role=button). The editable branch renders an
    // interactive control somewhere in the section.
    const notes = screen.getByTestId('bg2-mobile-drawer-notes');
    const interactive =
      notes.querySelector('button, textarea, [role="button"]');
    expect(interactive).not.toBeNull();
  });

  test('NotesCell in drawer is READ-ONLY for users without budgets.edit', async () => {
    __authState.me = {
      id: 'u-ro', email: 'test-readonly@example.test',
      permissions: ['budgets.view'],
    };
    wrap(<BudgetGridV2 budget={makeBudget({
      lines: [{
        ...makeBudget().lines[1], notes: 'Existing note',
      }],
    })} projectId="p1" />);
    fireEvent.click(screen.getByTestId('bg2-mobile-line-l-drainage'));
    await waitFor(() =>
      expect(screen.getByTestId('bg2-mobile-drawer-notes')).toBeInTheDocument(),
    );
    const notes = screen.getByTestId('bg2-mobile-drawer-notes');
    // Read-only branch of NotesCell renders no interactive controls.
    expect(notes.querySelector('textarea')).toBeNull();
  });
});

describe('Mobile drawer — sensitive-field gating (R3.9 parity)', () => {
  beforeEach(() => useIsDesktop.mockReturnValue(false));

  test('non-sensitive user: drawer hides actuals/FFC/FTC/committed', async () => {
    __authState.me = {
      id: 'u-ro', email: 'test-readonly@example.test',
      permissions: ['budgets.view'],
    };
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    fireEvent.click(screen.getByTestId('bg2-mobile-line-l-drainage'));
    await waitFor(() =>
      expect(screen.getByTestId('bg2-mobile-drawer')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('bg2-mobile-field-actuals')).toBeNull();
    expect(screen.queryByTestId('bg2-mobile-field-ffc')).toBeNull();
    expect(screen.queryByTestId('bg2-mobile-field-ftc')).toBeNull();
    expect(screen.queryByTestId('bg2-mobile-field-committed')).toBeNull();
    // But the budget-only fields are still visible.
    expect(screen.getByTestId('bg2-mobile-field-original')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-field-current')).toBeInTheDocument();
  });

  test('sensitive user: drawer shows all 4 sensitive fields', async () => {
    wrap(<BudgetGridV2 budget={makeBudget()} projectId="p1" />);
    fireEvent.click(screen.getByTestId('bg2-mobile-line-l-drainage'));
    await waitFor(() =>
      expect(screen.getByTestId('bg2-mobile-drawer')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('bg2-mobile-field-actuals')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-field-ffc')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-field-ftc')).toBeInTheDocument();
    expect(screen.getByTestId('bg2-mobile-field-committed')).toBeInTheDocument();
  });
});
