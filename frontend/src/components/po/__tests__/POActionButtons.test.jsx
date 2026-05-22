/**
 * <POActionButtons/> tests — Chat 26 §R7.2 (Batch 1).
 *
 * Slim Batch-1 action set per the corrected build pack scope. Edit /
 * Delete / Edit (issued) / + Receipt / Void are intentionally deferred
 * to Batch 2 (no target routes, or no reason-dialog system) — assert
 * here that they render on NO status × persona combination, so a
 * regression that quietly re-mounts a dead button breaks CI.
 *
 *   draft               → Submit
 *   pending_approval    → Approve, Reject              (self-approval guard)
 *   approved            → Issue, Send back             (send-back NOT guarded)
 *   issued              → Close
 *   partially_receipted → Close
 *   receipted           → Close
 *   closed / voided     → (none)
 *
 * Personas mirror the seeded RBAC roles:
 *   - FULL PM     — pos.create + pos.edit + pos.delete + pos.submit
 *                   + pos.receipt + pos.close + pos.void
 *                   (NB: no pos.approve)
 *   - APPROVER    — pos.approve (+ pos.issue, pos.void, pos.edit)
 *   - READ-ONLY   — pos.view only
 *   - SUBMITTER   — APPROVER perms + IS the PO's submitted_by
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
const ME_APPROVER = { id: 'user-app', permissions: ['pos.view', 'pos.approve', 'pos.issue', 'pos.void', 'pos.edit', 'pos.close'] };
const ME_READONLY = { id: 'user-ro', permissions: ['pos.view'] };

// Buttons explicitly deferred to Batch 2. Asserting all five render
// on NO status × persona combination is the regression guard.
const DEFERRED_TESTIDS = [
  'po-actions-edit-btn',
  'po-actions-delete-btn',
  'po-actions-edit-issued-btn',
  'po-actions-receipt-btn',
  'po-actions-receipt-partial-btn',
  'po-actions-void-btn',
  'po-actions-void-issued-btn',
];

function makePO({ status, submitted_by = 'user-someone', edit_tier = 'full', id = 'po-1' } = {}) {
  return { id, status, submitted_by, edit_tier };
}

function setMockTransition({ mutateAsync = jest.fn().mockResolvedValue({}), isPending = false } = {}) {
  usePoTransition.mockReturnValue({ mutateAsync, isPending });
}


describe('<POActionButtons/> R7.2 — slim Batch-1 action matrix', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setMockTransition();
  });

  // ── draft ──────────────────────────────────────────────────────────
  describe('draft', () => {
    test('FULL PM sees Submit only (Edit / Delete deferred to Batch 2)', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(<POActionButtons po={makePO({ status: 'draft' })} />);
      expect(screen.getByTestId('po-actions-submit-btn')).toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-edit-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-delete-btn')).not.toBeInTheDocument();
    });

    test('READ-ONLY persona sees no buttons', () => {
      useAuth.mockReturnValue({ me: ME_READONLY });
      renderWithProviders(<POActionButtons po={makePO({ status: 'draft' })} />);
      expect(screen.queryByTestId('po-actions-submit-btn')).not.toBeInTheDocument();
    });
  });

  // ── pending_approval ───────────────────────────────────────────────
  describe('pending_approval', () => {
    test('APPROVER (non-submitter) sees Approve + Reject', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'pending_approval', submitted_by: 'someone-else' })}
        />,
      );
      expect(screen.getByTestId('po-actions-approve-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-reject-btn')).toBeInTheDocument();
    });

    test('SELF-APPROVAL: submitter sees disabled Approve twin, Reject hidden', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'pending_approval', submitted_by: 'user-app' })}
        />,
      );
      expect(screen.queryByTestId('po-actions-approve-btn')).not.toBeInTheDocument();
      expect(screen.getByTestId('po-actions-approve-self-disabled')).toBeDisabled();
      expect(screen.queryByTestId('po-actions-reject-btn')).not.toBeInTheDocument();
    });

    test('FULL PM (no pos.approve) sees neither Approve nor Reject', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'pending_approval' })} />,
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
            edit_tier: 'read_only', // ← live backend value for this status
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
    test('APPROVER sees Issue + Send back (Void deferred to Batch 2)', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'approved', submitted_by: 'someone-else' })}
        />,
      );
      expect(screen.getByTestId('po-actions-issue-btn')).toBeInTheDocument();
      expect(screen.getByTestId('po-actions-send-back-btn')).toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-void-btn')).not.toBeInTheDocument();
    });

    test('SUBMITTER can still send back their own approved PO (no self-guard on send-back)', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons
          po={makePO({ status: 'approved', submitted_by: 'user-app' })}
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
          po={makePO({ status: 'approved', submitted_by: 'someone-else' })}
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
        <POActionButtons po={makePO({ status: 'approved' })} />,
      );
      expect(screen.queryByTestId('po-actions-issue-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-send-back-btn')).not.toBeInTheDocument();
    });
  });

  // ── issued / partially_receipted / receipted ──────────────────────
  describe('issued', () => {
    test('APPROVER sees Close only (Receipt / Edit-issued / Void deferred)', () => {
      useAuth.mockReturnValue({ me: ME_APPROVER });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'issued' })} />,
      );
      expect(screen.getByTestId('po-actions-close-issued-btn')).toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-receipt-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-edit-issued-btn')).not.toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-void-issued-btn')).not.toBeInTheDocument();
    });
  });

  describe('partially_receipted', () => {
    test('FULL PM sees Close only (Receipt deferred)', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'partially_receipted' })} />,
      );
      expect(screen.getByTestId('po-actions-close-partial-btn')).toBeInTheDocument();
      expect(screen.queryByTestId('po-actions-receipt-partial-btn')).not.toBeInTheDocument();
    });
  });

  describe('receipted', () => {
    test('FULL PM sees Close', () => {
      useAuth.mockReturnValue({ me: ME_PM });
      renderWithProviders(
        <POActionButtons po={makePO({ status: 'receipted' })} />,
      );
      expect(screen.getByTestId('po-actions-close-btn')).toBeInTheDocument();
    });
  });

  // ── terminal states ───────────────────────────────────────────────
  describe('terminal states (closed, voided)', () => {
    test.each(['closed', 'voided'])('%s renders no action buttons', (status) => {
      useAuth.mockReturnValue({ me: ME_PM });
      const { container } = renderWithProviders(
        <POActionButtons po={makePO({ status })} />,
      );
      const actions = container.querySelector('[data-testid="po-actions"]');
      expect(actions.children.length).toBe(0);
    });
  });

  // ── deferred-button regression guard ──────────────────────────────
  //
  // The fastest way for a Batch-2 PR to silently leak a dead button is
  // to wire it back into <POActionButtons/> before its route / dialog
  // ships. This iterates every reachable state × every persona we
  // model and asserts none of the deferred testids ever render. If
  // Batch 2 brings these back, the assertion in the relevant per-status
  // test above should be flipped at the same time.
  describe('deferred-to-Batch-2 buttons must render on NO state × persona', () => {
    const STATES = [
      'draft', 'pending_approval', 'approved', 'issued',
      'partially_receipted', 'receipted', 'closed', 'voided',
    ];
    const PERSONAS = [
      ['FULL PM',     ME_PM],
      ['APPROVER',    ME_APPROVER],
      ['READ-ONLY',   ME_READONLY],
      ['SUBMITTER',   { ...ME_APPROVER, id: 'user-app' }],
    ];
    for (const [pname, me] of PERSONAS) {
      for (const status of STATES) {
        test(`${pname} × ${status} — none of the deferred buttons render`, () => {
          useAuth.mockReturnValue({ me });
          renderWithProviders(
            <POActionButtons po={makePO({ status, submitted_by: me.id ?? 'x' })} />,
          );
          for (const tid of DEFERRED_TESTIDS) {
            expect(screen.queryByTestId(tid)).not.toBeInTheDocument();
          }
        });
      }
    }
  });
});
