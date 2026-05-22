/**
 * <POActionButtons/> tests — Chat 26 §R7.2 (Batch 1).
 *
 * Per-status × per-persona render matrix. Personas mirror the seeded
 * RBAC roles used in the backend tests:
 *   - FULL PM           — pos.create + pos.edit + pos.delete + pos.submit
 *                         + pos.receipt + pos.close + pos.void
 *   - APPROVER          — pos.approve (+ pos.issue, pos.void)
 *   - READ-ONLY         — pos.view only
 *
 * Plus:
 *   - approved row (Issue / Send back / Void)
 *   - self-approval rule (submitter cannot Approve/Reject their own
 *     pending PO; send-back is allowed)
 *   - edit_tier handling: 'full' / 'header_annotation_only' / 'read_only'
 *     (case-insensitive normalisation; absent → read_only)
 */
import { screen, fireEvent, waitFor } from '@testing-library/react';
import POActionButtons from '../POActionButtons';
import { renderWithProviders } from '../../../test/renderWithProviders';

jest.mock('../../../context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../hooks/purchaseOrders', () => ({
  usePoTransition: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const { useAuth } = require('../../../context/AuthContext');
const { usePoTransition } = require('../../../hooks/purchaseOrders');
const { toast } = require('sonner');

const ME_PM       = { id: 'user-pm', permissions: ['pos.view', 'pos.create', 'pos.edit', 'pos.delete', 'pos.submit', 'pos.receipt', 'pos.close', 'pos.void'] };
const ME_APPROVER = { id: 'user-app', permissions: ['pos.view', 'pos.approve', 'pos.issue', 'pos.void', 'pos.edit'] };
const ME_READONLY = { id: 'user-ro', permissions: ['pos.view'] };

function makePO({ status, submitted_by = 'user-someone', edit_tier = 'full', id = 'po-1' } = {}) {
  return { id, status, submitted_by, edit_tier };
}

function setMockTransition({ mutateAsync = jest.fn().mockResolvedValue({}), isPending = false } = {}) {
  usePoTransition.mockReturnValue({ mutateAsync, isPending });
}


describe('<POActionButtons/> R7.2 — status × persona × edit_tier × self-approval', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setMockTransition();
  });

  // ── draft ──────────────────────────────────────────────────────────
  describe('draft', () => {
    test('FULL PM sees Submit, Edit, Delete', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'draft' })} projectId="p-1" />,
      );
      expect(screen.getByTestId('po-actions-submit-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-edit-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-delete-btn')).toBeInTheDocument();
    });

    test('READ-ONLY persona sees no buttons', () => {
      useAuth.mockReturnValue({ me: ME_READONLY });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'draft' })} projectId="p-1" />,
      );
      expect(screen.queryByTestId('po-actions-submit-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-edit-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-delete-btn')).not.toBeInTheDocument();
    });
  });

  // ── pending_approval ───────────────────────────────────────────────
  describe('pending_approval', () => {
    test('APPROVER (non-submitter) sees Approve + Reject', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'pending_approval', submitted_by: 'someone-else' })}
          projectId="p-1"
        />,
      );
      expect(screen.getByTestId('po-actions-approve-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-reject-btn')).toBeInTheDocument();
    });

    test('SELF-APPROVAL: submitter sees Approve disabled, Reject hidden', () => {
      // approver perm + IS the submitter
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'pending_approval', submitted_by: 'user-app' })}
          projectId="p-1"
        />,
      );
      // No active Approve button (active button has testid -approve-btn)
      expect(screen.queryByTestId('po-actions-approve-btn')).not.toBeInTheDocument();
      // Disabled placeholder is shown so user sees the explanation.
      expect(screen.getByTestId('po-actions-approve-self-disabled')).toBeDisabled();
      // Reject hidden entirely (no tooltip needed; the disabled Approve
      // placeholder communicates the rule).
      expect(screen.queryByTestId('po-actions-reject-btn')).not.toBeInTheDocument();
    });

    test('READ-ONLY persona sees neither Approve nor Reject', () => {
      useAuth.mockReturnValue({ me: ME_READONLY });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'pending_approval' })} projectId="p-1"
        />,
      );
      expect(screen.queryByTestId('po-actions-approve-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-reject-btn')).not.toBeInTheDocument();
    });
  });

  // ── approved (R7.0b) ───────────────────────────────────────────────
  describe('approved (R7.0b row)', () => {
    test('APPROVER sees Issue + Send back + Void', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'approved', submitted_by: 'someone-else' })}
          projectId="p-1"
        />,
      );
      expect(screen.getByTestId('po-actions-issue-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-send-back-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-void-btn')).toBeInTheDocument();
    });

    test('SUBMITTER can still send back their own approved PO (no self-guard on send-back)', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'approved', submitted_by: 'user-app' })}
          projectId="p-1"
        />,
      );
      // Send back is the correction path — must remain available.
      expect(screen.getByTestId('po-actions-send-back-btn')).toBeInTheDocument();
    });

    test('Send back opens dialog with required-notes; confirm disabled until non-whitespace', async () => {
      const mutateAsync = jest.fn().mockResolvedValue({});
      setMockTransition({ mutateAsync });
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'approved', submitted_by: 'someone-else' })}
          projectId="p-1"
        />,
      );
      fireEvent.click(screen.getByTestId('po-actions-send-back-btn'));
      // Dialog content renders via portal — search the document.
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
        <POActionButtons po={makePO({ status: 'approved' })} projectId="p-1" />,
      );
      expect(screen.queryByTestId('po-actions-issue-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-send-back-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-void-btn')).not.toBeInTheDocument();
    });
  });

  // ── issued ─────────────────────────────────────────────────────────
  describe('issued', () => {
    test('FULL PM sees Receipt + Void + Close + Edit (issued)', () => {
      useAuth.mockReturnValue({
        me: { ...ME_PM, permissions: [...ME_PM.permissions, 'pos.edit_issued'] },
      });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'issued' })} projectId="p-1" />,
      );
      expect(screen.getByTestId('po-actions-receipt-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-void-issued-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-close-issued-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-edit-issued-btn')).toBeInTheDocument();
    });
  });

  // ── partially_receipted / receipted / terminal ────────────────────
  describe('partially_receipted', () => {
    test('FULL PM sees Receipt + Close', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'partially_receipted' })} projectId="p-1" />,
      );
      expect(screen.getByTestId('po-actions-receipt-partial-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-close-partial-btn')).toBeInTheDocument();
    });
  });

  describe('terminal states (closed, voided)', () => {
    test('closed renders no action buttons', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      const { container } = renderWithProviders(
        <POActionButtons po={makePO({ status: 'closed' })} projectId="p-1" />,
      );
      const actions = container.querySelector('[data-testid="po-actions"]');
      expect(actions.children.length).toBe(0);
    });
    test('voided renders no action buttons', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      const { container } = renderWithProviders(
        <POActionButtons po={makePO({ status: 'voided' })} projectId="p-1" />,
      );
      const actions = container.querySelector('[data-testid="po-actions"]');
      expect(actions.children.length).toBe(0);
    });
  });

  // ── edit_tier handling (P0.12) ─────────────────────────────────────
  describe('edit_tier handling', () => {
    test("read_only suppresses ALL mutating buttons", () => {
      useAuth.mockReturnValue({ me: ME_PM });
      const { container } = renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'draft', edit_tier: 'read_only' })}
          projectId="p-1"
        />,
      );
      const actions = container.querySelector('[data-testid="po-actions"]');
      expect(actions.children.length).toBe(0);
    });

    test("header_annotation_only suppresses Edit + Delete but keeps Submit", () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'draft', edit_tier: 'header_annotation_only' })}
          projectId="p-1"
        />,
      );
      expect(screen.getByTestId('po-actions-submit-btn')).toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-edit-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-delete-btn')).not.toBeInTheDocument();
    });

    test("missing edit_tier falls back to read_only (no buttons)", () => {
      useAuth.mockReturnValue({ me: ME_PM });
      const { container } = renderWithProviders(
        <POActionButtons
          po={{ id: 'po-1', status: 'draft', submitted_by: 'x' /* no edit_tier */ }}
          projectId="p-1"
        />,
      );
      const actions = container.querySelector('[data-testid="po-actions"]');
      expect(actions.children.length).toBe(0);
    });

    test("edit_tier is case-insensitive (FULL == full)", () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'draft', edit_tier: 'FULL' })}
          projectId="p-1"
        />,
      );
      expect(screen.getByTestId('po-actions-edit-btn')).toBeInTheDocument();
    });
  });
});
