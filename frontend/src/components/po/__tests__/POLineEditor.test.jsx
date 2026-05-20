/**
 * <POLineEditor/> tests — Chat 24 §R5.
 *
 * Validates live qty×rate=net calculation and totals. Keeps mocks minimal
 * (no TanStack Query needed — the editor is a pure controlled component).
 */
import { render, screen, fireEvent } from '@testing-library/react';
import POLineEditor from '@/components/po/POLineEditor';

const BUDGET_LINES = [
  { id: 'bl-1', line_description: 'Materials' },
  { id: 'bl-2', line_description: 'Labour' },
];


describe('<POLineEditor/>', () => {
  test('renders a row per line', () => {
    const lines = [
      { budget_line_id: 'bl-1', description: 'A', quantity: '1', unit_rate: '10', vat_rate: '20' },
      { budget_line_id: 'bl-2', description: 'B', quantity: '2', unit_rate: '5',  vat_rate: '20' },
    ];
    render(<POLineEditor lines={lines} onChange={() => {}} budgetLines={BUDGET_LINES} />);
    expect(screen.getByTestId('po-line-editor-row-0')).toBeInTheDocument();
    expect(screen.getByTestId('po-line-editor-row-1')).toBeInTheDocument();
  });

  test('computes per-line net = qty × rate (GBP)', () => {
    const lines = [
      { budget_line_id: 'bl-1', description: 'A', quantity: '3', unit_rate: '40', vat_rate: '20' },
    ];
    render(<POLineEditor lines={lines} onChange={() => {}} budgetLines={BUDGET_LINES} />);
    expect(screen.getByTestId('po-line-editor-net-0')).toHaveTextContent(/£120\.00/);
  });

  test('totals: net + VAT + gross across all rows', () => {
    const lines = [
      { budget_line_id: 'bl-1', description: 'A', quantity: '2', unit_rate: '50', vat_rate: '20' },
      { budget_line_id: 'bl-2', description: 'B', quantity: '1', unit_rate: '50', vat_rate: '20' },
    ];
    render(<POLineEditor lines={lines} onChange={() => {}} budgetLines={BUDGET_LINES} />);
    // Net = 2×50 + 1×50 = 150; VAT = 30; Gross = 180.
    expect(screen.getByTestId('po-line-editor-total-net')).toHaveTextContent(/£150\.00/);
    expect(screen.getByTestId('po-line-editor-total-vat')).toHaveTextContent(/£30\.00/);
    expect(screen.getByTestId('po-line-editor-total-gross')).toHaveTextContent(/£180\.00/);
  });

  test('+ Add line calls onChange with one extra blank line', () => {
    const onChange = jest.fn();
    render(<POLineEditor lines={[]} onChange={onChange} budgetLines={BUDGET_LINES} />);
    fireEvent.click(screen.getByTestId('po-line-editor-add'));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toHaveLength(1);
  });

  test('× removes the targeted line', () => {
    const onChange = jest.fn();
    const lines = [
      { budget_line_id: 'bl-1', description: 'A', quantity: '1', unit_rate: '1', vat_rate: '20' },
      { budget_line_id: 'bl-2', description: 'B', quantity: '1', unit_rate: '1', vat_rate: '20' },
    ];
    render(<POLineEditor lines={lines} onChange={onChange} budgetLines={BUDGET_LINES} />);
    fireEvent.click(screen.getByTestId('po-line-editor-remove-0'));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toHaveLength(1);
    expect(onChange.mock.calls[0][0][0].budget_line_id).toBe('bl-2');
  });

  test('changing qty bubbles patch through onChange', () => {
    const onChange = jest.fn();
    const lines = [
      { budget_line_id: 'bl-1', description: 'A', quantity: '1', unit_rate: '10', vat_rate: '20' },
    ];
    render(<POLineEditor lines={lines} onChange={onChange} budgetLines={BUDGET_LINES} />);
    fireEvent.change(screen.getByTestId('po-line-editor-qty-0'), { target: { value: '5' } });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0][0].quantity).toBe('5');
  });
});
