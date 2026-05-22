/**
 * <POApprovalPanel/> tests — Chat 26 §R7.3 (Batch 1).
 *
 * Asserts:
 *   - Panel renders only when status === 'pending_approval' AND an open
 *     approval row exists (resolution === null).
 *   - Budget-snapshot table renders all over-budget fields verbatim
 *     (decimal strings — no parseFloat path inside the test).
 *   - Read-only persona → £ em-dash via <SensitiveValue/>.
 *   - Approve calls approvePO with optional reason; creator-cannot-
 *     approve (Approve button absent / disabled twin shown).
 *   - Reject calls rejectPO; reason required (confirm disabled until
 *     non-whitespace).
 *   - Send-back is NOT in this panel (it lives in <POActionButtons/>).
 */
import { screen, fireEvent, waitFor } from '@testing-library/react';
import POApprovalPanel from '../POApprovalPanel';
import { renderWithProviders } from '../../../test/renderWithProviders';

jest.mock('../../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../hooks/purchaseOrders', () => ({
  usePoTransition: jest.fn(),
  usePOApprovals: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const { useAuth } = require('../../../context/AuthContext');
const { usePoTransition, usePOApprovals } = require('../../../hooks/purchaseOrders');
const { toast } = require('sonner');

const ME_APPROVER = {
  id: 'user-app',
  permissions: ['pos.view', 'pos.view_sensitive', 'pos.approve'],
};
const ME_READONLY = { id: 'user-ro', permissions: ['pos.view'] };

const SNAPSHOT_ROW = {
  budget_line_id: 'bl-1',
  cost_code: 'CC-100',
  current_budget: '10000.00',
  committed_value: '8000.00',
  actuals_to_date: '5000.00',
  this_po_net: '3000.00',
  projected_total: '11000.00',
  over_by: '1000.00',
  is_overrun: true,
};

const OPEN_APPROVAL = {
  id: 'appr-1',
  purchase_order_id: 'po-1',
  submitted_by: 'user-someone-else',
  submitted_at: '2026-02-10T12:34:56Z',
  submission_reason: 'Materials overrun',
  budget_snapshot: [SNAPSHOT_ROW],
  resolution: null,
  resolved_by: null,
  resolved_at: null,
  resolution_notes: null,
};

const PO_PENDING = {
  id: 'po-1', status: 'pending_approval', submitted_by: 'user-someone-else',
};


function setMockTransition({ mutateAsync = jest.fn().mockResolvedValue({}), isPending = false } = {}) {
  usePoTransition.mockReturnValue({ mutateAsync, isPending });
}


describe('<POApprovalPanel/> R7.3', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setMockTransition();
    usePOApprovals.mockReturnValue({
      data: { items: [OPEN_APPROVAL] }, isLoading: false,
    });
  });

  test('renders panel + snapshot ONLY when status==pending_approval AND open row exists', () => {
    useAuth.mockReturnValue({ me: ME_APPROVER });
    renderWithProviders(<POApprovalPanel po={PO_PENDING} />);
    expect(screen.getByTestId('po-approval-panel')).toBeInTheDocument();
    expect(screen.getByTestId('po-approval-snapshot')).toBeInTheDocument();
    expect(screen.getByTestId('po-approval-snapshot-row-bl-1')).toBeInTheDocument();
  });

  test('panel hides for approved PO (no longer pending) — history-only path', () => {
    useAuth.mockReturnValue({ me: ME_APPROVER });
    renderWithProviders(
      <POApprovalPanel po={{ ...PO_PENDING, status: 'approved' }} />,
    );
    expect(screen.queryByTestId('po-approval-panel')).not.toBeInTheDocument();
  });

  test('snapshot renders every over-budget field verbatim (decimal strings, formatted)', () => {
    useAuth.mockReturnValue({ me: ME_APPROVER });
    renderWithProviders(<POApprovalPanel po={PO_PENDING} />);
    const row = screen.getByTestId('po-approval-snapshot-row-bl-1');
    // £10,000.00, £8,000.00, £5,000.00, £3,000.00, £11,000.00, £1,000.00
    expect(row).toHaveTextContent('CC-100');
    expect(row).toHaveTextContent('£10,000.00');
    expect(row).toHaveTextContent('£8,000.00');
    expect(row).toHaveTextContent('£5,000.00');
    expect(row).toHaveTextContent('£3,000.00');
    expect(row).toHaveTextContent('£11,000.00');
    expect(row).toHaveTextContent('£1,000.00');
  });

  test('read-only persona renders £ em-dashes (no sensitive figures)', () => {
    useAuth.mockReturnValue({ me: ME_READONLY });
    renderWithProviders(<POApprovalPanel po={PO_PENDING} />);
    const row = screen.getByTestId('po-approval-snapshot-row-bl-1');
    expect(row).not.toHaveTextContent('£10,000.00');
    // SensitiveValue renders an em-dash placeholder.
    expect(row).toHaveTextContent('—');
  });

  test('Approve calls approvePO with optional reason', async () => {
    const mutateAsync = jest.fn().mockResolvedValue({});
    // Inject the approve verb specifically — usePoTransition is called
    // once for approve, once for reject; both share the same mock here.
    usePoTransition.mockReturnValue({ mutateAsync, isPending: false });
    useAuth.mockReturnValue({ me: ME_APPROVER });
    renderWithProviders(<POApprovalPanel po={PO_PENDING} />);
    fireEvent.click(screen.getByTestId('po-approval-approve-btn'));
    const confirm = await screen.findByTestId('po-approval-approve-confirm');
    // Reason optional — confirm enabled with no text.
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({}));
    expect(toast.success).toHaveBeenCalledWith('Approved');
  });

  test('Reject requires reason; confirm disabled until non-whitespace', async () => {
    const mutateAsync = jest.fn().mockResolvedValue({});
    usePoTransition.mockReturnValue({ mutateAsync, isPending: false });
    useAuth.mockReturnValue({ me: ME_APPROVER });
    renderWithProviders(<POApprovalPanel po={PO_PENDING} />);
    fireEvent.click(screen.getByTestId('po-approval-reject-btn'));
    const confirm = await screen.findByTestId('po-approval-reject-confirm');
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId('po-approval-reject-reason'), {
      target: { value: '   ' },
    });
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId('po-approval-reject-reason'), {
      target: { value: 'budget breach' },
    });
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ reason: 'budget breach' }));
  });

  test('creator-cannot-approve: submitter sees disabled Approve twin, no Reject', () => {
    useAuth.mockReturnValue({ me: ME_APPROVER });
    // Submitter IS the approver — self-approval guard fires.
    renderWithProviders(
      <POApprovalPanel po={{ ...PO_PENDING, submitted_by: 'user-app' }} />,
    );
    expect(screen.queryByTestId('po-approval-approve-btn')).not.toBeInTheDocument();
    expect(screen.getByTestId('po-approval-approve-self-disabled')).toBeDisabled();
    expect(screen.queryByTestId('po-approval-reject-btn')).not.toBeInTheDocument();
  });

  test('send-back is NOT rendered in this panel (it lives in POActionButtons)', () => {
    useAuth.mockReturnValue({ me: ME_APPROVER });
    renderWithProviders(<POApprovalPanel po={PO_PENDING} />);
    expect(screen.queryByText(/send back/i)).not.toBeInTheDocument();
  });

  test('panel renders history-only when pending but no open row returned', () => {
    usePOApprovals.mockReturnValue({
      data: { items: [{ ...OPEN_APPROVAL, resolution: 'approved' }] },
      isLoading: false,
    });
    useAuth.mockReturnValue({ me: ME_APPROVER });
    renderWithProviders(<POApprovalPanel po={PO_PENDING} />);
    expect(screen.queryByTestId('po-approval-panel')).not.toBeInTheDocument();
    expect(screen.getByTestId('po-approval-history')).toBeInTheDocument();
  });
});
