/**
 * <PODeleteDialog/> — R7 Batch 2 (Delete).
 *
 * Confirm-only dialog for deleting a draft PO. Backend returns 422 on
 * non-draft (`DELETE /purchase-orders/{id}`) — the button that opens
 * this dialog only mounts when `po.status === 'draft'`, mirroring that
 * contract.
 *
 * On success, navigates back to the project's PO list.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import { useDeletePO } from '@/hooks/purchaseOrders';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';


export default function PODeleteDialog({ open, onOpenChange, po, projectId }) {
  const navigate = useNavigate();
  const del = useDeletePO(po?.id);

  const onConfirm = async () => {
    try {
      await del.mutateAsync();
      toast.success('PO deleted');
      onOpenChange(false);
      if (projectId) {
        navigate(`/projects/${projectId}/purchase-orders`);
      }
    } catch (err) {
      toast.error(
        err?.response?.data?.detail?.message
        ?? err?.response?.data?.detail
        ?? err?.message ?? 'Delete failed',
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="po-delete-dialog">
        <DialogHeader>
          <DialogTitle>Delete draft PO</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-sy-grey-700">
          This deletes the draft purchase order {po?.po_number ? <b>{po.po_number}</b> : null}.
          Only draft POs can be deleted — issued and later statuses must
          be voided instead.
        </p>
        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="po-delete-cancel"
          >Cancel</Button>
          <Button
            type="button"
            disabled={del.isPending}
            onClick={onConfirm}
            className="bg-red-600 hover:bg-red-700 text-white"
            data-testid="po-delete-confirm"
          >Delete PO</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
