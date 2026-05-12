/**
 * LineDrawer tests — Build Pack §R8.4 TestLineCRUD + E9 conflict path.
 *
 * Covers:
 *   - Drawer opens with current line values pre-filled.
 *   - dirty=true after typing → Save button enables.
 *   - PATCH body contains ONLY dirty fields (no `version`, no extras).
 *   - E9 conflict banner appears when line.updated_at changes mid-edit.
 */
import { screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LineDrawer } from '../LineDrawer';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { mockBudget, mockLine, mockMe } from '../../../test/mocks/fixtures';

jest.mock('../../../context/AuthContext', () => ({
  useAuth: jest.fn(),
}));

const mockMutateAsync = jest.fn();
jest.mock('../../../hooks/budgets', () => ({
  usePatchBudgetLine: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
  useCreateLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  usePatchLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  useDeleteLineItem: () => ({
    mutateAsync: jest.fn(), isPending: false,
  }),
}));
jest.mock('../../../hooks/costCodes', () => ({
  useCostCodes: () => ({ data: [], isLoading: false }),
  buildCostCodeMap: () => new Map(),
}));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const { useAuth } = require('../../../context/AuthContext');

const PM = mockMe(['budgets.view', 'budgets.edit', 'budgets.view_sensitive']);

function setup({ status = 'Draft', lineOverrides = {} } = {}) {
  const line = mockLine({
    line_description: 'Original description',
    percentage_complete: 10,
    updated_at: '2026-05-01T00:00:00Z',
    ...lineOverrides,
  });
  const budget = mockBudget({ status, lines: [line] });
  return { budget, line };
}

describe('LineDrawer — open + dirty + save', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ me: PM });
    mockMutateAsync.mockReset();
    mockMutateAsync.mockResolvedValue({});
  });

  test('opens with current line values pre-filled', async () => {
    const { budget, line } = setup();
    renderWithProviders(
      <LineDrawer
        budget={budget} projectId={budget.project_id}
        lineId={line.id} onClose={jest.fn()} />,
    );
    const input = await screen.findByTestId('line-drawer-description');
    expect(input).toHaveValue('Original description');
    expect(screen.getByTestId('line-drawer-dirty-state').textContent).toMatch(/No changes/);
    expect(screen.getByTestId('line-drawer-save')).toBeDisabled();
  });

  test('typing flips dirty state and enables Save', async () => {
    const user = userEvent.setup();
    const { budget, line } = setup();
    renderWithProviders(
      <LineDrawer budget={budget} projectId={budget.project_id}
                  lineId={line.id} onClose={jest.fn()} />,
    );
    const input = await screen.findByTestId('line-drawer-description');
    await user.clear(input);
    await user.type(input, 'New desc');
    expect(screen.getByTestId('line-drawer-dirty-state').textContent).toMatch(/Unsaved changes/);
    expect(screen.getByTestId('line-drawer-save')).not.toBeDisabled();
  });

  test('Save sends ONLY dirty fields (line_description), no version/extras', async () => {
    const user = userEvent.setup();
    const { budget, line } = setup();
    renderWithProviders(
      <LineDrawer budget={budget} projectId={budget.project_id}
                  lineId={line.id} onClose={jest.fn()} />,
    );
    const input = await screen.findByTestId('line-drawer-description');
    await user.clear(input);
    await user.type(input, 'Updated');
    await waitFor(() =>
      expect(screen.getByTestId('line-drawer-save')).not.toBeDisabled(),
    );
    fireEvent.click(screen.getByTestId('line-drawer-save'));
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledTimes(1));
    const sentBody = mockMutateAsync.mock.calls[0][0].body;
    expect(sentBody).toEqual({ line_description: 'Updated' });
    expect(sentBody).not.toHaveProperty('version');
    expect(sentBody).not.toHaveProperty('updated_at');
    expect(sentBody).not.toHaveProperty('cost_code_id');
  });
});

describe('LineDrawer — E9 conflict banner', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ me: PM });
  });

  test('renders amber Reload banner when line.updated_at changes after drawer opens', async () => {
    useAuth.mockReturnValue({ me: PM });
    const { budget, line } = setup({
      lineOverrides: { updated_at: '2026-05-01T00:00:00Z' },
    });
    // Render via a wrapping component that owns the "current budget"
    // in local state. We then mutate that state from a test-driven
    // button to simulate a parent cache invalidation bumping line.updated_at.
    const updatedLine = { ...line, updated_at: '2026-05-02T12:00:00Z' };
    const updatedBudget = { ...budget, lines: [updatedLine] };

    function Harness() {
      const [b, setB] = require('react').useState(budget);
      return (
        <>
          <button
            type="button"
            data-testid="harness-bump-updated-at"
            onClick={() => setB(updatedBudget)}
          >
            bump
          </button>
          <LineDrawer budget={b} projectId={b.project_id}
                      lineId={line.id} onClose={jest.fn()} />
        </>
      );
    }
    renderWithProviders(<Harness />);
    expect(screen.queryByTestId('line-drawer-conflict-banner')).toBeNull();
    fireEvent.click(screen.getByTestId('harness-bump-updated-at'));
    await waitFor(() =>
      expect(screen.getByTestId('line-drawer-conflict-banner'))
        .toBeInTheDocument(),
    );
    expect(screen.getByTestId('line-drawer-reload')).toBeInTheDocument();
  });
});

describe('LineDrawer — discard-on-dirty close', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ me: PM });
  });

  test('clicking Close with unsaved changes opens the discard dialog', async () => {
    const user = userEvent.setup();
    const onClose = jest.fn();
    const { budget, line } = setup();
    renderWithProviders(
      <LineDrawer budget={budget} projectId={budget.project_id}
                  lineId={line.id} onClose={onClose} />,
    );
    const input = await screen.findByTestId('line-drawer-description');
    await user.clear(input);
    await user.type(input, 'Dirty');
    fireEvent.click(screen.getByTestId('line-drawer-close'));
    expect(await screen.findByTestId('line-drawer-discard-dialog'))
      .toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
