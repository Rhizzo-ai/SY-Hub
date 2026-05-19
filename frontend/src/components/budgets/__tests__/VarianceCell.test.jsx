/**
 * VarianceCell test — Chat 23 R3.4 heat-map cell.
 *
 * Verifies the semantic colour mapping (emerald/amber/rose, NOT brand
 * sy-teal/sy-orange) and the formatted money + pct render.
 */
import { render, screen } from '@testing-library/react';
import { VarianceCell } from '../grid/VarianceCell';

describe('VarianceCell', () => {
  test.each([
    ['Green', 'bg-emerald-50', 'text-emerald-800'],
    ['Amber', 'bg-amber-50',   'text-amber-800'],
    ['Red',   'bg-rose-50',    'text-rose-800'],
  ])('applies semantic class for status %s', (status, bg, fg) => {
    const { unmount } = render(
      <VarianceCell value={1234.56} status={status} pct={4.2} />,
    );
    const el = screen.getByTestId('variance-cell');
    expect(el.className).toContain(bg);
    expect(el.className).toContain(fg);
    // Brand tokens MUST NOT be used here (semantic colours only).
    expect(el.className).not.toContain('sy-teal');
    expect(el.className).not.toContain('sy-orange');
    expect(el.getAttribute('data-variance-status')).toBe(status);
    unmount();
  });

  test('falls back to slate when status is null', () => {
    render(<VarianceCell value={0} status={null} pct={null} />);
    const el = screen.getByTestId('variance-cell');
    expect(el.className).toContain('bg-slate-50');
  });

  test('omits pct chip when null or non-finite', () => {
    const { unmount } = render(
      <VarianceCell value={100} status="Green" pct={null} />,
    );
    expect(screen.getByTestId('variance-cell').textContent).not.toContain('%');
    unmount();
    render(<VarianceCell value={100} status="Green" pct={Infinity} />);
    expect(screen.getByTestId('variance-cell').textContent).not.toContain('%');
  });

  test('renders pct to 1 decimal', () => {
    render(<VarianceCell value={5000} status="Amber" pct={3.456} />);
    expect(screen.getByTestId('variance-cell').textContent).toContain('(3.5%)');
  });
});
