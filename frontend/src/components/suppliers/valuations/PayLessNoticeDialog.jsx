/**
 * <PayLessNoticeDialog/> — Chat 48 (Build Pack 2.8-FE-ii §R4.7).
 *
 * Issue a PayLess notice against a Certified valuation. The backend
 * gates this on `payment_notices.create` (route perm). PayLess is the
 * formal "we are withholding £X from this certified payment" notice;
 * the backend keeps it as a separate `notice_type='PayLess'` row so
 * the audit trail and certified amount remain intact.
 *
 * Body (verified PayLessNoticeBody):
 *   { subcontract_valuation_id (uuid, required),
 *     withhold_amount          (str Decimal, >= 0),
 *     reason                   (str, 1..2000),
 *     due_date                 (date | null) }
 *
 * Validation:
 *   - withhold_amount: digits + ≤2dp; non-negative. (Defence-in-depth
 *     against bad input; the server is authoritative.)
 *   - reason: required, 1..2000 chars.
 *   - Confirm disabled until both pass.
 *
 * 409 if the valuation isn't Certified (race / stale UI) — surfaced
 * verbatim; the hook's onSettled invalidates the notices list.
 * 422 surfaces server detail verbatim (negative amount, blank reason).
 */
import React, { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';

import { useCreatePayLess } from '@/hooks/paymentNotices';

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';


const MONEY_RE = /^\d+(\.\d{1,2})?$/;
function isValidMoney(s) {
  if (s == null) return false;
  const t = String(s).trim();
  if (t === '') return false;
  return MONEY_RE.test(t);
}


export default function PayLessNoticeDialog({
  open, onOpenChange, valuationId,
}) {
  const create = useCreatePayLess(valuationId);

  const [withhold, setWithhold] = useState('0');
  const [reason, setReason]     = useState('');
  const [dueDate, setDueDate]   = useState('');

  useEffect(() => {
    if (!open) return;
    setWithhold('0');
    setReason('');
    setDueDate('');
  }, [open]);

  const errors = useMemo(() => {
    const e = {};
    if (!isValidMoney(withhold)) e.withhold = 'Enter a non-negative amount (up to 2 decimal places).';
    const r = reason.trim();
    if (r.length < 1) e.reason = 'Reason is required.';
    if (r.length > 2000) e.reason = 'Reason must be 2000 characters or fewer.';
    return e;
  }, [withhold, reason]);

  const isValid = Object.keys(errors).length === 0;

  const onSubmit = async () => {
    if (!isValid) return;
    try {
      await create.mutateAsync({
        subcontract_valuation_id: valuationId,
        withhold_amount: withhold.trim(),
        reason: reason.trim(),
        due_date: dueDate || null,
      });
      toast.success('PayLess notice issued');
      onOpenChange(false);
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Failed to issue notice';
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
      <DialogContent className="max-w-lg" data-testid="payless-dialog">
        <DialogHeader>
          <DialogTitle>Issue a PayLess notice</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-sm text-sy-grey-700">
            A PayLess notice records that an amount will be withheld
            from the certified payment. The certified figures remain
            unchanged.
          </p>

          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Withhold amount (£) *</span>
            <input
              type="text"
              inputMode="decimal"
              className="w-full px-2 py-1 border rounded text-sm tabular-nums"
              value={withhold}
              onChange={(e) => setWithhold(e.target.value)}
              placeholder="0.00"
              data-testid="payless-withhold-amount"
            />
            {errors.withhold && (
              <span
                className="text-xs text-red-700"
                data-testid="payless-error-withhold"
              >{errors.withhold}</span>
            )}
          </label>

          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Reason *</span>
            <Textarea
              rows={3}
              value={reason}
              maxLength={2000}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason for withholding"
              data-testid="payless-reason"
            />
            {errors.reason && (
              <span
                className="text-xs text-red-700"
                data-testid="payless-error-reason"
              >{errors.reason}</span>
            )}
          </label>

          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Due date (optional)</span>
            <input
              type="date"
              className="w-full px-2 py-1 border rounded text-sm"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              data-testid="payless-due-date"
            />
          </label>
        </div>

        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="payless-cancel"
          >Cancel</Button>
          <Button
            type="button"
            disabled={!isValid || create.isPending}
            onClick={onSubmit}
            data-testid="payless-submit"
          >Issue notice</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
