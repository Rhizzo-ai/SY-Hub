/**
 * LineItemsBreakdown — "+ Add item" regression lock.
 *
 * B88 Pack 2 Gate 2 re-eyeball round 3 — Defect:
 *   Clicking "+ Add item" silently did nothing. Root cause: the client
 *   sent `{ description, amount, display_order }` but the backend
 *   `CreateBudgetLineItemRequest` is `extra="forbid"` (pydantic v2) so
 *   the POST returned 422 every time. The mutation had no `onError`
 *   handler so the failure was swallowed.
 *
 * Fix:
 *   - Drop `display_order` (server assigns next-available slot).
 *   - Surface failures via `sonner` toast so silent regressions can't
 *     hide again.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LineItemsBreakdown } from
  '@/components/budgets/grid/PerLineTransactionDrilldown/LineItemsBreakdown';

// Spy registry hung on globalThis so the jest.mock factories can read
// it without violating jest's "no out-of-scope variable" rule.
globalThis.__test__ = globalThis.__test__ || {};
globalThis.__test__.createMutate = jest.fn();
globalThis.__test__.toastError = jest.fn();

jest.mock('sonner', () => ({
  toast: {
    error: (...args) => globalThis.__test__.toastError(...args),
    success: jest.fn(),
  },
}));
jest.mock('@/hooks/budgets', () => ({
  useCreateLineItem: () => ({
    mutate: (body, opts) => globalThis.__test__.createMutate(body, opts),
    isPending: false,
  }),
  usePatchLineItem: () => ({ mutate: jest.fn(), isPending: false }),
  useDeleteLineItem: () => ({
    mutateAsync: jest.fn(), isPending: false,
  }),
}));

const LINE = { id: 'line-1', items: [] };
const BUDGET = { id: 'b1', status: 'Active' };

beforeEach(() => {
  globalThis.__test__.createMutate.mockReset();
  globalThis.__test__.toastError.mockReset();
});

describe('LineItemsBreakdown — Add item (B88 Pack 2 Defect)', () => {
  test('fires create with cleaned payload (no display_order)', () => {
    render(
      <LineItemsBreakdown line={LINE} budget={BUDGET} canEdit={true} />,
    );
    fireEvent.click(screen.getByTestId('bg2-item-add-line-1'));
    expect(globalThis.__test__.createMutate).toHaveBeenCalled();
    const [body] = globalThis.__test__.createMutate.mock.calls[0];
    expect(body).toEqual({
      description: 'New item',
      amount: '0',
    });
    expect(body.display_order).toBeUndefined();
  });

  test('surfaces an error toast when the create mutation fails', async () => {
    globalThis.__test__.createMutate.mockImplementation((body, opts) => {
      opts?.onError?.({
        response: { data: { detail: 'Validation failed' } },
        message: 'request failed',
      });
    });
    render(
      <LineItemsBreakdown line={LINE} budget={BUDGET} canEdit={true} />,
    );
    fireEvent.click(screen.getByTestId('bg2-item-add-line-1'));
    await waitFor(() =>
      expect(globalThis.__test__.toastError)
        .toHaveBeenCalledWith('Validation failed'),
    );
  });

  test('falls back to generic message when error detail is not a string', async () => {
    globalThis.__test__.createMutate.mockImplementation((body, opts) => {
      opts?.onError?.({ response: { data: { detail: { msg: 'x' } } } });
    });
    render(
      <LineItemsBreakdown line={LINE} budget={BUDGET} canEdit={true} />,
    );
    fireEvent.click(screen.getByTestId('bg2-item-add-line-1'));
    await waitFor(() =>
      expect(globalThis.__test__.toastError)
        .toHaveBeenCalledWith('Failed to add item.'),
    );
  });

  test('Add item button hidden when canEdit=false', () => {
    render(
      <LineItemsBreakdown line={LINE} budget={BUDGET} canEdit={false} />,
    );
    expect(screen.queryByTestId('bg2-item-add-line-1'))
      .not.toBeInTheDocument();
  });
});
