/**
 * <CISTab/> tests — Chat 40 §R5 #4.
 *
 * Covers:
 *  - Current-status banner (verified date / "no verification on record")
 *  - History table newest-first (backend orders; just verifies render)
 *  - verification_number masked without cis.view_sensitive
 *  - Record form gated on cis.verify
 *  - Success invalidates queries (mutation onSuccess fires)
 *  - 409 toast path on failure
 */
jest.mock('@/hooks/cis', () => ({
  useCurrentVerification: jest.fn(),
  useVerifications: jest.fn(),
  useRecordVerification: jest.fn(),
}));
jest.mock('@/context/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CISTab from '@/components/suppliers/CISTab';

const hooks = jest.requireMock('@/hooks/cis');
const { useAuth } = jest.requireMock('@/context/AuthContext');
const { toast } = jest.requireMock('sonner');

function setMe(perms) {
  useAuth.mockReturnValue({ me: { permissions: perms, is_super_admin: false } });
}

let recordMutate;
beforeEach(() => {
  recordMutate = jest.fn().mockResolvedValue({});
  hooks.useCurrentVerification.mockReturnValue({ data: null });
  hooks.useVerifications.mockReturnValue({ data: { items: [] }, isLoading: false, isError: false });
  hooks.useRecordVerification.mockReturnValue({ mutateAsync: recordMutate });
  useAuth.mockReset();
  toast.success.mockReset();
  toast.error.mockReset();
});

describe('<CISTab/>', () => {
  test('banner shows "No verification on record" when current is null', () => {
    setMe(['cis.view']);
    render(<CISTab supplierId="S1" />);
    expect(screen.getByTestId('cis-current-banner')).toHaveTextContent('No verification on record');
  });

  test('banner shows current match_status + verified_on when present', () => {
    setMe(['cis.view']);
    hooks.useCurrentVerification.mockReturnValue({
      data: { id: 'V1', match_status: 'Gross', verified_on: '2026-02-15' },
    });
    render(<CISTab supplierId="S1" />);
    const banner = screen.getByTestId('cis-current-banner');
    expect(banner).toHaveTextContent('Gross');
    expect(banner).toHaveTextContent('15 Feb 2026');
  });

  test('history table renders rows (backend orders newest-first)', () => {
    setMe(['cis.view', 'cis.view_sensitive']);
    hooks.useVerifications.mockReturnValue({
      data: { items: [
        { id: 'V2', match_status: 'Net', verified_on: '2026-02-10',
          tax_rate_pct: '20.0', verification_number: 'V222', notes: 'later' },
        { id: 'V1', match_status: 'Gross', verified_on: '2026-01-01',
          tax_rate_pct: null, verification_number: 'V111', notes: 'earlier' },
      ]},
      isLoading: false, isError: false,
    });
    render(<CISTab supplierId="S1" />);
    expect(screen.getByTestId('cis-history-row-V1')).toBeInTheDocument();
    expect(screen.getByTestId('cis-history-row-V2')).toBeInTheDocument();
    expect(screen.getByTestId('cis-history-vnum-V1')).toHaveTextContent('V111');
  });

  test('verification_number masked without cis.view_sensitive', () => {
    setMe(['cis.view']); // no view_sensitive
    hooks.useVerifications.mockReturnValue({
      data: { items: [
        { id: 'V1', match_status: 'Gross', verified_on: '2026-01-01',
          tax_rate_pct: null, verification_number: null, notes: null },
      ]},
      isLoading: false, isError: false,
    });
    render(<CISTab supplierId="S1" />);
    expect(screen.getByTestId('cis-history-vnum-V1')).toHaveTextContent('—');
  });

  test('record form NOT shown without cis.verify', () => {
    setMe(['cis.view']);
    render(<CISTab supplierId="S1" />);
    expect(screen.queryByTestId('cis-record-form')).toBeNull();
  });

  test('record form shown with cis.verify; happy submit fires mutation + success toast', async () => {
    setMe(['cis.view', 'cis.verify']);
    render(<CISTab supplierId="S1" />);
    expect(screen.getByTestId('cis-record-form')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('cis-record-match'), { target: { value: 'Net' } });
    fireEvent.change(screen.getByTestId('cis-record-tax'), { target: { value: '20' } });
    fireEvent.change(screen.getByTestId('cis-record-verified-on'),
                     { target: { value: '2026-02-15' } });
    fireEvent.click(screen.getByTestId('cis-record-submit'));
    await waitFor(() => expect(recordMutate).toHaveBeenCalled());
    const body = recordMutate.mock.calls[0][0];
    expect(body.match_status).toBe('Net');
    expect(body.tax_rate_pct).toBe('20');
    expect(body.verified_on).toBe('2026-02-15');
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Verification recorded'));
  });

  test('409 from backend → toast.error with detail', async () => {
    setMe(['cis.view', 'cis.verify']);
    recordMutate.mockRejectedValueOnce({
      response: { status: 409, data: { detail: 'CIS verification only valid for subcontractors' } },
    });
    render(<CISTab supplierId="S1" />);
    fireEvent.change(screen.getByTestId('cis-record-verified-on'),
                     { target: { value: '2026-02-15' } });
    fireEvent.click(screen.getByTestId('cis-record-submit'));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.error.mock.calls[0][0]).toMatch(/only valid for subcontractors/);
  });
});
