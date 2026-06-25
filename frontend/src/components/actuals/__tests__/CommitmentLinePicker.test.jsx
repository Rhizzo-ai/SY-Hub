/**
 * CommitmentLinePicker tests (C1-front · Chat 64 §R6).
 *
 * The data hook is mocked so each state is driven deterministically; the
 * component's real filtering / sensitivity / radio logic is exercised.
 */
import { render, screen, fireEvent, within } from '@testing-library/react';
import { CommitmentLinePicker } from '../CommitmentLinePicker';
import { usePurchaseOrdersForBudgetLine } from '@/hooks/purchaseOrders';

jest.mock('@/hooks/purchaseOrders', () => ({
  usePurchaseOrdersForBudgetLine: jest.fn(),
}));

const BL = 'bl-1';

const baseProps = () => ({
  projectId: 'p1',
  budgetLineId: BL,
  value: null,
  onChange: jest.fn(),
  standalone: false,
  onStandaloneChange: jest.fn(),
  error: '',
  disabled: false,
});

const mockHook = (data, isLoading = false) =>
  usePurchaseOrdersForBudgetLine.mockReturnValue({ data, isLoading });

afterEach(() => jest.clearAllMocks());

test('muted hint when no budget line selected', () => {
  mockHook(undefined, false);
  render(<CommitmentLinePicker {...baseProps()} budgetLineId={null} />);
  expect(screen.getByTestId('commitment-picker-hint')).toBeInTheDocument();
});

test('loading state', () => {
  mockHook(undefined, true);
  render(<CommitmentLinePicker {...baseProps()} />);
  expect(screen.getByTestId('commitment-picker-loading')).toBeInTheDocument();
});

test('empty → auto-standalone + note, no checkbox', () => {
  mockHook({ items: [] });
  const onStandaloneChange = jest.fn();
  render(
    <CommitmentLinePicker {...baseProps()} onStandaloneChange={onStandaloneChange} />,
  );
  expect(screen.getByTestId('commitment-picker-empty')).toBeInTheDocument();
  expect(screen.getByTestId('commitment-picker-empty').textContent)
    .toMatch(/standalone cost/i);
  expect(onStandaloneChange).toHaveBeenCalledWith(true);
  // No "No PO available" control to opt out of in the empty state.
  expect(screen.queryByTestId('commitment-picker-standalone')).not.toBeInTheDocument();
});

test('populated radio list renders PO number + remaining of net', () => {
  mockHook({
    items: [{
      po_number: 'PO-0001', status: 'issued',
      lines: [{
        id: 'L1', budget_line_id: BL, description: 'Groundworks',
        remaining_amount: '6000.00', net_amount: '10000.00',
        is_fully_receipted: false,
      }],
    }],
  });
  render(<CommitmentLinePicker {...baseProps()} />);
  expect(screen.getByTestId('commitment-picker')).toBeInTheDocument();
  const lineEl = screen.getByTestId('commitment-picker-line-L1');
  expect(lineEl.textContent).toContain('PO-0001');
  expect(lineEl.textContent).toMatch(/£6,000\.00 remaining of £10,000\.00/);
  expect(screen.getByTestId('commitment-picker-standalone')).toBeInTheDocument();
});

test('selecting a PO line calls onChange and clears standalone', () => {
  mockHook({
    items: [{
      po_number: 'PO-0001', status: 'approved',
      lines: [{
        id: 'L1', budget_line_id: BL, description: 'X',
        remaining_amount: '100.00', net_amount: '100.00',
        is_fully_receipted: false,
      }],
    }],
  });
  const onChange = jest.fn();
  const onStandaloneChange = jest.fn();
  render(
    <CommitmentLinePicker
      {...baseProps()} onChange={onChange} onStandaloneChange={onStandaloneChange}
    />,
  );
  const radio = within(screen.getByTestId('commitment-picker-line-L1')).getByRole('radio');
  fireEvent.click(radio);
  expect(onChange).toHaveBeenCalledWith('L1');
  expect(onStandaloneChange).toHaveBeenCalledWith(false);
});

test('selecting "No PO available" sets standalone and clears the line', () => {
  mockHook({
    items: [{
      po_number: 'PO-0001', status: 'issued',
      lines: [{
        id: 'L1', budget_line_id: BL, description: 'X',
        remaining_amount: '100.00', net_amount: '100.00',
        is_fully_receipted: false,
      }],
    }],
  });
  const onChange = jest.fn();
  const onStandaloneChange = jest.fn();
  render(
    <CommitmentLinePicker
      {...baseProps()} onChange={onChange} onStandaloneChange={onStandaloneChange}
    />,
  );
  const radio = within(screen.getByTestId('commitment-picker-standalone')).getByRole('radio');
  fireEvent.click(radio);
  expect(onChange).toHaveBeenCalledWith(null);
  expect(onStandaloneChange).toHaveBeenCalledWith(true);
});

test('fully-invoiced line is shown but disabled', () => {
  mockHook({
    items: [{
      po_number: 'PO-0009', status: 'receipted',
      lines: [{
        id: 'L9', budget_line_id: BL, description: 'Done',
        remaining_amount: '0.00', net_amount: '5000.00',
        is_fully_receipted: true,
      }],
    }],
  });
  render(<CommitmentLinePicker {...baseProps()} />);
  const radio = within(screen.getByTestId('commitment-picker-line-L9')).getByRole('radio');
  expect(radio).toBeDisabled();
  expect(screen.getByText(/fully invoiced/i)).toBeInTheDocument();
});

test('null money (no view_sensitive) renders no "£null" and no money suffix', () => {
  mockHook({
    items: [{
      po_number: 'PO-0002', status: 'issued',
      lines: [{
        id: 'L2', budget_line_id: BL, description: 'Hidden money',
        remaining_amount: null, net_amount: null, is_fully_receipted: false,
      }],
    }],
  });
  render(<CommitmentLinePicker {...baseProps()} />);
  expect(screen.getByTestId('commitment-picker-line-L2')).toBeInTheDocument();
  expect(screen.queryByText(/£null/)).not.toBeInTheDocument();
  expect(screen.queryByText(/remaining of/)).not.toBeInTheDocument();
});

test('error text surfaces when parent passes one', () => {
  mockHook({
    items: [{
      po_number: 'PO-0003', status: 'issued',
      lines: [{
        id: 'L3', budget_line_id: BL, description: 'Y',
        remaining_amount: '1.00', net_amount: '1.00', is_fully_receipted: false,
      }],
    }],
  });
  render(<CommitmentLinePicker {...baseProps()} error="Pick one" />);
  expect(screen.getByTestId('commitment-picker-error')).toHaveTextContent('Pick one');
});
