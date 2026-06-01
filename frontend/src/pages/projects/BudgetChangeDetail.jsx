/**
 * BudgetChangeDetail — Surface B (BCR workflow page).
 *
 * Routes: /budget-changes/:bcrId
 *
 * Renders the BCR header, line table, action bar (Surface B), and
 * (in Draft mode) the inline edit affordance. Workflow buttons live
 * in <BCRActionButtons/>. Reject + Withdraw modals are mounted inside
 * that component.
 *
 * Two-step Approve→Apply UI: when status === 'Approved', the action
 * bar shows the "awaiting apply" hint and the Apply button. This is
 * intentional — backend services/budget_changes.py:507 (approve) and
 * :580 (apply) are separate transitions; approve does NOT mutate
 * budget_lines, only apply does.
 */
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';

import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';

import { useAuth } from '@/context/AuthContext';
import { useBCR, usePatchBCR } from '@/hooks/budgetChanges';
import { useBudget } from '@/hooks/budgets';
import {
  canEditBCR, canViewBCR, isBCRCreator,
} from '@/lib/budgetChangeCapability';
import { fmtGBP } from '@/lib/poFormat';

import BCRStatusPill from '@/components/budgetChanges/BCRStatusPill';
import BCRLineEditor from '@/components/budgetChanges/BCRLineEditor';
import BCRActionButtons from '@/components/budgetChanges/BCRActionButtons';

function shortDateTime(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return s;
  }
}

export default function BudgetChangeDetail() {
  const { bcrId } = useParams();
  const { me } = useAuth();
  const canView = canViewBCR(me);

  const { data: bcr, isLoading, isError, error } = useBCR(bcrId, {
    enabled: canView,
  });
  const { data: budget } = useBudget(bcr?.budget_id, {
    enabled: !!bcr?.budget_id,
  });

  const [editOpen, setEditOpen] = useState(false);

  if (!canView) {
    return (
      <div
        data-testid="bcr-detail-no-perm"
        className="m-6 rounded-lg border border-slate-200 bg-slate-50 p-6 text-slate-600"
      >
        You don't have access to budget changes.
      </div>
    );
  }
  if (isLoading) {
    return (
      <div
        data-testid="bcr-detail-loading"
        className="m-6 rounded-lg border border-slate-200 p-12 text-center text-slate-500"
      >
        Loading budget change…
      </div>
    );
  }
  if (isError) {
    return (
      <div
        data-testid="bcr-detail-error"
        className="m-6 rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700"
      >
        {error?.friendlyMessage ?? error?.message ?? 'Failed to load BCR.'}
      </div>
    );
  }
  if (!bcr) return null;

  const budgetLines = budget?.lines ?? [];
  const linesById = Object.fromEntries(budgetLines.map((bl) => [bl.id, bl]));
  const creator = isBCRCreator(bcr, me);

  return (
    <div className="space-y-6 p-6" data-testid="bcr-detail">
      {/* Back link */}
      <Link
        to={bcr.budget_id ? `/projects/_/budgets/${bcr.budget_id}?tab=changes` : '/'}
        className="inline-flex items-center text-sm text-slate-600 hover:text-slate-900"
        data-testid="bcr-detail-back"
      >
        <ArrowLeft className="mr-1 h-4 w-4" />
        Back to budget changes
      </Link>

      {/* Header */}
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <span
                className="font-mono text-lg font-semibold text-slate-900"
                data-testid="bcr-detail-reference"
              >
                {bcr.reference}
              </span>
              <BCRStatusPill status={bcr.status} />
              <span className="text-sm text-slate-500">{bcr.change_type}</span>
            </div>
            <h1
              className="mt-2 text-xl font-bold text-slate-900"
              data-testid="bcr-detail-title"
            >
              {bcr.title}
            </h1>
            {bcr.reason ? (
              <p className="mt-2 text-sm text-slate-700">{bcr.reason}</p>
            ) : null}
          </div>
          <div className="text-right">
            <div className="text-xs text-slate-500">Net impact</div>
            <div
              className="font-mono tabular-nums text-2xl font-semibold"
              data-testid="bcr-detail-net-impact"
            >
              {fmtGBP(bcr.net_impact) ?? '£0.00'}
            </div>
          </div>
        </div>

        {/* Timeline */}
        <dl className="mt-4 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <div>
            <dt className="text-slate-500">Created</dt>
            <dd className="text-slate-800">{shortDateTime(bcr.created_at)}</dd>
          </div>
          {bcr.submitted_at ? (
            <div>
              <dt className="text-slate-500">Submitted</dt>
              <dd className="text-slate-800">{shortDateTime(bcr.submitted_at)}</dd>
            </div>
          ) : null}
          {bcr.approved_at ? (
            <div>
              <dt className="text-slate-500">Approved</dt>
              <dd className="text-slate-800">{shortDateTime(bcr.approved_at)}</dd>
            </div>
          ) : null}
          {bcr.applied_at ? (
            <div>
              <dt className="text-slate-500">Applied</dt>
              <dd className="text-slate-800">{shortDateTime(bcr.applied_at)}</dd>
            </div>
          ) : null}
          {bcr.rejected_at ? (
            <div>
              <dt className="text-slate-500">Rejected</dt>
              <dd className="text-slate-800">{shortDateTime(bcr.rejected_at)}</dd>
            </div>
          ) : null}
        </dl>

        {bcr.rejection_reason ? (
          <div
            className="mt-4 rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
            data-testid="bcr-detail-rejection-reason"
          >
            <b>Rejected:</b> {bcr.rejection_reason}
          </div>
        ) : null}
      </div>

      {/* Lines */}
      <div className="rounded-lg border border-slate-200">
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2">
          <h2 className="text-sm font-semibold text-slate-700">
            Budget-line deltas
          </h2>
          <span className="text-xs text-slate-500">
            {bcr.lines?.length ?? 0} line{bcr.lines?.length === 1 ? '' : 's'}
          </span>
        </div>
        <table className="w-full text-sm" data-testid="bcr-detail-lines">
          <thead className="bg-white text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2 text-left">Budget line</th>
              <th className="px-3 py-2 text-left">Cost code</th>
              <th className="px-3 py-2 text-right">Delta</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(bcr.lines ?? []).map((ln, i) => {
              const bl = linesById[ln.budget_line_id];
              return (
                <tr key={ln.id} data-testid={`bcr-detail-line-${i}`}>
                  <td className="px-3 py-2">
                    {bl
                      ? (bl.line_description || '(unlabelled)')
                      : <span className="text-slate-400">(line not in current budget snapshot)</span>}
                    {bl?.is_contingency ? (
                      <span className="ml-2 text-xs text-amber-700">(contingency)</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-600">
                    {bl?.cost_code ?? '—'}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono tabular-nums ${
                      Number(ln.delta) < 0 ? 'text-rose-700' : 'text-emerald-700'
                    }`}
                  >
                    {fmtGBP(ln.delta) ?? ln.delta}
                  </td>
                </tr>
              );
            })}
            {(bcr.lines ?? []).length === 0 ? (
              <tr>
                <td colSpan={3} className="px-3 py-6 text-center text-sm text-slate-500">
                  No lines on this BCR.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {/* Actions */}
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <BCRActionButtons
          bcr={bcr}
          onEdit={canEditBCR(me) && bcr.status === 'Draft' && creator
            ? () => setEditOpen(true)
            : null}
        />
      </div>

      {/* Edit dialog (Draft only) */}
      <EditBCRDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        bcr={bcr}
        budgetLines={budgetLines}
      />
    </div>
  );
}


// ─── Edit dialog ────────────────────────────────────────────────────
//
// PATCH /api/v1/budget-changes/{id} replaces title / reason / lines on
// a Draft BCR. Backend rejects PATCH on any non-Draft status with 409.
function EditBCRDialog({ open, onOpenChange, bcr, budgetLines }) {
  const [title, setTitle] = useState(bcr?.title ?? '');
  const [reason, setReason] = useState(bcr?.reason ?? '');
  const [lines, setLines] = useState(
    (bcr?.lines ?? []).map((ln) => ({
      budget_line_id: ln.budget_line_id,
      delta: ln.delta,
    })),
  );
  const patchMut = usePatchBCR(bcr?.id);

  // Re-hydrate when the bcr prop changes (e.g. on next open).
  useEffect(() => {
    if (!open) return;
    setTitle(bcr?.title ?? '');
    setReason(bcr?.reason ?? '');
    setLines((bcr?.lines ?? []).map((ln) => ({
      budget_line_id: ln.budget_line_id,
      delta: ln.delta,
    })));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, bcr?.id]);

  const submit = async () => {
    // Mirrors CreateBudgetChangeDialog: signed-decimal regex validation
    // (lib/schemas/actuals.js pattern).
    const DELTA_REGEX = /^-?\d+(\.\d{1,2})?$/;
    if (!title.trim()) {
      toast.error('Title is required.');
      return;
    }
    for (const ln of lines) {
      if (!ln.budget_line_id) {
        toast.error('Every line needs a budget-line selection.');
        return;
      }
      const raw = String(ln.delta ?? '').trim();
      if (!DELTA_REGEX.test(raw)) {
        toast.error('Every line needs a numeric delta (e.g. -40000 or 1500.50).');
        return;
      }
      if (Number(raw) === 0) {
        toast.error('Every line needs a non-zero delta.');
        return;
      }
    }
    try {
      await patchMut.mutateAsync({
        title: title.trim(),
        reason: reason.trim() || null,
        lines: lines.map((ln) => ({
          budget_line_id: ln.budget_line_id,
          delta: String(ln.delta).trim(),
        })),
      });
      toast.success('BCR updated');
      onOpenChange(false);
    } catch (err) {
      toast.error(
        err?.response?.data?.detail
        ?? err?.friendlyMessage
        ?? 'Update failed',
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="bcr-edit-dialog"
        className="max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        <DialogHeader>
          <DialogTitle>Edit budget change</DialogTitle>
          <DialogDescription>
            Edit the header and lines of this Draft BCR. Saving keeps
            the BCR in Draft — submit it for approval when you're ready.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label htmlFor="bcr-edit-title">Title</Label>
            <Input
              id="bcr-edit-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              data-testid="bcr-edit-title"
            />
          </div>
          <div>
            <Label htmlFor="bcr-edit-reason">Reason (optional)</Label>
            <Textarea
              id="bcr-edit-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              data-testid="bcr-edit-reason"
            />
          </div>
          <div>
            <Label>Lines</Label>
            <BCRLineEditor
              value={lines}
              onChange={setLines}
              changeType={bcr?.change_type}
              budgetLines={budgetLines}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="bcr-edit-cancel"
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={submit}
            disabled={patchMut.isPending}
            data-testid="bcr-edit-save"
          >
            {patchMut.isPending ? 'Saving…' : 'Save changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
