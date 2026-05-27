/**
 * <POVoidDialog/> — R7 Batch 2 §R7.6.
 *
 * Required-reason confirm dialog for voiding a PO. Mirrors the
 * reject-dialog shape (po-reject-dialog) exactly per the build pack:
 * confirm `disabled` until a trimmed reason is entered.
 *
 * Posts via `usePoTransition(poId, 'void')`, which now applies an
 * optimistic `status: 'voided'` patch on `onMutate` (rollback on
 * error), and coarse-invalidates `['budgets']` on settle (AC5 — void
 * releases commitment).
 */
import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { usePoTransition } from '@/hooks/purchaseOrders';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';


export default function POVoidDialog({ open, onOpenChange, po }) {
  const voidTxn = usePoTransition(po?.id, 'void');
  const [reason, setReason] = useState('');

  useEffect(() => {
    if (open) setReason('');
  }, [open]);

  const reasonTrimmed = reason.trim();

  const onConfirm = async () => {
    try {
      await voidTxn.mutateAsync({ reason: reasonTrimmed });
      toast.success('PO voided');
      onOpenChange(false);
    } catch (err) {
      toast.error(
        err?.response?.data?.detail?.message
        ?? err?.response?.data?.detail
        ?? err?.message ?? 'Void failed',
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="po-void-dialog">
        <DialogHeader>
          <DialogTitle>Void purchase order</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-sy-grey-700">
          Voiding releases the committed amount on the budget. A reason
          is required and is recorded in the audit log.
        </p>
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={4}
          placeholder="Reason for voiding"
          data-testid="po-void-reason"
        />
        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="po-void-cancel"
          >Cancel</Button>
          <Button
            type="button"
            disabled={!reasonTrimmed || voidTxn.isPending}
            onClick={onConfirm}
            className="bg-red-600 hover:bg-red-700 text-white"
            data-testid="po-void-confirm"
          >Void PO</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
