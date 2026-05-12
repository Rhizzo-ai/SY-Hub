/**
 * VarianceBadge tests — derived helper + render.
 */
import { render, screen } from '@testing-library/react';
import { VarianceBadge, deriveVarianceStatus } from '../VarianceBadge';

describe('deriveVarianceStatus', () => {
  test('null/NaN → null', () => {
    expect(deriveVarianceStatus(null)).toBeNull();
    expect(deriveVarianceStatus(undefined)).toBeNull();
    expect(deriveVarianceStatus(Number.NaN)).toBeNull();
  });

  test('|pct| ≤ 2 → Green', () => {
    expect(deriveVarianceStatus(0)).toBe('Green');
    expect(deriveVarianceStatus(2)).toBe('Green');
    expect(deriveVarianceStatus(-1.5)).toBe('Green');
  });

  test('2 < |pct| ≤ 10 → Amber', () => {
    expect(deriveVarianceStatus(4)).toBe('Amber');
    expect(deriveVarianceStatus(-10)).toBe('Amber');
  });

  test('|pct| > 10 → Red', () => {
    expect(deriveVarianceStatus(11)).toBe('Red');
    expect(deriveVarianceStatus(-100)).toBe('Red');
  });
});

describe('VarianceBadge render', () => {
  test('renders the em-dash when status is null', () => {
    const { container } = render(<VarianceBadge status={null} value={null} pct={null} />);
    expect(container.textContent).toContain('—');
  });

  test('renders the status pill with the band label', () => {
    render(<VarianceBadge status="Amber" value={5000} pct={4} />);
    expect(screen.getByTestId('variance-badge-Amber')).toHaveTextContent('Amber');
  });
});
