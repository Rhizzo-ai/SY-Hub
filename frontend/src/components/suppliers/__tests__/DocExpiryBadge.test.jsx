/**
 * <DocExpiryBadge/> tests — Chat 40 §R5 #7.
 *
 * Expired (< today) → destructive "Expired"
 * Expiring (≤ 30d)  → orange "Expiring soon"
 * Valid (> 30d)     → no badge
 * Null/empty        → no badge
 */
import { render, screen } from '@testing-library/react';
import DocExpiryBadge, { _bucketForTests } from '@/components/suppliers/DocExpiryBadge';

// Helper to make an ISO date relative to "today" so the test
// remains stable as the real clock advances.
function isoDelta(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

describe('<DocExpiryBadge/>', () => {
  test('renders nothing when expiresOn is null', () => {
    const { container } = render(<DocExpiryBadge expiresOn={null} />);
    expect(container.firstChild).toBeNull();
  });

  test('renders nothing when expiresOn is undefined', () => {
    const { container } = render(<DocExpiryBadge expiresOn={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  test('renders nothing when expiresOn is invalid', () => {
    const { container } = render(<DocExpiryBadge expiresOn="not-a-date" />);
    expect(container.firstChild).toBeNull();
  });

  test('Expired (yesterday) → destructive badge "Expired"', () => {
    render(<DocExpiryBadge expiresOn={isoDelta(-1)} />);
    expect(screen.getByTestId('doc-expiry-badge-expired')).toHaveTextContent('Expired');
  });

  test('Expiring (in 7 days) → orange badge "Expiring soon"', () => {
    render(<DocExpiryBadge expiresOn={isoDelta(7)} />);
    expect(screen.getByTestId('doc-expiry-badge-expiring')).toHaveTextContent('Expiring soon');
  });

  test('Expiring (in 30 days exactly) → orange badge (boundary)', () => {
    render(<DocExpiryBadge expiresOn={isoDelta(30)} />);
    expect(screen.getByTestId('doc-expiry-badge-expiring')).toBeInTheDocument();
  });

  test('Valid (in 60 days) → no badge', () => {
    const { container } = render(<DocExpiryBadge expiresOn={isoDelta(60)} />);
    expect(container.firstChild).toBeNull();
  });

  test('Today → expiring (diff 0)', () => {
    render(<DocExpiryBadge expiresOn={isoDelta(0)} />);
    expect(screen.getByTestId('doc-expiry-badge-expiring')).toBeInTheDocument();
  });

  describe('_bucketForTests pure logic', () => {
    test('returns null for null/undefined/invalid', () => {
      expect(_bucketForTests(null)).toBeNull();
      expect(_bucketForTests(undefined)).toBeNull();
      expect(_bucketForTests('not-a-date')).toBeNull();
    });

    test('bucket boundaries — fixed clock', () => {
      const now = new Date('2026-06-15T10:00:00Z');
      expect(_bucketForTests('2026-06-14', now)).toBe('expired'); // -1
      expect(_bucketForTests('2026-06-15', now)).toBe('expiring'); // 0
      expect(_bucketForTests('2026-07-15', now)).toBe('expiring'); // 30
      expect(_bucketForTests('2026-07-16', now)).toBe('valid');    // 31
      expect(_bucketForTests('2027-06-15', now)).toBe('valid');
    });
  });
});
