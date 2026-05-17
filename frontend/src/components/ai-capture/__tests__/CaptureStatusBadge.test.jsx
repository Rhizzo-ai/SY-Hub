// frontend/src/components/ai-capture/__tests__/CaptureStatusBadge.test.jsx — Chat 19C §R6.3
import { render, screen } from '@testing-library/react';
import { CaptureStatusBadge } from '@/components/ai-capture/CaptureStatusBadge';

describe('CaptureStatusBadge', () => {
  test('renders Awaiting_Review with humanised label', () => {
    render(<CaptureStatusBadge status="Awaiting_Review" />);
    expect(screen.getByTestId('capture-status-Awaiting_Review')).toHaveTextContent('Awaiting Review');
  });
  test('renders Discarded with line-through class', () => {
    render(<CaptureStatusBadge status="Discarded" />);
    const el = screen.getByTestId('capture-status-Discarded');
    expect(el.className).toMatch(/line-through/);
  });
});
