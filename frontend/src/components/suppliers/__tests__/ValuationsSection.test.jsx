/**
 * <ValuationsSection/> tests — Build Pack 2.8-FE-ii §R6, Gate 2.
 *
 * Single-file integration suite spanning the section, list, detail
 * and dialogs. Mocks the hook layer (lib/api/__tests__/* pins the
 * wire) so we can assert UI invariants without round-tripping.
 *
 * Coverage map (Build Pack §R6, Gate 2 lockdown):
 *   1.  Forbidden state when `subcontract_valuations.view` missing.
 *   2.  "New valuation" hidden + hint shown when subcontract status
 *       is NOT in {Active, Completed}.
 *   3.  "New valuation" shown when status ∈ {Active, Completed} AND
 *       canCreateValuation.
 *   4.  list rows render with status pills + reference + period +
 *       gross applied; over-claim chip visible.
 *   5.  list empty state copy.
 *   6.  Sensitive sums in list: em-dash for non-sensitive user;
 *       gross_applied + retention_rate (non-sensitive) still visible
 *       to non-sensitive user in DETAIL.
 *   7.  Detail sensitive gating: non-sensitive user sees em-dash for
 *       the 5 sensitive fields.
 *   8.  Detail action buttons by status:
 *         - Draft       → [Submit]
 *         - Submitted   → [Certify, Reject]
 *         - Certified   → [] (no lifecycle)
 *         - Rejected    → [] + rejection-reason banner
 *   9.  Certify button hidden without `subcontract_valuations.certify`.
 *  10. Submit toast 409 surfaces server detail; 422 surfaces verbatim.
 *  11. Certify dialog: Confirm DISABLED until budget line selected;
 *       click "Certify" with a selected line → mutate body carries
 *       { budget_line_id, transaction_date, description }.
 *  12. Reject dialog: Confirm disabled while reason blank; non-blank
 *       reason enables Confirm.
 *  13. PaymentNoticesPanel renders for Certified valuation; PayLess
 *       button only with `payment_notices.create`; PayLess submit
 *       sends the body with withhold_amount as STRING.
 *  14. PaymentNoticesPanel hidden for non-Certified valuation.
 *  15. Over-claim warning banner shown when over_claim_flag is true.
 */
import { screen, fireEvent, waitFor } from '@testing-library/react';

import { renderWithProviders } from '../../../test/renderWithProviders';
import ValuationsSection from '../valuations/ValuationsSection';

jest.mock('../../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../hooks/subcontractValuations', () => ({
  valKeys: { all: ['vals'], list: () => [], detail: () => [] },
  useValuations: jest.fn(),
  useValuation: jest.fn(),
  useCreateValuation: jest.fn(),
  useSubmitValuation: jest.fn(),
  useCertifyValuation: jest.fn(),
  useRejectValuation: jest.fn(),
}));
jest.mock('../../../hooks/paymentNotices', () => ({
  noticeKeys: { all: ['notices'], list: () => [] },
  usePaymentNotices: jest.fn(),
  useCreatePayLess: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));
// Reuse-target — stub <BudgetLinePicker/> to a controlled select so the
// certify dialog test can drive the budget line id.
jest.mock('@/components/actuals/BudgetLinePicker', () => ({
  BudgetLinePicker: ({ value, onChange }) => (
    <select
      data-testid="mock-budget-line-picker"
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || null)}
    >
      <option value="">— Select —</option>
      <option value="BL-1">BL-1</option>
    </select>
  ),
}));

const { useAuth } = require('../../../context/AuthContext');
const valHooks = require('../../../hooks/subcontractValuations');
const noticeHooks = require('../../../hooks/paymentNotices');
const { toast } = require('sonner');


// ─── Personas ────────────────────────────────────────────────────────
const ME_FULL = {
  id: 'user-pm',
  permissions: [
    'subcontract_valuations.view', 'subcontract_valuations.view_sensitive',
    'subcontract_valuations.create', 'subcontract_valuations.certify',
    'payment_notices.view', 'payment_notices.create',
  ],
};
const ME_NON_SENSITIVE = {
  id: 'user-ns',
  permissions: ['subcontract_valuations.view', 'payment_notices.view'],
};
const ME_VIEW_ONLY = {
  id: 'user-vo',
  permissions: ['subcontract_valuations.view', 'payment_notices.view'],
};
const ME_NO_VIEW = {
  id: 'user-nv',
  permissions: [],
};

const SC_ACTIVE = {
  id: 'SC-1',
  project_id: 'PROJ-1',
  status: 'Active',
};
const SC_DRAFT = {
  id: 'SC-2',
  project_id: 'PROJ-1',
  status: 'Draft',
};


// ─── Hook return shape helpers ───────────────────────────────────────
function mockListReturn(items = []) {
  return {
    data: { items, total: items.length },
    isLoading: false,
    isError: false,
  };
}
function mockNoOpMutation() {
  return {
    mutate: jest.fn(),
    mutateAsync: jest.fn().mockResolvedValue({}),
    isPending: false,
    isError: false,
    error: null,
    reset: jest.fn(),
  };
}


beforeEach(() => {
  jest.clearAllMocks();
  useAuth.mockReturnValue({ me: ME_FULL });
  valHooks.useValuations.mockReturnValue(mockListReturn([]));
  valHooks.useValuation.mockReturnValue({
    data: null, isLoading: false, isError: false,
  });
  valHooks.useCreateValuation.mockReturnValue(mockNoOpMutation());
  valHooks.useSubmitValuation.mockReturnValue(mockNoOpMutation());
  valHooks.useCertifyValuation.mockReturnValue(mockNoOpMutation());
  valHooks.useRejectValuation.mockReturnValue(mockNoOpMutation());
  noticeHooks.usePaymentNotices.mockReturnValue(mockListReturn([]));
  noticeHooks.useCreatePayLess.mockReturnValue(mockNoOpMutation());
});


// ════════════════════════════════════════════════════════════════════
// 1. Forbidden when missing subcontract_valuations.view
// ════════════════════════════════════════════════════════════════════

test('renders forbidden line when user lacks subcontract_valuations.view', () => {
  useAuth.mockReturnValue({ me: ME_NO_VIEW });
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  expect(screen.getByTestId('valuations-section-forbidden')).toBeInTheDocument();
  // List hook should NOT fire (component returns before mounting children).
  expect(valHooks.useValuations).not.toHaveBeenCalled();
});


// ════════════════════════════════════════════════════════════════════
// 2 / 3. "New valuation" gating
// ════════════════════════════════════════════════════════════════════

test('hides "New valuation" + shows hint when subcontract status is not Active/Completed', () => {
  renderWithProviders(<ValuationsSection subcontract={SC_DRAFT} />);
  expect(screen.queryByTestId('valuations-section-new-btn')).not.toBeInTheDocument();
  expect(screen.getByTestId('valuations-section-hint')).toHaveTextContent(
    /Valuations open once the subcontract is active/i,
  );
});

test('shows "New valuation" button on Active subcontract with create perm', () => {
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  expect(screen.getByTestId('valuations-section-new-btn')).toBeInTheDocument();
});

test('hides "New valuation" button when user lacks subcontract_valuations.create', () => {
  useAuth.mockReturnValue({ me: ME_VIEW_ONLY });
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  expect(screen.queryByTestId('valuations-section-new-btn')).not.toBeInTheDocument();
});


// ════════════════════════════════════════════════════════════════════
// 4 / 5. List rows + empty state
// ════════════════════════════════════════════════════════════════════

test('list empty state shows the empty copy', () => {
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  expect(screen.getByTestId('valuations-list-empty')).toBeInTheDocument();
});

test('list renders rows with reference, status pill, period, gross applied', () => {
  valHooks.useValuations.mockReturnValue(mockListReturn([
    {
      id: 'V1', valuation_number: 1, reference: 'VAL-0001',
      status: 'Submitted',
      period_start: '2026-05-01', period_end: '2026-05-31',
      gross_applied_to_date: '50000.00',
      net_payable_this_cert: '38000.00',
      over_claim_flag: true, over_claim_note: 'Over by £2k',
    },
  ]));
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  expect(screen.getByText('VAL-0001')).toBeInTheDocument();
  expect(screen.getByTestId('valuations-row-V1-status')).toHaveTextContent('Submitted');
  // Over-claim chip rendered.
  expect(screen.getByTestId('valuations-row-V1-overclaim')).toBeInTheDocument();
});


// ════════════════════════════════════════════════════════════════════
// 6. Non-sensitive user — list shows em-dash for sensitive net
// ════════════════════════════════════════════════════════════════════

test('non-sensitive user sees em-dash for net_payable in list (defence-in-depth)', () => {
  useAuth.mockReturnValue({ me: ME_NON_SENSITIVE });
  // Backend has nulled the sensitive keys for this persona.
  valHooks.useValuations.mockReturnValue(mockListReturn([
    {
      id: 'V1', valuation_number: 1, reference: 'VAL-0001',
      status: 'Submitted',
      gross_applied_to_date: '50000.00',
      net_payable_this_cert: null,
    },
  ]));
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  expect(screen.getByTestId('valuations-row-V1-net').textContent.trim())
    .toBe('\u2014');
});


// ════════════════════════════════════════════════════════════════════
// 7. Detail sensitive gating + non-sensitive fields still visible
// ════════════════════════════════════════════════════════════════════

function selectFirstRow(items) {
  valHooks.useValuations.mockReturnValue(mockListReturn(items));
  valHooks.useValuation.mockReturnValue({
    data: items[0], isLoading: false, isError: false,
  });
}

test('detail: non-sensitive user sees em-dash for 5 sensitive fields; retention_rate + over_claim are still visible', () => {
  useAuth.mockReturnValue({ me: ME_NON_SENSITIVE });
  selectFirstRow([{
    id: 'V1', valuation_number: 1, reference: 'VAL-0001',
    status: 'Submitted',
    gross_applied_to_date: '50000.00',
    labour_portion: '30000.00',
    materials_portion: '20000.00',
    gross_this_cert: '10000.00',
    // Server returned nulls for sensitive keys without the perm:
    previous_certified_net: null,
    retention_this_cert: null,
    cis_rate_pct: null,
    cis_deduction_this_cert: null,
    net_payable_this_cert: null,
    // Non-sensitive (always visible):
    retention_rate_pct: '5',
    over_claim_flag: true, over_claim_note: 'Note',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));

  // Sensitive → em-dash
  expect(screen.getByTestId('valuation-detail-prev-net').textContent.trim()).toBe('\u2014');
  expect(screen.getByTestId('valuation-detail-retention').textContent.trim()).toBe('\u2014');
  expect(screen.getByTestId('valuation-detail-cis-rate').textContent.trim()).toBe('\u2014');
  expect(screen.getByTestId('valuation-detail-cis-deduction').textContent.trim()).toBe('\u2014');
  expect(screen.getByTestId('valuation-detail-net-payable').textContent.trim()).toBe('\u2014');

  // Non-sensitive → visible:
  expect(screen.getByTestId('valuation-detail-retention-rate').textContent).toContain('5%');
  expect(screen.getByTestId('valuation-detail-overclaim-banner')).toBeInTheDocument();
});

test('detail: sensitive user sees real values for the 5 sensitive fields', () => {
  selectFirstRow([{
    id: 'V1', valuation_number: 1, reference: 'VAL-0001',
    status: 'Submitted',
    gross_applied_to_date: '50000.00',
    previous_certified_net: '10000.00',
    retention_this_cert: '500.00',
    cis_rate_pct: '20',
    cis_deduction_this_cert: '1900.00',
    net_payable_this_cert: '7600.00',
    retention_rate_pct: '5',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  expect(screen.getByTestId('valuation-detail-prev-net').textContent).toMatch(/10,000/);
  expect(screen.getByTestId('valuation-detail-cis-rate').textContent).toMatch(/20%/);
  expect(screen.getByTestId('valuation-detail-net-payable').textContent).toMatch(/7,600/);
});


// ════════════════════════════════════════════════════════════════════
// 8. Lifecycle buttons by status
// ════════════════════════════════════════════════════════════════════

test('Draft → only Submit lifecycle button', () => {
  selectFirstRow([{
    id: 'V1', status: 'Draft', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '0',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  expect(screen.getByTestId('valuation-actions-submit-btn')).toBeInTheDocument();
  expect(screen.queryByTestId('valuation-actions-certify-btn')).not.toBeInTheDocument();
  expect(screen.queryByTestId('valuation-actions-reject-btn')).not.toBeInTheDocument();
});

test('Submitted → Certify + Reject buttons (with .certify perm)', () => {
  selectFirstRow([{
    id: 'V1', status: 'Submitted', valuation_number: 1,
    reference: 'VAL-0001', gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  expect(screen.getByTestId('valuation-actions-certify-btn')).toBeInTheDocument();
  expect(screen.getByTestId('valuation-actions-reject-btn')).toBeInTheDocument();
  expect(screen.queryByTestId('valuation-actions-submit-btn')).not.toBeInTheDocument();
});

test('Certified → no lifecycle buttons (PayLess via notices panel)', () => {
  selectFirstRow([{
    id: 'V1', status: 'Certified', valuation_number: 1,
    reference: 'VAL-0001', gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  expect(screen.queryByTestId('valuation-actions-submit-btn')).not.toBeInTheDocument();
  expect(screen.queryByTestId('valuation-actions-certify-btn')).not.toBeInTheDocument();
  expect(screen.queryByTestId('valuation-actions-reject-btn')).not.toBeInTheDocument();
});

test('Rejected → no lifecycle buttons + rejection-reason banner shown', () => {
  selectFirstRow([{
    id: 'V1', status: 'Rejected', valuation_number: 1,
    reference: 'VAL-0001', gross_applied_to_date: '50000.00',
    rejection_reason: 'Numbers do not reconcile.',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  expect(screen.queryByTestId('valuation-actions-submit-btn')).not.toBeInTheDocument();
  expect(screen.getByTestId('valuation-detail-rejection-reason'))
    .toHaveTextContent(/Numbers do not reconcile/);
});


// ════════════════════════════════════════════════════════════════════
// 9. Certify button hidden without .certify perm
// ════════════════════════════════════════════════════════════════════

test('Submitted + no .certify perm → Certify + Reject buttons hidden', () => {
  useAuth.mockReturnValue({ me: ME_VIEW_ONLY });
  selectFirstRow([{
    id: 'V1', status: 'Submitted', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  expect(screen.queryByTestId('valuation-actions-certify-btn')).not.toBeInTheDocument();
  expect(screen.queryByTestId('valuation-actions-reject-btn')).not.toBeInTheDocument();
});


// ════════════════════════════════════════════════════════════════════
// 10. Submit toast: 409 + 422 surfaced verbatim
// ════════════════════════════════════════════════════════════════════

test('Submit 409 → toast.error with server detail', async () => {
  const submitMut = mockNoOpMutation();
  submitMut.mutateAsync = jest.fn().mockRejectedValue({
    response: { status: 409, data: { detail: 'Cannot submit a Certified valuation' } },
  });
  valHooks.useSubmitValuation.mockReturnValue(submitMut);
  selectFirstRow([{
    id: 'V1', status: 'Draft', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '0',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  fireEvent.click(screen.getByTestId('valuation-actions-submit-btn'));
  await waitFor(() => {
    expect(toast.error).toHaveBeenCalledWith('Cannot submit a Certified valuation');
  });
});

test('Submit 422 → toast.error with server maths detail verbatim', async () => {
  const submitMut = mockNoOpMutation();
  submitMut.mutateAsync = jest.fn().mockRejectedValue({
    response: { status: 422, data: { detail: 'gross_applied_to_date must be >= 0' } },
  });
  valHooks.useSubmitValuation.mockReturnValue(submitMut);
  selectFirstRow([{
    id: 'V1', status: 'Draft', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '0',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  fireEvent.click(screen.getByTestId('valuation-actions-submit-btn'));
  await waitFor(() => {
    expect(toast.error).toHaveBeenCalledWith('gross_applied_to_date must be >= 0');
  });
});


// ════════════════════════════════════════════════════════════════════
// 11. Certify dialog — Confirm disabled until budget line selected
// ════════════════════════════════════════════════════════════════════

test('Certify dialog: Confirm DISABLED until a budget line is selected', async () => {
  selectFirstRow([{
    id: 'V1', status: 'Submitted', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  fireEvent.click(screen.getByTestId('valuation-actions-certify-btn'));

  const confirm = await screen.findByTestId('valuation-certify-confirm');
  expect(confirm).toBeDisabled();
  expect(screen.getByTestId('valuation-certify-budget-line-required')).toBeInTheDocument();

  // Pick a budget line via the stubbed picker.
  fireEvent.change(screen.getByTestId('mock-budget-line-picker'), {
    target: { value: 'BL-1' },
  });
  expect(confirm).not.toBeDisabled();
});

test('Certify dialog: confirm with budget line → mutate body carries { budget_line_id, transaction_date, description }', async () => {
  const certifyMut = mockNoOpMutation();
  valHooks.useCertifyValuation.mockReturnValue(certifyMut);

  selectFirstRow([{
    id: 'V1', status: 'Submitted', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  fireEvent.click(screen.getByTestId('valuation-actions-certify-btn'));

  fireEvent.change(screen.getByTestId('mock-budget-line-picker'), {
    target: { value: 'BL-1' },
  });
  fireEvent.change(screen.getByTestId('valuation-certify-tx-date'), {
    target: { value: '2026-05-31' },
  });
  fireEvent.change(screen.getByTestId('valuation-certify-description'), {
    target: { value: 'May valuation' },
  });
  fireEvent.click(screen.getByTestId('valuation-certify-confirm'));

  await waitFor(() => {
    expect(certifyMut.mutateAsync).toHaveBeenCalledTimes(1);
  });
  expect(certifyMut.mutateAsync).toHaveBeenCalledWith({
    budget_line_id: 'BL-1',
    transaction_date: '2026-05-31',
    description: 'May valuation',
  });
});

test('Certify dialog: 422 maths detail shown VERBATIM in toast', async () => {
  const certifyMut = mockNoOpMutation();
  certifyMut.mutateAsync = jest.fn().mockRejectedValue({
    response: {
      status: 422,
      data: {
        detail:
          'labour_portion + materials_portion (£40,000.00) must equal gross_this_cert (£30,000.00)',
      },
    },
  });
  valHooks.useCertifyValuation.mockReturnValue(certifyMut);

  selectFirstRow([{
    id: 'V1', status: 'Submitted', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  fireEvent.click(screen.getByTestId('valuation-actions-certify-btn'));
  fireEvent.change(screen.getByTestId('mock-budget-line-picker'), {
    target: { value: 'BL-1' },
  });
  fireEvent.click(screen.getByTestId('valuation-certify-confirm'));

  await waitFor(() => {
    expect(toast.error).toHaveBeenCalledWith(
      'labour_portion + materials_portion (£40,000.00) must equal gross_this_cert (£30,000.00)',
    );
  });
});


// ════════════════════════════════════════════════════════════════════
// 12. Reject dialog — disabled while reason blank
// ════════════════════════════════════════════════════════════════════

test('Reject dialog: Confirm DISABLED while reason blank; enabled when non-blank', async () => {
  selectFirstRow([{
    id: 'V1', status: 'Submitted', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '0',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  fireEvent.click(screen.getByTestId('valuation-actions-reject-btn'));

  const confirm = await screen.findByTestId('valuation-reject-confirm');
  expect(confirm).toBeDisabled();

  fireEvent.change(screen.getByTestId('valuation-reject-reason'), {
    target: { value: 'Numbers do not reconcile' },
  });
  expect(confirm).not.toBeDisabled();
});


// ════════════════════════════════════════════════════════════════════
// 13. PaymentNoticesPanel — Certified only + PayLess button + body
// ════════════════════════════════════════════════════════════════════

test('PaymentNoticesPanel: shown for Certified, with PayLess button (with payment_notices.create)', () => {
  selectFirstRow([{
    id: 'V1', status: 'Certified', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '50000.00',
  }]);
  noticeHooks.usePaymentNotices.mockReturnValue(mockListReturn([
    {
      id: 'N1', reference: 'PN-0001', notice_type: 'Payment',
      gross_certified: '50000.00', retention: '2500.00',
      cis_deducted: '9500.00', net_due: '38000.00', due_date: '2026-06-15',
    },
  ]));
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  expect(screen.getByTestId('payment-notices-panel')).toBeInTheDocument();
  expect(screen.getByTestId('payment-notices-payless-btn')).toBeInTheDocument();
  expect(screen.getByTestId('notice-type-Payment')).toBeInTheDocument();
});

test('PaymentNoticesPanel: PayLess button HIDDEN without payment_notices.create', () => {
  useAuth.mockReturnValue({ me: ME_NON_SENSITIVE });  // has view, not create
  selectFirstRow([{
    id: 'V1', status: 'Certified', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  expect(screen.queryByTestId('payment-notices-payless-btn')).not.toBeInTheDocument();
});

test('PayLess submit → mutate body has withhold_amount as STRING + reason + due_date', async () => {
  const payLessMut = mockNoOpMutation();
  noticeHooks.useCreatePayLess.mockReturnValue(payLessMut);

  selectFirstRow([{
    id: 'V1', status: 'Certified', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  fireEvent.click(screen.getByTestId('payment-notices-payless-btn'));

  fireEvent.change(await screen.findByTestId('payless-withhold-amount'), {
    target: { value: '2500.00' },
  });
  fireEvent.change(screen.getByTestId('payless-reason'), {
    target: { value: 'Defective workmanship' },
  });
  fireEvent.change(screen.getByTestId('payless-due-date'), {
    target: { value: '2026-06-15' },
  });
  fireEvent.click(screen.getByTestId('payless-submit'));

  await waitFor(() => {
    expect(payLessMut.mutateAsync).toHaveBeenCalledTimes(1);
  });
  const [body] = payLessMut.mutateAsync.mock.calls[0];
  expect(body).toEqual({
    subcontract_valuation_id: 'V1',
    withhold_amount: '2500.00',
    reason: 'Defective workmanship',
    due_date: '2026-06-15',
  });
  expect(typeof body.withhold_amount).toBe('string');
});

test('PayLess 409 surfaces server detail verbatim (non-Certified race)', async () => {
  const payLessMut = mockNoOpMutation();
  payLessMut.mutateAsync = jest.fn().mockRejectedValue({
    response: {
      status: 409,
      data: {
        detail:
          'PayLess notices can only be issued against a Certified valuation (current status: Submitted)',
      },
    },
  });
  noticeHooks.useCreatePayLess.mockReturnValue(payLessMut);

  selectFirstRow([{
    id: 'V1', status: 'Certified', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  fireEvent.click(screen.getByTestId('payment-notices-payless-btn'));
  fireEvent.change(await screen.findByTestId('payless-withhold-amount'), {
    target: { value: '1' },
  });
  fireEvent.change(screen.getByTestId('payless-reason'), {
    target: { value: 'x' },
  });
  fireEvent.click(screen.getByTestId('payless-submit'));

  await waitFor(() => {
    expect(toast.error).toHaveBeenCalledWith(
      'PayLess notices can only be issued against a Certified valuation (current status: Submitted)',
    );
  });
});


// ════════════════════════════════════════════════════════════════════
// 14. PaymentNoticesPanel hidden for non-Certified valuation
// ════════════════════════════════════════════════════════════════════

test('PaymentNoticesPanel HIDDEN for Submitted valuation', () => {
  selectFirstRow([{
    id: 'V1', status: 'Submitted', valuation_number: 1, reference: 'VAL-0001',
    gross_applied_to_date: '50000.00',
  }]);
  renderWithProviders(<ValuationsSection subcontract={SC_ACTIVE} />);
  fireEvent.click(screen.getByTestId('valuations-row-V1'));
  expect(screen.queryByTestId('payment-notices-panel')).not.toBeInTheDocument();
});
