/**
 * <ColumnPicker/> tests — Chat 41 §R8 (Build Pack 2.7-FE-revision).
 *
 * Controlled component — parent owns the visible Set and the options
 * array. The tests:
 *   - render the optional columns
 *   - call onToggle(key) on click
 *   - never list core columns
 */
import React, { useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ColumnPicker from '@/components/suppliers/ColumnPicker';

const OPTIONS = [
  { key: 'trade',  label: 'Trade',  default: true },
  { key: 'cis',    label: 'CIS',    default: true },
  { key: 'email',  label: 'Email',  default: false },
];

// Lightweight host that mirrors the SupplierList ownership shape.
function Host({ initial = new Set(['trade', 'cis']) }) {
  const [visible, setVisible] = useState(initial);
  const onToggle = (key) => setVisible((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  return (
    <ColumnPicker options={OPTIONS} visible={visible} onToggle={onToggle} />
  );
}

describe('<ColumnPicker/>', () => {
  test('renders one checkbox per optional column', () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId('supplier-list-column-picker'));
    expect(screen.getByTestId('column-toggle-trade')).toBeInTheDocument();
    expect(screen.getByTestId('column-toggle-cis')).toBeInTheDocument();
    expect(screen.getByTestId('column-toggle-email')).toBeInTheDocument();
  });

  test('default-on checkboxes start checked; off ones start unchecked', () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId('supplier-list-column-picker'));
    expect(screen.getByTestId('column-toggle-trade').checked).toBe(true);
    expect(screen.getByTestId('column-toggle-cis').checked).toBe(true);
    expect(screen.getByTestId('column-toggle-email').checked).toBe(false);
  });

  test('toggling an item flips checked + updates parent state', () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId('supplier-list-column-picker'));
    const email = screen.getByTestId('column-toggle-email');
    fireEvent.click(email);
    expect(screen.getByTestId('column-toggle-email').checked).toBe(true);
    fireEvent.click(screen.getByTestId('column-toggle-email'));
    expect(screen.getByTestId('column-toggle-email').checked).toBe(false);
  });

  test('core columns (name/type/status) are NOT listed', () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId('supplier-list-column-picker'));
    expect(screen.queryByTestId('column-toggle-name')).toBeNull();
    expect(screen.queryByTestId('column-toggle-type')).toBeNull();
    expect(screen.queryByTestId('column-toggle-status')).toBeNull();
  });
});
