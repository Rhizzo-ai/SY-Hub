/**
 * <POActionButtons/> — Chat 26 §R7.2 (Batch 1).
 *
 * Single source of truth for PO lifecycle action buttons. Replaces the
 * inline action area previously living in <PurchaseOrderDetail/>.
 *
 * BATCH-1 SCOPE (workflow-only).
 *
 * Action matrix — `po.status × perm × self-approval`:
 *
 *   draft               → Submit
 *   pending_approval    → Approve, Reject              (self-approval guard)
 *   approved            → Issue, Send back             (send-back NOT guarded)
 *   issued              → Close
 *   partially_receipted → Close
 *   receipted           → Close
 *   closed / voided     → (none)
 *
 * Intentionally deferred to Batch 2 (do NOT render dead buttons):
 *
 *   - Edit / Delete (draft) — no /edit nor /delete routes exist in
 *     App.js; the Links would land on the App.js catch-all
 *     ('not-found-page'). Edit / Delete forms ship with Batch 2.
 *   - Edit (issued)         — same: no route.
 *   - + Receipt             — receipt form is R7.4 / Batch 2.
 *   - Void                  — backend requires non-empty `reason`
 *     (POVoidBody, min_length=1). A reason dialog needs the R7.6 /
 *     Batch 2 confirm-dialog system. Without it the click 422s.
 *
 * The capability helpers (`canEditPO`, `canDeletePO`, `canEditIssuedPO`,
 * `canReceiptPO`, `canVoidPO`) are imported but not currently used —
 * Batch 2 wires the buttons back in once their target routes / dialogs
 * exist. Leaving the imports here keeps the diff localised to a couple
 * of lines per button when those batches land.
 *
 * `edit_tier` (lowercase string from backend) gates EDITING ONLY.
 * Workflow transitions (Submit / Approve / Reject / Issue / Send back /
 * Close) are gated by status × perm, independent of edit_tier. With
 * Edit / Delete already removed from Batch 1, edit_tier currently has
 * no observable effect on the rendered set — kept as a placeholder so
 * Batch 2 only has to flip the deferred conditionals back on.
 *
 * Self-approval guard mirrors backend `SelfApprovalForbidden`: when
 * `po.submitted_by === me.id`, Approve + Reject hide. Send back is NOT
 * subject to this rule (correction path).
 *
 * Toast policy (Batch 1): plain mutate + Sonner success/error.
 * Optimistic + confirm-dialog polish is R7.6 / Batch 2.
 */
import React, { useState } from 'react';
import { toast } from 'sonner';

import { useAuth } from '@/context/AuthContext';
import { usePoTransition } from '@/hooks/purchaseOrders';
import {
  canApprovePO, canClosePO,
  canIssuePO, canRejectPO, canSubmitPO,
} from '@/lib/poCapability';
import { isSubmitter } from '@/lib/poSubmitter';

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

// Send-back is gated on `pos.edit OR pos.approve` (matches the backend
// guard on POST /purchase-orders/{id}/send-back, R7.0b). Inlined here
// since canEditPO/canApprovePO are the live imports above.
function canSendBackPO(me) {
  // Use canApprovePO as the primary gate — anyone who can approve can
  // send back. The OR-with-pos.edit fallback covers PMs who can author
  // POs but not approve; they're still allowed to recall an approved PO.
  // (Mirrors the backend's _require check in the send-back endpoint.)
  if (canApprovePO(me)) return true;
  return Array.isArray(me?.permissions) && me.permissions.includes('pos.edit');
}

const BTN_BASE = 'px-3 py-1.5 rounded text-sm';
const BTN_PRIMARY  = `${BTN_BASE} bg-sy-teal-600 text-white`;
const BTN_OUTLINE  = `${BTN_BASE} border`;
const BTN_DANGER   = `${BTN_BASE} border text-red-700`;


export default function POActionButtons({ po }) {
  const { me } = useAuth();
  const status = po?.status;
  const submitterMatches = isSubmitter(po, me);

  const submit   = usePoTransition(po.id, 'submit');
  const approve  = usePoTransition(po.id, 'approve');
  const reject   = usePoTransition(po.id, 'reject');
  const sendBack = usePoTransition(po.id, 'sendBack');
  const issueTxn = usePoTransition(po.id, 'issue');
  const closeTxn = usePoTransition(po.id, 'close');

  const [sendBackOpen, setSendBackOpen] = useState(false);
  const [sendBackNotes, setSendBackNotes] = useState('');
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const callTxn = async (m, body = {}, successMsg = 'Done') => {
    try {
      await m.mutateAsync(body);
      toast.success(successMsg);
    } catch (err) {
      toast.error(
        err?.response?.data?.detail?.message
        ?? err?.response?.data?.detail
        ?? err?.message
        ?? 'Action failed',
      );
    }
  };

  // Convenience flags per status (drives which buttons mount).
  const isDraft       = status === 'draft';
  const isPending     = status === 'pending_approval';
  const isApproved    = status === 'approved';
  const isIssued      = status === 'issued';
  const isPartial     = status === 'partially_receipted';
  const isReceipted   = status === 'receipted';

  const sendBackNotesTrimmed = sendBackNotes.trim();
  const rejectReasonTrimmed = rejectReason.trim();

  return (
    <>
      <div className="flex flex-wrap gap-2" data-testid="po-actions">
        {/* draft → Submit only. Edit / Delete deferred to Batch 2 (no
            /edit nor /delete routes exist yet). */}
        {isDraft && canSubmitPO(me) && (
          <button
            type="button"
            onClick={() => callTxn(submit, {}, 'Submitted')}
            disabled={submit.isPending}
            className={BTN_PRIMARY}
            data-testid="po-actions-submit-btn"
          >Submit</button>
        )}

        {/* pending_approval — Approve / Reject hide when current user is
            the submitter (mirrors backend SelfApprovalForbidden). */}
        {isPending && canApprovePO(me) && !submitterMatches && (
          <button
            type="button"
            onClick={() => callTxn(approve, {}, 'Approved')}
            disabled={approve.isPending}
            className={BTN_PRIMARY}
            data-testid="po-actions-approve-btn"
          >Approve</button>
        )}
        {isPending && canApprovePO(me) && submitterMatches && (
          <button
            type="button" disabled
            className={`${BTN_PRIMARY} opacity-40 cursor-not-allowed`}
            title="You submitted this PO — another approver must action it"
            data-testid="po-actions-approve-self-disabled"
          >Approve</button>
        )}
        {isPending && canRejectPO(me) && !submitterMatches && (
          <button
            type="button"
            onClick={() => { setRejectReason(''); setRejectOpen(true); }}
            className={BTN_DANGER}
            data-testid="po-actions-reject-btn"
          >Reject</button>
        )}

        {/* approved → Issue / Send back. Void deferred to Batch 2 (the
            backend requires a non-empty reason; the dialog system that
            collects it ships with R7.6). */}
        {isApproved && canIssuePO(me) && (
          <button
            type="button"
            onClick={() => callTxn(issueTxn, {}, 'Issued')}
            disabled={issueTxn.isPending}
            className={BTN_PRIMARY}
            data-testid="po-actions-issue-btn"
          >Issue</button>
        )}
        {isApproved && canSendBackPO(me) && (
          <button
            type="button"
            onClick={() => { setSendBackNotes(''); setSendBackOpen(true); }}
            className={BTN_OUTLINE}
            data-testid="po-actions-send-back-btn"
          >Send back</button>
        )}

        {/* issued → Close. Edit-issued + Receipt + Void deferred. */}
        {isIssued && canClosePO(me) && (
          <button
            type="button"
            onClick={() => callTxn(closeTxn, {}, 'Closed')}
            disabled={closeTxn.isPending}
            className={BTN_OUTLINE}
            data-testid="po-actions-close-issued-btn"
          >Close</button>
        )}

        {/* partially_receipted → Close. Receipt deferred. */}
        {isPartial && canClosePO(me) && (
          <button
            type="button"
            onClick={() => callTxn(closeTxn, {}, 'Closed')}
            disabled={closeTxn.isPending}
            className={BTN_OUTLINE}
            data-testid="po-actions-close-partial-btn"
          >Close</button>
        )}

        {/* receipted */}
        {isReceipted && canClosePO(me) && (
          <button
            type="button"
            onClick={() => callTxn(closeTxn, {}, 'Closed')}
            disabled={closeTxn.isPending}
            className={BTN_OUTLINE}
            data-testid="po-actions-close-btn"
          >Close</button>
        )}
      </div>

      {/* ── Send-back reason dialog (required notes) ─────────────── */}
      <Dialog open={sendBackOpen} onOpenChange={setSendBackOpen}>
        <DialogContent data-testid="po-send-back-dialog">
          <DialogHeader>
            <DialogTitle>Send PO back to draft</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-sy-grey-700">
            This unwinds the approval and returns the PO to <b>draft</b>.
            Notes are required and recorded in the audit log.
          </p>
          <Textarea
            value={sendBackNotes}
            onChange={(e) => setSendBackNotes(e.target.value)}
            rows={4}
            placeholder="Why is this PO being sent back?"
            data-testid="po-send-back-notes"
          />
          <DialogFooter>
            <Button
              type="button" variant="outline"
              onClick={() => setSendBackOpen(false)}
              data-testid="po-send-back-cancel"
            >Cancel</Button>
            <Button
              type="button"
              disabled={!sendBackNotesTrimmed || sendBack.isPending}
              onClick={async () => {
                await callTxn(
                  sendBack,
                  { notes: sendBackNotesTrimmed },
                  'PO sent back to draft',
                );
                setSendBackOpen(false);
              }}
              data-testid="po-send-back-confirm"
            >Send back</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Reject reason dialog (required reason) ────────────────── */}
      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent data-testid="po-reject-dialog">
          <DialogHeader>
            <DialogTitle>Reject PO</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-sy-grey-700">
            Rejection returns the PO to <b>draft</b>. Reason is required
            and is recorded on the approval row.
          </p>
          <Textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            rows={4}
            placeholder="Reason for rejection"
            data-testid="po-reject-reason"
          />
          <DialogFooter>
            <Button
              type="button" variant="outline"
              onClick={() => setRejectOpen(false)}
              data-testid="po-reject-cancel"
            >Cancel</Button>
            <Button
              type="button"
              disabled={!rejectReasonTrimmed || reject.isPending}
              onClick={async () => {
                await callTxn(
                  reject,
                  { reason: rejectReasonTrimmed },
                  'PO rejected',
                );
                setRejectOpen(false);
              }}
              data-testid="po-reject-confirm"
            >Reject</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
