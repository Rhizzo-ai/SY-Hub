/**
 * StatusBadge test — minimal render guard.
 */
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../StatusBadge';

describe('StatusBadge', () => {
  test('renders the status label', () => {
    render(<StatusBadge status="Active" />);
    expect(screen.getByTestId('budget-status-badge-Active')).toHaveTextContent('Active');
  });
});
