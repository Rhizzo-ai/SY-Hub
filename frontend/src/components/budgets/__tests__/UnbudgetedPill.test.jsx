/**
 * UnbudgetedPill tests — B107 §8.1.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import {
  UnbudgetedPill, isBlockingUnbudgeted, isFlaggedUnbudgeted,
} from '@/components/budgets/UnbudgetedPill';

const FLOOR = 1000;

describe('UnbudgetedPill (B107 §3)', () => {
  test('RED blocking pill when unbudgeted + uncleared + committed >= floor', () => {
    render(<UnbudgetedPill
      row={{ is_unbudgeted: true, unbudgeted_cleared_at: null, committed_not_invoiced: '1500.00' }}
      floor={FLOOR}
    />);
    expect(screen.getByTestId('unbudgeted-pill-blocking'))
      .toHaveTextContent('Sign-off required');
  });

  test('AMBER flagged pill when below floor', () => {
    render(<UnbudgetedPill
      row={{ is_unbudgeted: true, unbudgeted_cleared_at: null, committed_not_invoiced: '500.00' }}
      floor={FLOOR}
    />);
    expect(screen.getByTestId('unbudgeted-pill-flagged'))
      .toHaveTextContent('Unbudgeted');
  });

  test('renders nothing when the unbudgeted line has been cleared', () => {
    const { container } = render(<UnbudgetedPill
      row={{ is_unbudgeted: true, unbudgeted_cleared_at: '2026-01-01T00:00:00Z', committed_not_invoiced: '5000' }}
      floor={FLOOR}
    />);
    expect(container).toBeEmptyDOMElement();
  });

  test('renders nothing for a budgeted (non-unbudgeted) line', () => {
    const { container } = render(<UnbudgetedPill
      row={{ is_unbudgeted: false, committed_not_invoiced: '5000' }}
      floor={FLOOR}
    />);
    expect(container).toBeEmptyDOMElement();
  });

  test('helpers: floor boundary is inclusive (>= blocks)', () => {
    const base = { is_unbudgeted: true, unbudgeted_cleared_at: null };
    expect(isBlockingUnbudgeted({ ...base, committed_not_invoiced: 1000 }, 1000)).toBe(true);
    expect(isFlaggedUnbudgeted({ ...base, committed_not_invoiced: 999 }, 1000)).toBe(true);
    expect(isBlockingUnbudgeted({ ...base, committed_not_invoiced: 999 }, 1000)).toBe(false);
  });
});
