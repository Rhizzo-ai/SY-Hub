/**
 * BulkPayDialog (Chat 19B §R5.3).
 *
 * D30 N-call loop: POST /actuals/:id/mark-paid sequentially with shared
 * paid_date + per-row payment_reference. Per-row pass/fail pills.
 *
 * Snapshot pattern: the `actuals` prop shrinks as the parent removes
 * succeeded rows from its selection. We freeze the row list at open-time
 * so the operator can still read the result pills after `onComplete` runs.
 */
import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { fmtGBP } from '@/lib/format';
import * as actualsApi from '@/lib/api/actuals';
import { useQueryClient } from '@tanstack/react-query';
import { actualsKeys } from '@/hooks/actuals';

export function BulkPayDialog({ open, onOpenChange, actuals, onComplete }) {
  const qc = useQueryClient();
  const [paidDate, setPaidDate] = useState(new Date().toISOString().slice(0, 10));
  const [refs, setRefs] = useState({});       // {actualId: ref}
  const [status, setStatus] = useState({});   // {actualId: 'pending'|'success'|'error'}
  const [errors, setErrors] = useState({});   // {actualId: errorMsg}
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);

  // Snapshot the actuals list at open-time. After `run()` succeeds, the
  // parent's onComplete callback shrinks `selected` which shrinks the
  // `actuals` prop passed in — without this snapshot the dialog would
  // reset its per-row status pills the moment the user is reading them.
  const [snapshot, setSnapshot] = useState([]);
  useEffect(() => {
    if (!open) return;
    setSnapshot(actuals);
    const defaultDateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const nextRefs = {};
    for (const a of actuals) {
      nextRefs[a.id] = `BACS-${defaultDateStr}-${a.id.slice(0, 6)}`;
    }
    setRefs(nextRefs);
    setStatus({});
    setErrors({});
    setDone(false);
    setRunning(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const rows = snapshot;
  const totalCount = rows.length;
  const completedCount = Object.values(status).filter(
    (s) => s === 'success' || s === 'error',
  ).length;
  const successCount = Object.values(status).filter((s) => s === 'success').length;
  const progressPct = totalCount === 0 ? 0 : Math.round((completedCount / totalCount) * 100);

  const allRefsValid = rows.every((a) => (refs[a.id] || '').trim().length > 0);
  const canRun = !running && !done && !!paidDate && allRefsValid && totalCount > 0;

  const run = async () => {
    setRunning(true);
    setStatus(Object.fromEntries(rows.map((a) => [a.id, 'pending'])));
    const succeededIds = [];
    const failedIds = [];
    for (const a of rows) {
      try {
        // eslint-disable-next-line no-await-in-loop
        await actualsApi.markPaid(a.id, {
          paid_date: paidDate,
          payment_reference: refs[a.id],
        });
        setStatus((s) => ({ ...s, [a.id]: 'success' }));
        succeededIds.push(a.id);
      } catch (err) {
        const detail = err?.response?.data?.detail;
        const msg = typeof detail === 'string'
          ? detail
          : detail?.message ?? err?.message ?? 'unknown';
        setStatus((s) => ({ ...s, [a.id]: 'error' }));
        setErrors((e) => ({ ...e, [a.id]: msg }));
        failedIds.push(a.id);
      }
    }
    setRunning(false);
    setDone(true);
    // Invalidate ALL actuals-related caches so the list, detail, project
    // lists, and Louise's view all refetch.
    qc.invalidateQueries({ queryKey: actualsKeys.all });
    qc.invalidateQueries({ queryKey: ['budgets'] });
    if (succeededIds.length > 0) onComplete(succeededIds);
    if (failedIds.length === 0) {
      toast.success(
        `Marked ${succeededIds.length} bill${succeededIds.length === 1 ? '' : 's'} as Paid`,
      );
    } else {
      toast.error(
        `${succeededIds.length} succeeded · ${failedIds.length} failed. See dialog for details.`,
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !running && onOpenChange(o)}>
      <DialogContent className="max-w-2xl" data-testid="bulk-pay-dialog">
        <DialogHeader>
          <DialogTitle>
            Mark {totalCount} bill{totalCount === 1 ? '' : 's'} as Paid
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <Label>Payment date (applies to all)</Label>
            <Input
              type="date"
              value={paidDate}
              onChange={(e) => setPaidDate(e.target.value)}
              disabled={running || done}
              data-testid="bulk-pay-date"
            />
          </div>

          <div className="max-h-64 overflow-y-auto rounded-md border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="p-2 text-left">Supplier</th>
                  <th className="p-2 text-right">Gross</th>
                  <th className="p-2 text-left">Payment ref</th>
                  <th className="p-2 text-left">Result</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id} data-testid={`bulk-pay-row-${a.id}`}>
                    <td className="p-2 truncate">{a.supplier_name_snapshot}</td>
                    <td className="p-2 text-right tabular">{fmtGBP(a.gross_amount)}</td>
                    <td className="p-2">
                      <Input
                        value={refs[a.id] ?? ''}
                        onChange={(e) =>
                          setRefs((r) => ({ ...r, [a.id]: e.target.value }))
                        }
                        disabled={running || done}
                        data-testid={`bulk-pay-ref-${a.id}`}
                      />
                    </td>
                    <td className="p-2">
                      {status[a.id] === 'pending' && (
                        <span className="text-xs text-slate-500">…</span>
                      )}
                      {status[a.id] === 'success' && (
                        <span
                          className="text-xs font-medium text-emerald-700"
                          data-testid={`bulk-pay-success-${a.id}`}
                        >
                          Paid
                        </span>
                      )}
                      {status[a.id] === 'error' && (
                        <span
                          className="text-xs font-medium text-rose-700"
                          title={errors[a.id]}
                          data-testid={`bulk-pay-error-${a.id}`}
                        >
                          Failed
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {(running || done) && (
            <div data-testid="bulk-pay-progress">
              <Progress value={progressPct} />
              <p className="mt-1 text-xs text-slate-600">
                {completedCount} / {totalCount} complete
                {done && ` · ${successCount} succeeded · ${totalCount - successCount} failed`}
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          {!done ? (
            <>
              <Button
                variant="ghost"
                onClick={() => onOpenChange(false)}
                disabled={running}
                data-testid="bulk-pay-cancel"
              >
                Cancel
              </Button>
              <Button
                disabled={!canRun}
                onClick={run}
                className="bg-sy-teal text-white hover:brightness-110"
                data-testid="bulk-pay-run"
              >
                {running ? `Paying ${completedCount}/${totalCount}…` : `Pay ${totalCount}`}
              </Button>
            </>
          ) : (
            <Button
              onClick={() => onOpenChange(false)}
              className="bg-sy-teal text-white hover:brightness-110"
              data-testid="bulk-pay-close"
            >
              Close
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
