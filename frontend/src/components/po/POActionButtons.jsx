/**
 * <POActionButtons/> — R7 Batch 2 (wires Edit / Delete / Receipt / Void).
 *
 * Single source of truth for PO lifecycle action buttons. R7 Batch 1
 * shipped the workflow-only set (Submit / Approve / Reject / Issue /
 * Send back / Close); Batch 2 now turns the remaining seven testids
 * (DEFERRED_TESTIDS) back on:
 *
 *   - po-actions-receipt-btn          (issued)            → §R7.4
 *   - po-actions-receipt-partial-btn  (partially_receipted) → §R7.4
 *   - po-actions-void-btn             (approved)          → §R7.6
 *   - po-actions-void-issued-btn      (issued / partial)  → §R7.6
 *   - po-actions-edit-btn             (draft, edit_tier='full')
 *   - po-actions-edit-issued-btn      (issued+, edit_tier='header_annotation_only')
 *   - po-actions-delete-btn           (draft only)
 *
 * Workflow gating remains status × perm × self-approval. Edit gating
 * is additionally driven by the backend's `edit_tier` enum (lowercase
 * strings: `full` | `header_annotation_only` | `read_only`), per
 * services/po_authz.py:EditPermission. Delete is draft-only because
 * the backend returns 422 on non-draft (DELETE contract).
 *
 * `edit_tier === 'full'` AND status==='draft' → edit-btn.
 * `edit_tier === 'header_annotation_only'`    → edit-issued-btn.
 * (Service maps `approved` to `full` too — that's still an edit-btn
 * surface; the issued/partial/receipted set is the only header-only
 * tier, so the testid split mirrors that.)
 *
 * Action matrix:
 *   draft               → Edit, Submit, Delete
 *   pending_approval    → Approve, Reject              (self-approval guard)
 *   approved            → Edit, Issue, Send back, Void
 *   issued              → Edit (annotation), Receipt, Close, Void
 *   partially_receipted → Edit (annotation), Receipt, Close
 *   receipted           → Edit (annotation), Close
 *   closed / voided     → (none)
 *
 * Self-approval guard mirrors backend `SelfApprovalForbidden`. Send
 * back is NOT subject to it (correction path).
 */
import React, { useState } from 'react';
import { toast } from 'sonner';

import { useAuth } from '@/context/AuthContext';
import { usePoTransition } from '@/hooks/purchaseOrders';
import {
  canApprovePO, canClosePO, canDeletePO, canEditPO, canEditIssuedPO,
  canIssuePO, canReceiptPO, canRejectPO, canSubmitPO, canVoidPO,
} from '@/lib/poCapability';
import { isSubmitter } from '@/lib/poSubmitter';

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

import POReceiptDialog from '@/components/po/POReceiptDialog';
import POVoidDialog    from '@/components/po/POVoidDialog';
import POEditDialog    from '@/components/po/POEditDialog';
import PODeleteDialog  from '@/components/po/PODeleteDialog';

// Send-back is gated on `pos.edit OR pos.approve` (matches the backend
// guard on POST /purchase-orders/{id}/send-back, R7.0b). Inlined here
// since canEditPO/canApprovePO are the live imports above.
function canSendBackPO(me) {
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

  // Batch 2 dialog open-state.
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [voidOpen, setVoidOpen]       = useState(false);
  const [editOpen, setEditOpen]       = useState(false);
  const [deleteOpen, setDeleteOpen]   = useState(false);

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

  // R7 Batch 2 — edit_tier gating. Lowercase enum from
  // services/po_authz.py:EditPermission.
  const editTier = po?.edit_tier ?? 'read_only';
  const isEditFull            = editTier === 'full';
  const isEditAnnotationOnly  = editTier === 'header_annotation_only';

  // Edit gate = internal user + project access + edit perm, then tier.
  // The first two are enforced server-side and reflected in `edit_tier`
  // (a user without project access never receives a non-read_only
  // tier — the GET 404s on the PO entirely). So the frontend gate is
  // tier × perm only.
  const showEditBtn       = isEditFull           && canEditPO(me);
  const showEditIssuedBtn = isEditAnnotationOnly && canEditIssuedPO(me);

  const sendBackNotesTrimmed = sendBackNotes.trim();
  const rejectReasonTrimmed = rejectReason.trim();

  return (
    <>
      <div className="flex flex-wrap gap-2" data-testid="po-actions">

        {/* ── Edit (header-only) — draft / approved → edit-btn ─── */}
        {showEditBtn && (
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            className={BTN_OUTLINE}
            data-testid="po-actions-edit-btn"
          >Edit</button>
        )}

        {/* ── Edit (annotation-only) — issued+ → edit-issued-btn ─ */}
        {showEditIssuedBtn && (
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            className={BTN_OUTLINE}
            data-testid="po-actions-edit-issued-btn"
          >Edit</button>
        )}

        {/* draft → Submit + Delete (Edit handled above). */}
        {isDraft && canSubmitPO(me) && (
          <button
            type="button"
            onClick={() => callTxn(submit, {}, 'Submitted')}
            disabled={submit.isPending}
            className={BTN_PRIMARY}
            data-testid="po-actions-submit-btn"
          >Submit</button>
        )}
        {isDraft && canDeletePO(me) && (
          <button
            type="button"
            onClick={() => setDeleteOpen(true)}
            className={BTN_DANGER}
            data-testid="po-actions-delete-btn"
          >Delete</button>
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

        {/* approved → Issue / Send back / Void. */}
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
            onClick={() => setVoidOpen(true)}
            className={BTN_DANGER}
            data-testid="po-actions-void-btn"
          >Void</button>
        )}

        {/* issued → Receipt + Close. (Void-issued rendered once below
            for the issued / partial set.) */}
        {isIssued && canReceiptPO(me) && (
          <button
            type="button"
            onClick={() => setReceiptOpen(true)}
            className={BTN_PRIMARY}
            data-testid="po-actions-receipt-btn"
          >+ Receipt</button>
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

        {/* partially_receipted → Receipt + Close. */}
        {isPartial && canReceiptPO(me) && (
          <button
            type="button"
            onClick={() => setReceiptOpen(true)}
            className={BTN_PRIMARY}
            data-testid="po-actions-receipt-partial-btn"
          >+ Receipt</button>
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

        {/* Void-issued — single render for issued OR partial (no double
            testid). Receipted POs are NOT voidable (the backend
            rejects with 409 / wrong-status); we mirror that here. */}
        {(isIssued || isPartial) && canVoidPO(me) && (
          <button
            type="button"
            onClick={() => setVoidOpen(true)}
            className={BTN_DANGER}
            data-testid="po-actions-void-issued-btn"
          >Void</button>
        )}

        {/* receipted → Close. */}
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

      {/* ── R7.4 Receipt dialog ──────────────────────────────────── */}
      <POReceiptDialog
        open={receiptOpen}
        onOpenChange={setReceiptOpen}
        po={po}
      />

      {/* ── R7.6 Void dialog (required reason) ───────────────────── */}
      <POVoidDialog
        open={voidOpen}
        onOpenChange={setVoidOpen}
        po={po}
      />

      {/* ── Edit / Delete dialogs ────────────────────────────────── */}
      <POEditDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        po={po}
      />
      <PODeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        po={po}
        projectId={po?.project_id}
      />
    </>
  );
}
