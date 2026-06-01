/**
 * <BCRRejectDialog/> — Surface D.
 *
 * Required-reason modal for POST /budget-changes/{id}/reject. Mirrors
 * the POReject shape (see POActionButtons.jsx:340-378). Reason is
 * required at the backend (Field(..., min_length=1)).
 */
import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { useBCRTransition } from '@/hooks/budgetChanges';

export default function BCRRejectDialog({ open, onOpenChange, bcr }) {
  const [reason, setReason] = useState('');
  const reject = useBCRTransition(bcr?.id, 'reject');
  const trimmed = reason.trim();

  const close = () => {
    setReason('');
    onOpenChange(false);
  };

  const submit = async () => {
    try {
      await reject.mutateAsync({ reason: trimmed });
      toast.success('BCR rejected');
      close();
    } catch (err) {
      toast.error(
        err?.response?.data?.detail
        ?? err?.friendlyMessage
        ?? 'Rejection failed',
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="bcr-reject-dialog">
        <DialogHeader>
          <DialogTitle>Reject budget change</DialogTitle>
          <DialogDescription>
            Rejection is final — the BCR moves to <b>Rejected</b> and cannot
            be re-opened. Raise a new BCR if a correction is needed. Reason
            is required and is recorded on the audit log.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={4}
          placeholder="Reason for rejection"
          data-testid="bcr-reject-reason"
        />
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={close}
            data-testid="bcr-reject-cancel"
          >
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!trimmed || reject.isPending}
            onClick={submit}
            data-testid="bcr-reject-confirm"
            className="bg-rose-600 hover:bg-rose-700 text-white"
          >
            Reject
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
