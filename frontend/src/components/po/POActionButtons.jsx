/**
 * <POActionButtons/> — Chat 26 §R7.2 (Batch 1).
 *
 * Single source of truth for PO lifecycle action buttons. Replaces the
 * inline action area previously living in <PurchaseOrderDetail/>.
 *
 * Action matrix — `po.status × perm × edit_tier × self-approval`:
 *
 *   draft               → Submit, Edit, Delete
 *   pending_approval    → Approve, Reject              (self-approval guard)
 *   approved            → Issue, Send back, Void       (send-back NOT guarded)
 *   issued              → + Receipt, Void, Close
 *   partially_receipted → Receipt, Close
 *   receipted           → Close
 *   closed / voided     → (none)
 *
 * `edit_tier` (lowercase string from backend) gates EDITING ONLY —
 * Edit / Delete buttons. Workflow transitions (Submit / Approve /
 * Reject / Issue / Send back / Void / Close / Receipt) are gated by
 * status × perm, independent of edit_tier. The backend explicitly
 * tags pending_approval as edit_tier='read_only' to lock header/line
 * fields while the approver decides — but Approve/Reject must still
 * be reachable.
 *
 *   - 'full'                   → Edit + Delete + Edit (issued) allowed
 *   - 'header_annotation_only' → suppress Edit / Delete (workflow OK)
 *   - 'read_only'              → suppress Edit / Delete (workflow OK)
 *   - absent / unknown         → treat as 'read_only' (defensive)
 *
 * Self-approval guard mirrors backend `SelfApprovalForbidden`: when
 * `po.submitted_by === me.id`, Approve + Reject hide. Send back is NOT
 * subject to this rule (correction path).
 *
 * Toast policy (Batch 1): plain mutate + Sonner success/error.
 * Optimistic + confirm-dialog polish is R7.6 / Batch 2.
 */
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';

import { useAuth } from '@/context/AuthContext';
import { usePoTransition } from '@/hooks/purchaseOrders';
import {
  canApprovePO, canClosePO, canDeletePO, canEditPO, canEditIssuedPO,
  canIssuePO, canRejectPO, canReceiptPO, canSubmitPO, canVoidPO,
} from '@/lib/poCapability';
import { isSubmitter } from '@/lib/poSubmitter';

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

// Send-back is gated on `pos.edit OR pos.approve` (matches the backend
// guard on POST /purchase-orders/{id}/send-back, R7.0b).
function canSendBackPO(me) {
  return canEditPO(me) || canApprovePO(me);
}

function normaliseEditTier(raw) {
  if (typeof raw !== 'string' || !raw) return 'read_only';
  return raw.toLowerCase();
}

const BTN_BASE = 'px-3 py-1.5 rounded text-sm';
const BTN_PRIMARY  = `${BTN_BASE} bg-sy-teal-600 text-white`;
const BTN_OUTLINE  = `${BTN_BASE} border`;
const BTN_ORANGE   = `${BTN_BASE} bg-sy-orange-600 text-white`;
const BTN_DANGER   = `${BTN_BASE} border text-red-700`;


export default function POActionButtons({ po, projectId }) {
  const { me } = useAuth();
  const tier = normaliseEditTier(po?.edit_tier);
  const status = po?.status;
  const submitterMatches = isSubmitter(po, me);

  const submit   = usePoTransition(po.id, 'submit');
  const approve  = usePoTransition(po.id, 'approve');
  const reject   = usePoTransition(po.id, 'reject');
  const sendBack = usePoTransition(po.id, 'sendBack');
  const issueTxn = usePoTransition(po.id, 'issue');
  const voidTxn  = usePoTransition(po.id, 'void');
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

  // ── edit_tier short-circuit: blocks Edit / Delete buttons only.
  // Workflow transitions (Submit / Approve / Reject / Issue / Send
  // back / Void / Close / Receipt) are gated by status × perm and
  // remain reachable regardless of edit_tier. The backend tags
  // `pending_approval` as edit_tier='read_only' to lock header/line
  // edits while the approver decides — Approve/Reject must still
  // render. Only `'full'` unlocks Edit/Delete.
  const editAllowed = tier === 'full';

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
        {/* draft */}
        {isDraft && editAllowed && canEditPO(me) && (
          <Link
            to={`/projects/${projectId}/purchase-orders/${po.id}/edit`}
            className={BTN_OUTLINE}
            data-testid="po-actions-edit-btn"
          >Edit</Link>
        )}
        {isDraft && canSubmitPO(me) && (
          <button
            type="button"
            onClick={() => callTxn(submit, {}, 'Submitted')}
            disabled={submit.isPending}
            className={BTN_PRIMARY}
            data-testid="po-actions-submit-btn"
          >Submit</button>
        )}
        {isDraft && editAllowed && canDeletePO(me) && (
          <Link
            to={`/projects/${projectId}/purchase-orders/${po.id}/delete`}
            className={BTN_DANGER}
            data-testid="po-actions-delete-btn"
          >Delete</Link>
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

        {/* approved → Issue / Send back / Void */}
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
        {isApproved && canVoidPO(me) && (
          <button
            type="button"
            onClick={() => callTxn(voidTxn, {}, 'Voided')}
            disabled={voidTxn.isPending}
            className={BTN_DANGER}
            data-testid="po-actions-void-btn"
          >Void</button>
        )}

        {/* issued */}
        {isIssued && editAllowed && canEditIssuedPO(me) && (
          <Link
            to={`/projects/${projectId}/purchase-orders/${po.id}/edit`}
            className={BTN_OUTLINE}
            data-testid="po-actions-edit-issued-btn"
          >Edit (issued)</Link>
        )}
        {isIssued && canReceiptPO(me) && (
          <Link
            to={`/projects/${projectId}/purchase-orders/${po.id}/receipts/new`}
            className={BTN_ORANGE}
            data-testid="po-actions-receipt-btn"
          >+ Receipt</Link>
        )}
        {isIssued && canVoidPO(me) && (
          <button
            type="button"
            onClick={() => callTxn(voidTxn, {}, 'Voided')}
            disabled={voidTxn.isPending}
            className={BTN_DANGER}
            data-testid="po-actions-void-issued-btn"
          >Void</button>
        )}
        {isIssued && canClosePO(me) && (
          <button
            type="button"
            onClick={() => callTxn(closeTxn, {}, 'Closed')}
            disabled={closeTxn.isPending}
            className={BTN_OUTLINE}
            data-testid="po-actions-close-issued-btn"
          >Close</button>
        )}

        {/* partially_receipted */}
        {isPartial && canReceiptPO(me) && (
          <Link
            to={`/projects/${projectId}/purchase-orders/${po.id}/receipts/new`}
            className={BTN_ORANGE}
            data-testid="po-actions-receipt-partial-btn"
          >+ Receipt</Link>
        )}
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
