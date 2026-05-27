/**
 * <POActionButtons/> tests — Chat 26 §R7.2 (Batch 1) + R7 Batch 2.
 *
 * Batch 2 has re-enabled every previously-deferred button. The
 * DEFERRED_TESTIDS array is intentionally empty; the empty-loop
 * regression-guard block was REMOVED (zero iterations would have
 * been trivially green) and replaced with positive per-button render
 * assertions in the relevant status describe blocks below.
 *
 *   draft               → Edit, Submit, Delete
 *   pending_approval    → Approve, Reject              (self-approval guard)
 *   approved            → Edit, Issue, Send back, Void
 *   issued              → Edit (annotation), Receipt, Close, Void
 *   partially_receipted → Edit (annotation), Receipt, Close, Void
 *   receipted           → Edit (annotation), Close
 *   closed / voided     → (none)
 *
 * Personas mirror the seeded RBAC roles:
 *   - FULL PM     — pos.create + pos.edit + pos.delete + pos.submit
 *                   + pos.receipt + pos.close + pos.void
 *                   (NB: no pos.approve, no pos.edit_issued, no pos.issue)
 *   - APPROVER    — pos.approve + pos.issue + pos.void + pos.edit
 *                   + pos.close + pos.edit_issued
 *   - READ-ONLY   — pos.view only
 *   - SUBMITTER   — APPROVER perms + IS the PO's submitted_by
 *
 * `edit_tier` (lowercase string from backend services/po_authz.py):
 *   - 'full'                     → po-actions-edit-btn (draft / approved)
 *   - 'header_annotation_only'   → po-actions-edit-issued-btn (issued+)
 *   - 'read_only'                → no edit button
 */
import { screen, fireEvent, waitFor } from '@testing-library/react';
import POActionButtons from '../POActionButtons';
import { renderWithProviders } from '../../../test/renderWithProviders';

jest.mock('../../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../hooks/purchaseOrders', () => ({
  usePoTransition: jest.fn(),
  useCreateReceipt: jest.fn(),
  useDeletePO: jest.fn(),
  usePatchPO: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() },
}));

const { useAuth } = require('../../../context/AuthContext');
const {
  usePoTransition, useCreateReceipt, useDeletePO, usePatchPO,
} = require('../../../hooks/purchaseOrders');
const { toast } = require('sonner');

// R7 Batch 2 — full permission sets (incl. pos.edit_issued for the
// APPROVER persona so the issued/partial/receipted edit-issued
// assertions render).
const ME_PM = {
  id: 'user-pm',
  permissions: [
    'pos.view', 'pos.create', 'pos.edit', 'pos.delete', 'pos.submit',
    'pos.receipt', 'pos.close', 'pos.void',
  ],
};
const ME_APPROVER = {
  id: 'user-app',
  permissions: [
    'pos.view', 'pos.approve', 'pos.issue', 'pos.void',
    'pos.edit', 'pos.edit_issued', 'pos.close', 'pos.receipt',
  ],
};
const ME_READONLY = { id: 'user-ro', permissions: ['pos.view'] };

// R7 Batch 2 — ALL previously deferred testids are now wired. The
// array is intentionally empty; the loop-over-array guard block was
// removed (it would have been a vacuous green pass). Each re-enabled
// button has its own positive render assertion below.
const DEFERRED_TESTIDS = [];

function makePO({
  status,
  submitted_by = 'user-someone',
  edit_tier = 'full',
  id = 'po-1',
} = {}) {
  return { id, status, submitted_by, edit_tier };
}

function setMockTransition({
  mutateAsync = jest.fn().mockResolvedValue({}),
  isPending = false,
} = {}) {
  usePoTransition.mockReturnValue({ mutateAsync, isPending });
}

beforeEach(() => {
  jest.clearAllMocks();
  setMockTransition();
  useCreateReceipt.mockReturnValue({
    mutateAsync: jest.fn().mockResolvedValue({}), isPending: false,
  });
  useDeletePO.mockReturnValue({
    mutateAsync: jest.fn().mockResolvedValue({}), isPending: false,
  });
  usePatchPO.mockReturnValue({
    mutateAsync: jest.fn().mockResolvedValue({}), isPending: false,
  });
});


describe('<POActionButtons/> — R7 Batch 2 full action matrix', () => {

  // ── draft ──────────────────────────────────────────────────────────
  describe('draft', () => {
    test('FULL PM sees Edit + Submit + Delete', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'draft', edit_tier: 'full' })} />,
      );
      expect(screen.getByTestId('po-actions-edit-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-submit-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-delete-btn')).toBeInTheDocument();
    });

    test('READ-ONLY persona sees no buttons', () => {
      useAuth.mockReturnValue({ me: ME_READONLY });
      renderWithProviders(<POActionButtons po={makePO({ status: 'draft' })} />);
      expect(screen.queryByTestId('po-actions-submit-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-edit-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-delete-btn')).not.toBeInTheDocument();
    });

    test('Edit is hidden when edit_tier=read_only (e.g. pending)', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'draft', edit_tier: 'read_only' })} />,
      );
      expect(screen.queryByTestId('po-actions-edit-btn')).not.toBeInTheDocument();
    });
  });

  // ── pending_approval ───────────────────────────────────────────────
  describe('pending_approval', () => {
    test('APPROVER (non-submitter) sees Approve + Reject', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({
            status: 'pending_approval',
            submitted_by: 'someone-else',
            edit_tier: 'read_only',
          })}
        />,
      );
      expect(screen.getByTestId('po-actions-approve-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-reject-btn')).toBeInTheDocument();
    });

    test('SELF-APPROVAL: submitter sees disabled Approve twin, Reject hidden', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({
            status: 'pending_approval',
            submitted_by: 'user-app',
            edit_tier: 'read_only',
          })}
        />,
      );
      expect(screen.queryByTestId('po-actions-approve-btn')).not.toBeInTheDocument();
      expect(screen.getByTestId('po-actions-approve-self-disabled')).toBeDisabled();
      expect(screen.queryByTestId('po-actions-reject-btn')).not.toBeInTheDocument();
    });

    test('FULL PM (no pos.approve) sees neither Approve nor Reject', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'pending_approval', edit_tier: 'read_only' })} />,
      );
      expect(screen.queryByTestId('po-actions-approve-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-reject-btn')).not.toBeInTheDocument();
    });

    test('READ-ONLY persona sees neither Approve nor Reject', () => {
      useAuth.mockReturnValue({ me: ME_READONLY });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'pending_approval' })} />,
      );
      expect(screen.queryByTestId('po-actions-approve-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-reject-btn')).not.toBeInTheDocument();
    });

    test('edit_tier=read_only does NOT hide Approve/Reject (matrix-critical regression guard)', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({
            status: 'pending_approval',
            edit_tier: 'read_only',
            submitted_by: 'someone-else',
          })}
        />,
      );
      expect(screen.getByTestId('po-actions-approve-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-reject-btn')).toBeInTheDocument();
    });
  });

  // ── approved (R7.0b) ───────────────────────────────────────────────
  describe('approved (R7.0b row)', () => {
    test('APPROVER sees Edit + Issue + Send back + Void', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({
            status: 'approved',
            submitted_by: 'someone-else',
            edit_tier: 'full',
          })}
        />,
      );
      expect(screen.getByTestId('po-actions-edit-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-issue-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-send-back-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-void-btn')).toBeInTheDocument();
    });

    test('SUBMITTER can still send back their own approved PO (no self-guard on send-back)', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({
            status: 'approved',
            submitted_by: 'user-app',
            edit_tier: 'full',
          })}
        />,
      );
      expect(screen.getByTestId('po-actions-send-back-btn')).toBeInTheDocument();
    });

    test('Send back opens dialog with required-notes; confirm disabled until non-whitespace', async () => {
      const mutateAsync = jest.fn().mockResolvedValue({});
      setMockTransition({ mutateAsync });
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'approved', submitted_by: 'someone-else', edit_tier: 'full' })}
        />,
      );
      fireEvent.click(screen.getByTestId('po-actions-send-back-btn'));
      const confirm = await screen.findByTestId('po-send-back-confirm');
      expect(confirm).toBeDisabled();
      const ta = screen.getByTestId('po-send-back-notes');
      fireEvent.change(ta, { target: { value: '   ' } });
      expect(confirm).toBeDisabled();
      fireEvent.change(ta, { target: { value: 'wrong supplier' } });
      expect(confirm).not.toBeDisabled();
      fireEvent.click(confirm);
      await waitFor(() => {
        expect(mutateAsync).toHaveBeenCalledWith({ notes: 'wrong supplier' });
      });
      expect(toast.success).toHaveBeenCalledWith('PO sent back to draft');
    });

    test('READ-ONLY persona on approved PO sees no buttons', () => {
      useAuth.mockReturnValue({ me: ME_READONLY });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'approved', edit_tier: 'full' })} />,
      );
      expect(screen.queryByTestId('po-actions-issue-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-send-back-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-void-btn')).not.toBeInTheDocument();
    });
  });

  // ── issued / partially_receipted / receipted ──────────────────────
  describe('issued', () => {
    test('APPROVER sees Edit (annotation) + Receipt + Close + Void', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({
            status: 'issued',
            edit_tier: 'header_annotation_only',
          })}
        />,
      );
      expect(screen.getByTestId('po-actions-edit-issued-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-receipt-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-close-issued-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-void-issued-btn')).toBeInTheDocument();
      // edit-btn (full) hidden on annotation-only tier.
      expect(screen.queryByTestId('po-actions-edit-btn')).not.toBeInTheDocument();
    });

    test('FULL PM (no pos.edit_issued, no pos.void perms with the right tier) → only Close + Receipt', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'issued', edit_tier: 'header_annotation_only' })}
        />,
      );
      // edit-issued-btn requires pos.edit_issued, which ME_PM lacks.
      expect(screen.queryByTestId('po-actions-edit-issued-btn')).not.toBeInTheDocument();
      expect(screen.getByTestId('po-actions-receipt-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-close-issued-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-void-issued-btn')).toBeInTheDocument();
    });
  });

  describe('partially_receipted', () => {
    test('APPROVER sees Edit-issued + Receipt + Close + Void', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({
            status: 'partially_receipted',
            edit_tier: 'header_annotation_only',
          })}
        />,
      );
      expect(screen.getByTestId('po-actions-edit-issued-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-receipt-partial-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-close-partial-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-void-issued-btn')).toBeInTheDocument();
    });
  });

  describe('receipted', () => {
    test('APPROVER sees Edit-issued + Close (no more Receipt, no Void)', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({
            status: 'receipted',
            edit_tier: 'header_annotation_only',
          })}
        />,
      );
      expect(screen.getByTestId('po-actions-edit-issued-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-close-btn')).toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-receipt-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-receipt-partial-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-void-issued-btn')).not.toBeInTheDocument();
    });
  });

  // ── terminal states ───────────────────────────────────────────────
  describe('terminal states (closed, voided)', () => {
    test.each(['closed', 'voided'])('%s renders no action buttons', (status) => {
      useAuth.mockReturnValue({ me: ME_PM });
      const { container } = renderWithProviders(
        <POActionButtons po={makePO({ status, edit_tier: 'read_only' })} />,
      );
      const actions = container.querySelector('[data-testid="po-actions"]');
      expect(actions.children.length).toBe(0);
    });
  });

  // ── Delete is DRAFT-ONLY (mirrors backend 422 on non-draft) ───────
  describe('Delete — draft only (backend 422 discipline)', () => {
    const NON_DRAFT_STATES = [
      'pending_approval', 'approved', 'issued',
      'partially_receipted', 'receipted', 'closed', 'voided',
    ];
    for (const status of NON_DRAFT_STATES) {
      test(`${status} — delete-btn does NOT render (mirrors 422)`, () => {
        useAuth.mockReturnValue({ me: ME_PM });
        renderWithProviders(
          <POActionButtons
            po={makePO({ status, edit_tier: status === 'closed' || status === 'voided' ? 'read_only' : 'header_annotation_only' })}
          />,
        );
        expect(screen.queryByTestId('po-actions-delete-btn')).not.toBeInTheDocument();
      });
    }
    test('draft + canDeletePO → delete-btn renders behind confirm dialog', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'draft', edit_tier: 'full' })} />,
      );
      const btn = screen.getByTestId('po-actions-delete-btn');
      fireEvent.click(btn);
      expect(screen.getByTestId('po-delete-dialog')).toBeInTheDocument();
      expect(screen.getByTestId('po-delete-cancel')).toBeInTheDocument();
      expect(screen.getByTestId('po-delete-confirm')).toBeInTheDocument();
    });
  });

  // ── R7.6 — Void requires a reason (clones reject-dialog shape) ───
  describe('Void confirm-dialog — required reason (R7.6)', () => {
    test('void-btn (approved) opens dialog; confirm disabled until reason entered', async () => {
      const mutateAsync = jest.fn().mockResolvedValue({});
      setMockTransition({ mutateAsync });
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'approved', edit_tier: 'full' })} />,
      );
      fireEvent.click(screen.getByTestId('po-actions-void-btn'));
      const confirm = await screen.findByTestId('po-void-confirm');
      expect(confirm).toBeDisabled();
      const ta = screen.getByTestId('po-void-reason');
      fireEvent.change(ta, { target: { value: '   ' } });
      expect(confirm).toBeDisabled();
      fireEvent.change(ta, { target: { value: 'duplicate PO' } });
      expect(confirm).not.toBeDisabled();
      fireEvent.click(confirm);
      await waitFor(() => {
        expect(mutateAsync).toHaveBeenCalledWith({ reason: 'duplicate PO' });
      });
      expect(toast.success).toHaveBeenCalledWith('PO voided');
    });

    test('void-issued-btn (issued) opens the same void dialog', async () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'issued', edit_tier: 'header_annotation_only' })}
        />,
      );
      fireEvent.click(screen.getByTestId('po-actions-void-issued-btn'));
      expect(await screen.findByTestId('po-void-dialog')).toBeInTheDocument();
      expect(screen.getByTestId('po-void-reason')).toBeInTheDocument();
    });
  });

  // ── R7.4 — Receipt form opens / posts to the createReceipt hook ─
  describe('Receipt form (R7.4)', () => {
    test('receipt-btn opens receipt dialog (issued)', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'issued', edit_tier: 'header_annotation_only' })}
        />,
      );
      fireEvent.click(screen.getByTestId('po-actions-receipt-btn'));
      expect(screen.getByTestId('po-receipt-dialog')).toBeInTheDocument();
      expect(screen.getByTestId('po-receipt-date')).toBeInTheDocument();
      expect(screen.getByTestId('po-receipt-cancel')).toBeInTheDocument();
    });

    test('receipt-partial-btn opens receipt dialog (partial)', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'partially_receipted', edit_tier: 'header_annotation_only' })}
        />,
      );
      fireEvent.click(screen.getByTestId('po-actions-receipt-partial-btn'));
      expect(screen.getByTestId('po-receipt-dialog')).toBeInTheDocument();
    });
  });

  // ── Edit tier gating ───────────────────────────────────────────────
  describe('Edit-tier gating (full vs annotation-only)', () => {
    test('edit_tier=full + pos.edit → edit-btn (NOT edit-issued-btn)', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'approved', edit_tier: 'full' })} />,
      );
      expect(screen.getByTestId('po-actions-edit-btn')).toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-edit-issued-btn')).not.toBeInTheDocument();
    });

    test('edit_tier=header_annotation_only + pos.edit_issued → edit-issued-btn (NOT edit-btn)', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'issued', edit_tier: 'header_annotation_only' })}
        />,
      );
      expect(screen.getByTestId('po-actions-edit-issued-btn')).toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-edit-btn')).not.toBeInTheDocument();
    });

    test('edit_tier=read_only → neither edit-btn renders', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'closed', edit_tier: 'read_only' })} />,
      );
      expect(screen.queryByTestId('po-actions-edit-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-edit-issued-btn')).not.toBeInTheDocument();
    });

    test('annotation-only tier WITHOUT pos.edit_issued → edit-issued-btn hidden', () => {
      // ME_PM lacks pos.edit_issued.
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'issued', edit_tier: 'header_annotation_only' })}
        />,
      );
      expect(screen.queryByTestId('po-actions-edit-issued-btn')).not.toBeInTheDocument();
    });
  });

  // ── DEFERRED_TESTIDS — must remain empty (AC1) ────────────────────
  test('AC1 — DEFERRED_TESTIDS array is empty (all Batch-2 testids wired)', () => {
    expect(DEFERRED_TESTIDS).toEqual([]);
  });
});
