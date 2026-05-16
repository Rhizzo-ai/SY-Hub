/**
 * ActualStatusBadge unit tests (Chat 19B §R6).
 */
import { render, screen } from '@testing-library/react';
import { ActualStatusBadge } from '../ActualStatusBadge';

const STATUSES = ['Draft', 'Posted', 'Paid', 'Disputed', 'Void'];

describe('ActualStatusBadge', () => {
  test('renders the correct text for each of the 5 statuses', () => {
    for (const s of STATUSES) {
      const { unmount } = render(<ActualStatusBadge status={s} />);
      expect(screen.getByText(s)).toBeInTheDocument();
      unmount();
    }
  });

  test('exposes data-testid="actual-status-{status}"', () => {
    for (const s of STATUSES) {
      const { unmount } = render(<ActualStatusBadge status={s} />);
      expect(screen.getByTestId(`actual-status-${s}`)).toBeInTheDocument();
      unmount();
    }
  });
});
