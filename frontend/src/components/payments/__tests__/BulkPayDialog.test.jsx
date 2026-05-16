/**
 * BulkPayDialog tests (Chat 19B §R6).
 */
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { BulkPayDialog } from '../BulkPayDialog';
import { renderWithProviders } from '../../../test/renderWithProviders';
import { makePostedActual } from '../../../test/mocks/fixtures';

jest.mock('../../../lib/api/actuals', () => ({
  markPaid: jest.fn(),
}));
const actualsApi = require('../../../lib/api/actuals');

// Toast is a side-effect; we don't assert on it directly.
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const ID_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const ID_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

const rows = [
  makePostedActual({ id: ID_A, supplier_name_snapshot: 'A Ltd', gross_amount: '100.00' }),
  makePostedActual({ id: ID_B, supplier_name_snapshot: 'B Ltd', gross_amount: '200.00' }),
];

describe('BulkPayDialog', () => {
  beforeEach(() => jest.clearAllMocks());

  test('renders one row per actual passed in `actuals` prop', () => {
    renderWithProviders(
      <BulkPayDialog open actuals={rows} onOpenChange={() => {}} onComplete={() => {}} />,
    );
    expect(screen.getByTestId(`bulk-pay-row-${ID_A}`)).toBeInTheDocument();
    expect(screen.getByTestId(`bulk-pay-row-${ID_B}`)).toBeInTheDocument();
  });

  test('auto-generates payment_reference defaults of the form BACS-YYYYMMDD-{id6}', () => {
    renderWithProviders(
      <BulkPayDialog open actuals={rows} onOpenChange={() => {}} onComplete={() => {}} />,
    );
    const refA = screen.getByTestId(`bulk-pay-ref-${ID_A}`);
    expect(refA.value).toMatch(/^BACS-\d{8}-aaaaaa$/);
  });

  test('"Pay X" button is disabled when any ref is empty', () => {
    renderWithProviders(
      <BulkPayDialog open actuals={rows} onOpenChange={() => {}} onComplete={() => {}} />,
    );
    const runBtn = screen.getByTestId('bulk-pay-run');
    expect(runBtn).not.toBeDisabled();

    // Clear one row's ref
    fireEvent.change(screen.getByTestId(`bulk-pay-ref-${ID_A}`), { target: { value: '' } });
    expect(runBtn).toBeDisabled();
  });

  test('successful run: all status pills turn to "Paid"', async () => {
    actualsApi.markPaid.mockResolvedValue({ status: 'Paid' });
    const onComplete = jest.fn();
    renderWithProviders(
      <BulkPayDialog open actuals={rows} onOpenChange={() => {}} onComplete={onComplete} />,
    );
    fireEvent.click(screen.getByTestId('bulk-pay-run'));
    await waitFor(() => {
      expect(screen.getByTestId(`bulk-pay-success-${ID_A}`)).toBeInTheDocument();
    });
    expect(screen.getByTestId(`bulk-pay-success-${ID_B}`)).toBeInTheDocument();
    expect(onComplete).toHaveBeenCalledWith([ID_A, ID_B]);
    expect(actualsApi.markPaid).toHaveBeenCalledTimes(2);
  });

  test('failed-row run: one row pill turns red with the error message', async () => {
    actualsApi.markPaid
      .mockResolvedValueOnce({ status: 'Paid' })
      .mockRejectedValueOnce({
        response: { data: { detail: 'Disputed bills cannot be paid' } },
      });
    const onComplete = jest.fn();
    renderWithProviders(
      <BulkPayDialog open actuals={rows} onOpenChange={() => {}} onComplete={onComplete} />,
    );
    fireEvent.click(screen.getByTestId('bulk-pay-run'));
    await waitFor(() => {
      expect(screen.getByTestId(`bulk-pay-success-${ID_A}`)).toBeInTheDocument();
    });
    const errPill = await screen.findByTestId(`bulk-pay-error-${ID_B}`);
    expect(errPill).toBeInTheDocument();
    expect(errPill).toHaveAttribute('title', 'Disputed bills cannot be paid');
    // onComplete still fires with the successful subset.
    expect(onComplete).toHaveBeenCalledWith([ID_A]);
  });
});
