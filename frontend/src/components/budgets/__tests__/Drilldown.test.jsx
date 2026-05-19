/**
 * Drilldown stub tests — Chat 23 R4.2 / R4.3 / R4.4 status badge.
 */
import { render, screen } from '@testing-library/react';
import { POsSectionStub }
  from '../grid/PerLineTransactionDrilldown/POsSectionStub';
import { VariationsSectionStub }
  from '../grid/PerLineTransactionDrilldown/VariationsSectionStub';
import { BillStatusBadge }
  from '../grid/PerLineTransactionDrilldown/BillStatusBadge';

describe('Drilldown stubs', () => {
  test('POs stub renders empty-state copy', () => {
    render(<POsSectionStub />);
    expect(screen.getByTestId('bg2-pos-stub').textContent)
      .toMatch(/Purchase Orders ship in Prompt 2\.5/i);
  });

  test('Variations stub renders empty-state copy', () => {
    render(<VariationsSectionStub />);
    expect(screen.getByTestId('bg2-variations-stub').textContent)
      .toMatch(/Variations ship in Prompt 2\.6/i);
  });
});

describe('BillStatusBadge', () => {
  test.each([
    ['Draft',    'bg-slate-100'],
    ['Posted',   'bg-sky-50'],
    ['Paid',     'bg-emerald-50'],
    ['Disputed', 'bg-rose-50'],
    ['Void',     'bg-zinc-100'],
  ])('applies semantic colour for status %s', (status, klass) => {
    const { unmount } = render(<BillStatusBadge status={status} />);
    const el = screen.getByTestId(`bg2-bill-status-${status}`);
    expect(el.className).toContain(klass);
    expect(el.textContent).toBe(status);
    // Brand tokens never appear on status pills.
    expect(el.className).not.toContain('sy-teal');
    expect(el.className).not.toContain('sy-orange');
    unmount();
  });

  test('falls back to slate for unknown status', () => {
    render(<BillStatusBadge status="Mystery" />);
    expect(screen.getByTestId('bg2-bill-status-Mystery').className)
      .toContain('bg-slate-100');
  });

  test('null status renders em-dash, not crash', () => {
    render(<BillStatusBadge status={null} />);
    expect(screen.getByTestId('bg2-bill-status-unknown').textContent).toBe('—');
  });
});
