/**
 * <BCRActionButtons/> — Surface B actions.
 *
 * Single source of truth for BCR lifecycle action buttons. Mirrors
 * components/po/POActionButtons.jsx pattern.
 *
 * Action matrix:
 *   Draft       → Edit, Submit, Withdraw                    (creator-only on Withdraw)
 *   Submitted   → Approve, Reject, Withdraw                 (self-approval guard on Approve)
 *   Approved    → Apply                                     (two-step — approve does NOT auto-apply)
 *   Applied / Rejected / Withdrawn → (none — terminal)
 *
 * Self-approval guard mirrors backend `BudgetSelfApprovalError`
 * (LD2 — services/budget_changes.py:520-532). Visually hides Approve
 * for the creator and shows a disabled twin with a tooltip — same
 * pattern as PO approvals.
 *
 * The two-step Approve→Apply is intentional. After Approve, the BCR
 * sits in `Approved` state with `approved_at` stamped but the parent
 * budget_lines unchanged. The Apply step does the FRESH-read +
 * all-or-nothing write so two BCRs racing to apply see each other's
 * effect.
 */
import { useState } from 'react';
import { toast } from 'sonner';

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

import { useAuth } from '@/context/AuthContext';
import { useBCRTransition } from '@/hooks/budgetChanges';
import { useBudgetSelfApprovalThreshold } from '@/hooks/systemConfig';
import {
  canApproveBCR, canApplyBCR, canRejectBCR, canSubmitBCR,
  canWithdrawBCR, isBCRCreator,
} from '@/lib/budgetChangeCapability';

import BCRRejectDialog from '@/components/budgetChanges/BCRRejectDialog';

const BTN_BASE = 'px-3 py-1.5 rounded text-sm';
const BTN_PRIMARY = `${BTN_BASE} bg-sy-teal-600 text-white hover:bg-sy-teal-700`;
const BTN_OUTLINE = `${BTN_BASE} border border-slate-300 hover:bg-slate-50`;
const BTN_DANGER  = `${BTN_BASE} border border-rose-300 text-rose-700 hover:bg-rose-50`;
const BTN_SUCCESS = `${BTN_BASE} bg-emerald-600 text-white hover:bg-emerald-700`;

export default function BCRActionButtons({ bcr, onEdit }) {
  const { me } = useAuth();
  const status = bcr?.status;
  const submit = useBCRTransition(bcr?.id, 'submit');
  const approve = useBCRTransition(bcr?.id, 'approve');
  const withdraw = useBCRTransition(bcr?.id, 'withdraw');
  const apply = useBCRTransition(bcr?.id, 'apply');

  const [rejectOpen, setRejectOpen] = useState(false);
  const [withdrawConfirmOpen, setWithdrawConfirmOpen] = useState(false);

  const creator = isBCRCreator(bcr, me);
  const isDraft = status === 'Draft';
  const isSubmitted = status === 'Submitted';
  const isApproved = status === 'Approved';

  // LD2 self-approval guard — mirror backend
  // services/budget_changes.py:520-532. Threshold is gross movement
  // (sum of abs(delta) across all BCR lines) compared with the per-
  // tenant `budget.self_approval_threshold_gbp` value (default £10k).
  // Backend is the authority — a 403 BudgetSelfApprovalError is the
  // safety net if the client-side threshold is stale.
  const { threshold } = useBudgetSelfApprovalThreshold();
  const gross = (bcr?.lines ?? []).reduce(
    (sum, ln) => sum + Math.abs(Number(ln.delta) || 0),
    0,
  );
  const selfApprovalBlocked = creator && gross >= threshold;

  const callTxn = async (m, successMsg) => {
    try {
      await m.mutateAsync();
      toast.success(successMsg);
    } catch (err) {
      toast.error(
        err?.response?.data?.detail
        ?? err?.friendlyMessage
        ?? 'Action failed',
      );
    }
  };

  return (
    <>
      <div
        className="flex flex-wrap gap-2"
        data-testid="bcr-actions"
      >
        {/* ── Draft ────────────────────────────────────────────── */}
        {isDraft && onEdit ? (
          <button
            type="button"
            onClick={onEdit}
            className={BTN_OUTLINE}
            data-testid="bcr-actions-edit-btn"
          >
            Edit
          </button>
        ) : null}
        {isDraft && canSubmitBCR(me) ? (
          <button
            type="button"
            onClick={() => callTxn(submit, 'BCR submitted for approval')}
            disabled={submit.isPending}
            className={BTN_PRIMARY}
            data-testid="bcr-actions-submit-btn"
          >
            {submit.isPending ? 'Submitting…' : 'Submit for approval'}
          </button>
        ) : null}

        {/* ── Submitted ─ Approve / Reject ───────────────────── */}
        {/* Self-approval guard mirrors backend gross-movement check
            (sum(abs(delta)) >= threshold). Only hides Approve at-or-
            above the threshold — sub-threshold gross is permitted by
            backend so the UI must allow it too. */}
        {isSubmitted && canApproveBCR(me) && !selfApprovalBlocked ? (
          <button
            type="button"
            onClick={() => callTxn(approve, 'BCR approved — Apply next to push to budget')}
            disabled={approve.isPending}
            className={BTN_PRIMARY}
            data-testid="bcr-actions-approve-btn"
          >
            {approve.isPending ? 'Approving…' : 'Approve'}
          </button>
        ) : null}
        {isSubmitted && canApproveBCR(me) && selfApprovalBlocked ? (
          <button
            type="button"
            disabled
            className={`${BTN_PRIMARY} opacity-40 cursor-not-allowed`}
            title={`You created this BCR — gross movement £${gross.toLocaleString('en-GB')} is at/above the £${threshold.toLocaleString('en-GB')} self-approval threshold (LD2). Another approver must action it.`}
            data-testid="bcr-actions-approve-self-disabled"
          >
            Approve
          </button>
        ) : null}
        {isSubmitted && canRejectBCR(me) && !selfApprovalBlocked ? (
          <button
            type="button"
            onClick={() => setRejectOpen(true)}
            className={BTN_DANGER}
            data-testid="bcr-actions-reject-btn"
          >
            Reject
          </button>
        ) : null}

        {/* ── Approved ─ Apply (separate, intentional two-step) ─ */}
        {isApproved && canApplyBCR(me) ? (
          <button
            type="button"
            onClick={() => callTxn(apply, 'BCR applied to budget')}
            disabled={apply.isPending}
            className={BTN_SUCCESS}
            data-testid="bcr-actions-apply-btn"
          >
            {apply.isPending ? 'Applying…' : 'Apply to budget'}
          </button>
        ) : null}

        {/* ── Withdraw — creator only, Draft or Submitted ──────── */}
        {(isDraft || isSubmitted) && canWithdrawBCR(me) && creator ? (
          <button
            type="button"
            onClick={() => setWithdrawConfirmOpen(true)}
            className={BTN_OUTLINE}
            data-testid="bcr-actions-withdraw-btn"
          >
            Withdraw
          </button>
        ) : null}
      </div>

      {/* "Awaiting apply" hint when Approved — makes the two-step
          explicit. */}
      {isApproved ? (
        <div
          className="mt-3 rounded border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900"
          data-testid="bcr-awaiting-apply-hint"
        >
          <b>Approved — awaiting apply.</b> The parent budget has NOT yet
          been updated. Click <b>Apply to budget</b> to push the deltas
          and recompute totals. A separate apply step is intentional so
          concurrent BCRs always see the most recent budget state.
        </div>
      ) : null}

      {/* Reject dialog */}
      <BCRRejectDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        bcr={bcr}
      />

      {/* Withdraw confirm */}
      <Dialog
        open={withdrawConfirmOpen}
        onOpenChange={setWithdrawConfirmOpen}
      >
        <DialogContent data-testid="bcr-withdraw-dialog">
          <DialogHeader>
            <DialogTitle>Withdraw budget change?</DialogTitle>
            <DialogDescription>
              This moves the BCR to <b>Withdrawn</b> (terminal). If you
              need to change scope later, raise a new BCR.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setWithdrawConfirmOpen(false)}
              data-testid="bcr-withdraw-cancel"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={async () => {
                setWithdrawConfirmOpen(false);
                await callTxn(withdraw, 'BCR withdrawn');
              }}
              disabled={withdraw.isPending}
              data-testid="bcr-withdraw-confirm"
            >
              Withdraw
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
