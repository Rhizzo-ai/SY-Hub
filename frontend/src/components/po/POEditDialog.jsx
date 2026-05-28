/**
 * <POEditDialog/> — R7 Batch 2 (Edit — Option A, header-only).
 *
 * Header-only edit form for an existing PO. Posts via
 * `PATCH /v1/purchase-orders/{id}` (POPatch — header fields only).
 *
 * Two tiers, mapped to the backend `edit_tier` returned on the PO:
 *
 *   - edit_tier === 'full' (draft / approved, `pos.edit` required)
 *       — all header fields editable.
 *
 *   - edit_tier === 'header_annotation_only'
 *       (issued / partially_receipted / receipted, `pos.edit_issued`)
 *       — only `notes`, `delivery_notes`, `external_reference` editable.
 *
 * `edit_tier === 'read_only'` (closed / voided / pending_approval)
 * does not mount this dialog; the open buttons in <POActionButtons/>
 * gate that.
 *
 * The dialog binds to whatever edit_tier the backend returns — no
 * frontend invents the enum (build pack §EDIT NOTE).
 */
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { usePatchPO } from '@/hooks/purchaseOrders';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';


// Mirrors backend HEADER_ANNOTATION_FIELDS.
const ANNOTATION_FIELDS = ['notes', 'delivery_notes', 'external_reference'];


export default function POEditDialog({ open, onOpenChange, po }) {
  const patch = usePatchPO(po?.id);
  const tier = po?.edit_tier ?? 'read_only';
  const isFull = tier === 'full';

  const [issueDate, setIssueDate]           = useState('');
  const [requiredByDate, setRequiredByDate] = useState('');
  const [deliveryAddress, setDeliveryAddress] = useState('');
  const [deliveryNotes, setDeliveryNotes]   = useState('');
  const [externalRef, setExternalRef]       = useState('');
  const [notes, setNotes]                   = useState('');

  useEffect(() => {
    if (!open) return;
    setIssueDate(po?.issue_date?.slice(0, 10) ?? '');
    setRequiredByDate(po?.required_by_date?.slice(0, 10) ?? '');
    setDeliveryAddress(po?.delivery_address ?? '');
    setDeliveryNotes(po?.delivery_notes ?? '');
    setExternalRef(po?.external_reference ?? '');
    setNotes(po?.notes ?? '');
  }, [open, po]);

  const onSubmit = async () => {
    const body = {};
    // Always allow annotation fields (both tiers).
    if (deliveryNotes !== (po?.delivery_notes ?? '')) {
      body.delivery_notes = deliveryNotes || null;
    }
    if (externalRef !== (po?.external_reference ?? '')) {
      body.external_reference = externalRef || null;
    }
    if (notes !== (po?.notes ?? '')) {
      body.notes = notes || null;
    }
    if (isFull) {
      if (issueDate !== (po?.issue_date?.slice(0, 10) ?? '')) {
        body.issue_date = issueDate || null;
      }
      if (requiredByDate !== (po?.required_by_date?.slice(0, 10) ?? '')) {
        body.required_by_date = requiredByDate || null;
      }
      if (deliveryAddress !== (po?.delivery_address ?? '')) {
        body.delivery_address = deliveryAddress || null;
      }
    }
    if (Object.keys(body).length === 0) {
      toast.info?.('Nothing to save');
      onOpenChange(false);
      return;
    }
    try {
      await patch.mutateAsync(body);
      toast.success('PO updated');
      onOpenChange(false);
    } catch (err) {
      toast.error(
        err?.response?.data?.detail?.message
        ?? err?.response?.data?.detail
        ?? err?.message ?? 'Update failed',
      );
    }
  };

  // R7-polish §R3 — defense-in-depth short-circuit. <POActionButtons/>
  // already gates the Edit button on `edit_tier !== 'read_only'`, so
  // in normal flow this branch is unreachable. We still render an
  // inert marker (no form, no inputs, no mutations) if a caller forces
  // `open` while the backend reports the PO as read-only — keeps the
  // contract symmetric with `read_only` PATCH 403 responses from the
  // backend and protects against future regressions where the parent
  // forgets the gate. The early-return sits AFTER all hooks (rules of
  // hooks). See PurchaseOrderList.jsx:47-51 for the same shape.
  if (open && tier === 'read_only') {
    return (
      <div
        data-testid="po-edit-readonly-shortcircuit"
        style={{ display: 'none' }}
        aria-hidden="true"
      />
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="po-edit-dialog">
        <DialogHeader>
          <DialogTitle>
            Edit PO {po?.po_number ? `· ${po.po_number}` : ''}
          </DialogTitle>
        </DialogHeader>
        <p
          className="text-xs text-sy-grey-700"
          data-testid="po-edit-tier-banner"
        >
          {isFull
            ? 'Full header edit (draft / approved).'
            : `Annotation-only edit (status: ${po?.status}). Editable fields: ${ANNOTATION_FIELDS.join(', ')}.`}
        </p>

        {isFull && (
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Issue date</span>
              <input
                type="date"
                className="w-full px-2 py-1 border rounded text-sm"
                value={issueDate}
                onChange={(e) => setIssueDate(e.target.value)}
                data-testid="po-edit-issue-date"
              />
            </label>
            <label className="block text-sm">
              <span className="text-xs text-sy-grey-700">Required-by date</span>
              <input
                type="date"
                className="w-full px-2 py-1 border rounded text-sm"
                value={requiredByDate}
                onChange={(e) => setRequiredByDate(e.target.value)}
                data-testid="po-edit-required-by-date"
              />
            </label>
            <label className="block text-sm col-span-2">
              <span className="text-xs text-sy-grey-700">Delivery address</span>
              <Textarea
                value={deliveryAddress}
                onChange={(e) => setDeliveryAddress(e.target.value)}
                rows={2}
                data-testid="po-edit-delivery-address"
              />
            </label>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3">
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">External reference</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm"
              value={externalRef}
              onChange={(e) => setExternalRef(e.target.value)}
              maxLength={100}
              data-testid="po-edit-external-reference"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Delivery notes</span>
            <Textarea
              value={deliveryNotes}
              onChange={(e) => setDeliveryNotes(e.target.value)}
              rows={2}
              data-testid="po-edit-delivery-notes"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Notes</span>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              data-testid="po-edit-notes"
            />
          </label>
        </div>

        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="po-edit-cancel"
          >Cancel</Button>
          <Button
            type="button"
            disabled={patch.isPending}
            onClick={onSubmit}
            data-testid="po-edit-confirm"
          >Save changes</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
