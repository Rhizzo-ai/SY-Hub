/**
 * NotesCell tests — Chat 23 R5.
 *
 * Locks the inline-edit contract:
 *   - 600ms debounce on typing.
 *   - Rapid typing coalesces into a single PATCH.
 *   - Enter (no modifier) commits immediately (no wait).
 *   - Escape reverts to prior value AND cancels pending debounce.
 *   - Blur commits immediately.
 *   - Network failure rollbacks via the mutation onError + toast.
 *   - Read-only path bypasses the textarea entirely.
 */
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NotesCell } from '../grid/NotesCell';

// Mock the budgets API so we observe the PATCH calls without network.
jest.mock('@/lib/api/budgets', () => ({
  patchBudgetLine: jest.fn(),
}));
import * as budgetsApi from '@/lib/api/budgets';

// Mock sonner toast to capture error notifications.
jest.mock('sonner', () => ({
  toast: { error: jest.fn(), success: jest.fn() },
}));
import { toast } from 'sonner';

function wrap(ui) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>{ui}</QueryClientProvider>,
  );
}

beforeEach(() => {
  budgetsApi.patchBudgetLine.mockReset();
  budgetsApi.patchBudgetLine.mockResolvedValue({ ok: true });
  toast.error.mockReset();
  jest.useFakeTimers();
});

afterEach(() => {
  act(() => { jest.runOnlyPendingTimers(); });
  jest.useRealTimers();
});

describe('NotesCell R5 inline edit contract', () => {
  test('read-only path renders trigger but no textarea', () => {
    wrap(
      <NotesCell value="readonly text" canEdit={false}
                 lineId="l1" budgetId="b1" />,
    );
    expect(screen.getByTestId('notes-cell-readonly')).toBeInTheDocument();
    expect(screen.queryByTestId('notes-cell-input')).toBeNull();
  });

  test('clicking trigger enters edit mode', () => {
    wrap(
      <NotesCell value="" canEdit lineId="l1" budgetId="b1" />,
    );
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    expect(screen.getByTestId('notes-cell-input')).toBeInTheDocument();
  });

  test('600ms debounce — single PATCH after rapid typing', async () => {
    wrap(<NotesCell value="" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));

    const ta = screen.getByTestId('notes-cell-input');
    fireEvent.change(ta, { target: { value: 'h' } });
    fireEvent.change(ta, { target: { value: 'he' } });
    fireEvent.change(ta, { target: { value: 'hel' } });
    fireEvent.change(ta, { target: { value: 'hello' } });

    // Half-debounce in → no patch yet.
    act(() => { jest.advanceTimersByTime(300); });
    expect(budgetsApi.patchBudgetLine).not.toHaveBeenCalled();

    // Past debounce window → exactly one PATCH with the final value.
    act(() => { jest.advanceTimersByTime(400); });
    await waitFor(() =>
      expect(budgetsApi.patchBudgetLine).toHaveBeenCalledTimes(1),
    );
    expect(budgetsApi.patchBudgetLine).toHaveBeenCalledWith(
      'l1', { notes: 'hello' },
    );
  });

  test('Enter commits immediately (no debounce wait)', async () => {
    wrap(<NotesCell value="" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    const ta = screen.getByTestId('notes-cell-input');
    fireEvent.change(ta, { target: { value: 'immediate' } });
    fireEvent.keyDown(ta, { key: 'Enter' });

    // No timer advance — should already have fired.
    await waitFor(() =>
      expect(budgetsApi.patchBudgetLine).toHaveBeenCalledWith(
        'l1', { notes: 'immediate' },
      ),
    );
    // Exit edit mode after Enter.
    expect(screen.queryByTestId('notes-cell-input')).toBeNull();
  });

  test('Shift+Enter inserts newline (does NOT commit)', () => {
    wrap(<NotesCell value="" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    const ta = screen.getByTestId('notes-cell-input');
    fireEvent.change(ta, { target: { value: 'line1' } });
    fireEvent.keyDown(ta, { key: 'Enter', shiftKey: true });

    expect(budgetsApi.patchBudgetLine).not.toHaveBeenCalled();
    // Still in edit mode.
    expect(screen.getByTestId('notes-cell-input')).toBeInTheDocument();
  });

  test('Escape reverts to prior value AND cancels debounce', async () => {
    wrap(<NotesCell value="original" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    const ta = screen.getByTestId('notes-cell-input');
    fireEvent.change(ta, { target: { value: 'changed' } });
    // Debounce timer is now armed for 600ms.

    fireEvent.keyDown(ta, { key: 'Escape' });

    // Even after advancing past debounce, no PATCH should fire because
    // Escape cleared the timer.
    act(() => { jest.advanceTimersByTime(1000); });
    expect(budgetsApi.patchBudgetLine).not.toHaveBeenCalled();
    // Re-enter edit mode and confirm the draft is back to the prior
    // committed value.
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    expect(screen.getByTestId('notes-cell-input').value).toBe('original');
  });

  test('Blur fires PATCH immediately (no debounce wait)', async () => {
    wrap(<NotesCell value="" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    const ta = screen.getByTestId('notes-cell-input');
    fireEvent.change(ta, { target: { value: 'via-blur' } });
    fireEvent.blur(ta);
    await waitFor(() =>
      expect(budgetsApi.patchBudgetLine).toHaveBeenCalledWith(
        'l1', { notes: 'via-blur' },
      ),
    );
  });

  test('empty string commits as null (clear notes)', async () => {
    wrap(<NotesCell value="x" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    const ta = screen.getByTestId('notes-cell-input');
    fireEvent.change(ta, { target: { value: '' } });
    fireEvent.keyDown(ta, { key: 'Enter' });
    await waitFor(() =>
      expect(budgetsApi.patchBudgetLine).toHaveBeenCalledWith(
        'l1', { notes: null },
      ),
    );
  });

  test('same-value blur skips PATCH (no-op guard)', async () => {
    wrap(<NotesCell value="same" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    fireEvent.blur(screen.getByTestId('notes-cell-input'));
    // No change → no PATCH.
    act(() => { jest.advanceTimersByTime(2000); });
    expect(budgetsApi.patchBudgetLine).not.toHaveBeenCalled();
  });

  test('character counter shown when draft >= 450 chars', () => {
    wrap(<NotesCell value="" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    fireEvent.change(screen.getByTestId('notes-cell-input'),
      { target: { value: 'a'.repeat(455) } });
    expect(screen.getByTestId('notes-cell-counter').textContent)
      .toMatch(/455\s*\/\s*500/);
  });

  test('maxLength=500 attribute set on the textarea', () => {
    wrap(<NotesCell value="" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    expect(screen.getByTestId('notes-cell-input')
      .getAttribute('maxlength')).toBe('500');
  });

  test('network failure → revert + toast.error', async () => {
    budgetsApi.patchBudgetLine.mockRejectedValueOnce(new Error('boom'));
    wrap(<NotesCell value="orig" canEdit lineId="l1" budgetId="b1" />);
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    const ta = screen.getByTestId('notes-cell-input');
    fireEvent.change(ta, { target: { value: 'will-fail' } });
    fireEvent.keyDown(ta, { key: 'Enter' });
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(toast.error).toHaveBeenCalledWith(
      'Notes did not save',
      expect.objectContaining({ description: expect.stringMatching(/boom|reverted/i) }),
    );
    // Re-enter edit mode; draft should be back at 'orig'.
    fireEvent.click(screen.getByTestId('notes-cell-trigger'));
    expect(screen.getByTestId('notes-cell-input').value).toBe('orig');
  });
});
