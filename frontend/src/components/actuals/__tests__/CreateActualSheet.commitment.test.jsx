/**
 * CreateActualSheet commitment-gate tests (C1-front · Chat 64 §R6 / §R4.3).
 *
 * Strategy: the zod resolver is stubbed to a pass-through so field-level
 * validation never blocks submit — the only thing we're proving here is the
 * force-the-choice GATE and the payload/reset wiring around
 * `linked_commitment_id`. BudgetLinePicker is stubbed to drive `budget_line_id`
 * directly; the REAL CommitmentLinePicker renders (its data hook is mocked).
 */
import { render, screen, fireEvent, within, act } from '@testing-library/react';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { CreateActualSheet } from '../CreateActualSheet';
import { useCreateActual } from '@/hooks/actuals';
import { usePurchaseOrdersForBudgetLine } from '@/hooks/purchaseOrders';

// Pass-through resolver: forward the live form values, report no errors.
jest.mock('@hookform/resolvers/zod', () => ({
  zodResolver: () => async (values) => ({ values, errors: {} }),
}));

jest.mock('@/hooks/actuals', () => ({ useCreateActual: jest.fn() }));
jest.mock('@/hooks/purchaseOrders', () => ({
  usePurchaseOrdersForBudgetLine: jest.fn(),
}));
jest.mock('@/lib/api', () => ({
  api: { get: jest.fn(() => Promise.resolve({ data: { items: [] } })) },
}));

// Stub BudgetLinePicker → two buttons that set distinct budget_line_id values.
jest.mock('../BudgetLinePicker', () => ({
  BudgetLinePicker: ({ onChange }) => (
    <div>
      <button type="button" data-testid="set-bl-a" onClick={() => onChange('uuid-A')}>A</button>
      <button type="button" data-testid="set-bl-b" onClick={() => onChange('uuid-B')}>B</button>
    </div>
  ),
}));

const PO_FIXTURE = {
  items: [{
    po_number: 'PO-0001', status: 'issued',
    lines: [
      {
        id: 'LA', budget_line_id: 'uuid-A', description: 'Line A',
        remaining_amount: '6000.00', net_amount: '10000.00',
        is_fully_receipted: false,
      },
      {
        id: 'LB', budget_line_id: 'uuid-B', description: 'Line B',
        remaining_amount: '5000.00', net_amount: '5000.00',
        is_fully_receipted: false,
      },
    ],
  }],
};

let mockMutate;

beforeEach(() => {
  mockMutate = jest.fn();
  useCreateActual.mockReturnValue({ mutate: mockMutate, isPending: false });
  usePurchaseOrdersForBudgetLine.mockReturnValue({
    data: PO_FIXTURE, isLoading: false,
  });
});

afterEach(() => jest.clearAllMocks());

const renderSheet = () =>
  renderWithProviders(
    <CreateActualSheet open onOpenChange={() => {}} projectId="p1" />,
  );

const submit = async () =>
  act(async () => {
    fireEvent.submit(screen.getByTestId('create-actual-form'));
  });

test('gate: cannot submit until a choice is made', async () => {
  renderSheet();
  fireEvent.click(screen.getByTestId('set-bl-a'));
  await submit();
  expect(mockMutate).not.toHaveBeenCalled();
  expect(screen.getByTestId('commitment-picker-error')).toBeInTheDocument();
});

test('PO-line submit sends linked_commitment_id', async () => {
  renderSheet();
  fireEvent.click(screen.getByTestId('set-bl-a'));
  const radio = within(screen.getByTestId('commitment-picker-line-LA')).getByRole('radio');
  fireEvent.click(radio);
  await submit();
  expect(mockMutate).toHaveBeenCalledTimes(1);
  expect(mockMutate.mock.calls[0][0].linked_commitment_id).toBe('LA');
});

test('standalone submit omits linked_commitment_id', async () => {
  renderSheet();
  fireEvent.click(screen.getByTestId('set-bl-a'));
  const radio = within(screen.getByTestId('commitment-picker-standalone')).getByRole('radio');
  fireEvent.click(radio);
  await submit();
  expect(mockMutate).toHaveBeenCalledTimes(1);
  expect(mockMutate.mock.calls[0][0].linked_commitment_id).toBeUndefined();
});

test('changing the budget line clears the choice and shows the reset note', async () => {
  renderSheet();
  fireEvent.click(screen.getByTestId('set-bl-a'));
  const radioA = within(screen.getByTestId('commitment-picker-line-LA')).getByRole('radio');
  fireEvent.click(radioA);
  expect(radioA).toBeChecked();

  // Switch to a different budget line → choice resets, note appears.
  fireEvent.click(screen.getByTestId('set-bl-b'));
  expect(screen.getByTestId('commitment-reset-note')).toBeInTheDocument();

  // The previously-picked line is gone; the new line's radio is unchecked.
  const radioB = within(screen.getByTestId('commitment-picker-line-LB')).getByRole('radio');
  expect(radioB).not.toBeChecked();

  // And the gate is active again: submitting now is blocked.
  await submit();
  expect(mockMutate).not.toHaveBeenCalled();
});
