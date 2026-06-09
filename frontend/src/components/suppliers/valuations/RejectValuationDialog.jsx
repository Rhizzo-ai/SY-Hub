/**
 * <RejectValuationDialog/> — Chat 48 (Build Pack 2.8-FE-ii §R4.5).
 *
 * Capture a required `reason` and POST reject. The backend gates this
 * on `subcontract_valuations.certify` (shared with certify); only valid
 * from Submitted (409 otherwise). Empty reason → 422.
 *
 * Permission gating is the caller's job (<ValuationDetail/>); this
 * dialog only enforces the reason length. The Confirm button is
 * DISABLED while the textarea is blank or trimmed empty — the test
 * pins this.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { useRejectValuation } from '@/hooks/subcontractValuations';

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';


export default function RejectValuationDialog({
  open, onOpenChange, valuationId,
}) {
  const reject = useRejectValuation(valuationId);

  const [reason, setReason] = useState('');

  useEffect(() => {
    if (!open) return;
    setReason('');
  }, [open]);

  const canConfirm = useMemo(() => {
    const t = reason.trim();
    return t.length >= 1 && t.length <= 2000;
  }, [reason]);

  const onConfirm = async () => {
    if (!canConfirm) return;
    try {
      await reject.mutateAsync({ reason: reason.trim() });
      toast.success('Valuation rejected');
      onOpenChange(false);
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Reject failed';
      const text = typeof detail === 'string' ? detail : JSON.stringify(detail);
      if (status === 409) {
        toast.error(text);
      } else if (status === 422) {
        toast.error(text);
      } else if (status === 403) {
        toast.error('You don\u2019t have permission to do that.');
      } else if (status === 404) {
        toast.error('That valuation no longer exists.');
        onOpenChange(false);
      } else {
        toast.error(text);
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="valuation-reject-dialog">
        <DialogHeader>
          <DialogTitle>Reject this valuation</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-sm text-sy-grey-700">
            Rejection is a terminal status. The subcontractor will need
            to submit a new valuation to continue.
          </p>

          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Reason *</span>
            <Textarea
              rows={4}
              value={reason}
              maxLength={2000}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Explain why this valuation is being rejected"
              data-testid="valuation-reject-reason"
            />
            <span className="text-xs text-sy-grey-600 block mt-1">
              {reason.trim().length} / 2000
            </span>
          </label>
        </div>

        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="valuation-reject-cancel"
          >Cancel</Button>
          <Button
            type="button"
            disabled={!canConfirm || reject.isPending}
            onClick={onConfirm}
            className="bg-red-600 hover:bg-red-700 text-white"
            data-testid="valuation-reject-confirm"
          >Reject</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
