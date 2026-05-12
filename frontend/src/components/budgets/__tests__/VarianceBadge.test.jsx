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

  test('|pct| ≤ 2 → Green (incl. exact 0 and ±2 boundary)', () => {
    expect(deriveVarianceStatus(0)).toBe('Green');
    expect(deriveVarianceStatus(2)).toBe('Green');
    expect(deriveVarianceStatus(-2)).toBe('Green');
    expect(deriveVarianceStatus(1)).toBe('Green');
    expect(deriveVarianceStatus(-1.5)).toBe('Green');
  });

  test('2 < |pct| ≤ 10 → Amber (incl. ±5, ±10 boundary)', () => {
    expect(deriveVarianceStatus(4)).toBe('Amber');
    expect(deriveVarianceStatus(5)).toBe('Amber');
    expect(deriveVarianceStatus(-5)).toBe('Amber');
    expect(deriveVarianceStatus(10)).toBe('Amber');
    expect(deriveVarianceStatus(-10)).toBe('Amber');
  });

  test('|pct| > 10 → Red — symmetric for positive AND negative', () => {
    // E12 (Chat 17 R8 click-test): backend asymmetric rule returned
    // Green for negative variance even at -99%. Frontend re-derives
    // symmetric: any |pct| > 10 is Red regardless of sign.
    expect(deriveVarianceStatus(11)).toBe('Red');
    expect(deriveVarianceStatus(50)).toBe('Red');
    expect(deriveVarianceStatus(150)).toBe('Red');
    expect(deriveVarianceStatus(-11)).toBe('Red');
    expect(deriveVarianceStatus(-50)).toBe('Red');
    expect(deriveVarianceStatus(-99.75)).toBe('Red');
    expect(deriveVarianceStatus(-100)).toBe('Red');
    expect(deriveVarianceStatus(-150)).toBe('Red');
  });

  test('coercion safety — string numeric pct from backend Decimal', () => {
    // Backend serialises Decimal as string ('150.000'). Caller wraps
    // in Number() before calling. Verify our function rejects bare
    // strings to force callers to coerce explicitly.
    expect(deriveVarianceStatus('150.0')).toBeNull();
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
