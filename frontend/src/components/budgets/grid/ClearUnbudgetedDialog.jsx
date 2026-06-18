/**
 * ClearUnbudgetedDialog — B107 §4.2.
 *
 * Director sign-off on an unbudgeted budget line. Body-less POST
 * (B107 §1.3 — the endpoint takes NO note). On success the budget-lines
 * query is invalidated (via useClearUnbudgeted) so the pill clears.
 */
import React, { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { formatMoney } from '@/lib/format';
import { useClearUnbudgeted } from '@/hooks/budgets';

export function ClearUnbudgetedDialog({
  open, onOpenChange, line, budgetId, codeLabel,
}) {
  const clear = useClearUnbudgeted(budgetId);
  const [err, setErr] = useState(null);

  const onConfirm = async () => {
    if (!line?.id) return;
    setErr(null);
    try {
      await clear.mutateAsync(line.id);
      // B112: notify PO raiser — now unblocked (see Build Pack B107 §9).
      toast.success('Unbudgeted line signed off');
      onOpenChange?.(false);
    } catch (e) {
      setErr(e?.friendlyMessage || e?.message || 'Failed to clear the line.');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="clear-unbudgeted-dialog">
        <DialogHeader>
          <DialogTitle>Sign off unbudgeted line</DialogTitle>
        </DialogHeader>
        <div className="space-y-2 text-sm text-slate-700">
          <p>
            You are signing off an unbudgeted line. This clears the director
            hold so purchase orders against it can be submitted.
          </p>
          <dl className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
            <div className="flex justify-between py-0.5">
              <dt className="text-slate-500">Cost code</dt>
              <dd className="font-mono" data-testid="clear-unbudgeted-code">
                {codeLabel ?? '—'}
              </dd>
            </div>
            <div className="flex justify-between py-0.5">
              <dt className="text-slate-500">Committed (not invoiced)</dt>
              <dd
                className="font-mono tabular-nums"
                data-testid="clear-unbudgeted-committed"
              >
                {formatMoney(line?.committed_not_invoiced)}
              </dd>
            </div>
          </dl>
          {err && (
            <p className="text-rose-600" data-testid="clear-unbudgeted-error">
              {err}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange?.(false)}
            data-testid="clear-unbudgeted-cancel"
          >
            Cancel
          </Button>
          <Button
            type="button"
            disabled={clear.isPending}
            onClick={onConfirm}
            data-testid="clear-unbudgeted-confirm"
          >
            {clear.isPending ? 'Signing off…' : 'Sign off'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ClearUnbudgetedDialog;
