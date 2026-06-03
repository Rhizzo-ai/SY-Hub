/**
 * <CISStatusBadge/> tests — Chat 40 §R5 #6.
 *
 * 4 real statuses + null → correct variant + label.
 */
import { render, screen } from '@testing-library/react';
import CISStatusBadge from '@/components/suppliers/CISStatusBadge';

describe('<CISStatusBadge/>', () => {
  test('Gross → default variant, label "Gross"', () => {
    render(<CISStatusBadge status="Gross" testid="b" />);
    expect(screen.getByTestId('b')).toHaveTextContent('Gross');
  });

  test('Net → secondary variant, label "Net"', () => {
    render(<CISStatusBadge status="Net" testid="b" />);
    expect(screen.getByTestId('b')).toHaveTextContent('Net');
  });

  test('Unmatched → destructive variant, label "Unmatched"', () => {
    render(<CISStatusBadge status="Unmatched" testid="b" />);
    expect(screen.getByTestId('b')).toHaveTextContent('Unmatched');
  });

  test('Unverified → outline variant, label "Unverified"', () => {
    render(<CISStatusBadge status="Unverified" testid="b" />);
    expect(screen.getByTestId('b')).toHaveTextContent('Unverified');
  });

  test('null → outline variant, label "Unverified"', () => {
    render(<CISStatusBadge status={null} testid="b" />);
    expect(screen.getByTestId('b')).toHaveTextContent('Unverified');
  });

  test('default test-id reflects the effective status', () => {
    render(<CISStatusBadge status="Gross" />);
    expect(screen.getByTestId('cis-status-badge-Gross')).toBeInTheDocument();
  });

  test('null collapses to Unverified test-id', () => {
    render(<CISStatusBadge status={null} />);
    expect(screen.getByTestId('cis-status-badge-Unverified')).toBeInTheDocument();
  });
});
