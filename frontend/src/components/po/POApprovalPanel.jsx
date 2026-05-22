/**
 * <POApprovalPanel/> — Chat 26 §R7.3 (Batch 1).
 *
 * Renders inside the PO detail "approvals" tab:
 *   - Only while `po.status === 'pending_approval'` AND an open
 *     approval row exists (matches the preflight rule
 *     `po.approval && po.status==='pending_approval'`).
 *   - Renders the over-budget snapshot (per Chat-25 P0.10) from
 *     `approval.budget_snapshot` — an array of overrun lines with
 *     **decimal-string** values (do NOT parseFloat for arithmetic;
 *     reformat for layout only).
 *   - Provides Approve / Reject controls. Send-back is NOT here —
 *     it lives in <POActionButtons/> on the `approved` row (preflight
 *     confirmed the panel never sees `approved` status).
 *
 * Self-approval guard mirrors backend `SelfApprovalForbidden`: the
 * creator of the PO cannot Approve or Reject. Shared `isSubmitter`
 * helper is also used by <POActionButtons/>.
 *
 * Approval data source: the GET /purchase-orders/{po_id} endpoint
 * does NOT inline the open approval row, so this panel fetches
 * /purchase-orders/{po_id}/approvals via `usePOApprovals` and picks
 * the row with `resolution === null`. Historical (resolved) rows are
 * also rendered as a small log beneath the snapshot.
 */
import React, { useState } from 'react';
import { toast } from 'sonner';

import { useAuth } from '@/context/AuthContext';
import { usePoTransition, usePOApprovals } from '@/hooks/purchaseOrders';
import { canApprovePO, canRejectPO, canViewSensitivePO } from '@/lib/poCapability';
import { isSubmitter } from '@/lib/poSubmitter';
import SensitiveValue from '@/components/po/SensitiveValue';
import { fmtGBP } from '@/lib/poFormat';

import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';


function fmtSnapshotGBP(value, canSensitive) {
  if (!canSensitive) {
    return <SensitiveValue value={null} format={fmtGBP} hidden />;
  }
  // Decimal strings ship from the backend (Postgres NUMERIC) — Number()
  // ONLY for display rounding via fmtGBP; arithmetic stays string.
  if (value == null) return '—';
  return fmtGBP(Number(value));
}


function BudgetSnapshotTable({ snapshot, canSensitive }) {
  if (!Array.isArray(snapshot) || snapshot.length === 0) {
    return (
      <div className="text-xs text-sy-grey-500" data-testid="po-approval-snapshot-empty">
        No overrun lines on this PO.
      </div>
    );
  }
  return (
    <table
      className="w-full text-xs border-collapse mt-2"
      data-testid="po-approval-snapshot"
    >
      <thead>
        <tr className="text-left text-[11px] uppercase tracking-wider text-sy-grey-700 border-b">
          <th className="py-1 pr-2">Cost code</th>
          <th className="py-1 pr-2 text-right">Current budget</th>
          <th className="py-1 pr-2 text-right">Committed</th>
          <th className="py-1 pr-2 text-right">Actuals to date</th>
          <th className="py-1 pr-2 text-right">This PO (net)</th>
          <th className="py-1 pr-2 text-right">Projected total</th>
          <th className="py-1 pr-2 text-right">Over by</th>
        </tr>
      </thead>
      <tbody>
        {snapshot.map((row) => (
          <tr
            key={row.budget_line_id}
            className={`border-b last:border-0 ${row.is_overrun ? 'bg-red-50' : ''}`}
            data-testid={`po-approval-snapshot-row-${row.budget_line_id}`}
          >
            <td className="py-1 pr-2 font-mono">{row.cost_code ?? '—'}</td>
            <td className="py-1 pr-2 text-right tabular-nums">
              {fmtSnapshotGBP(row.current_budget, canSensitive)}
            </td>
            <td className="py-1 pr-2 text-right tabular-nums">
              {fmtSnapshotGBP(row.committed_value, canSensitive)}
            </td>
            <td className="py-1 pr-2 text-right tabular-nums">
              {fmtSnapshotGBP(row.actuals_to_date, canSensitive)}
            </td>
            <td className="py-1 pr-2 text-right tabular-nums">
              {fmtSnapshotGBP(row.this_po_net, canSensitive)}
            </td>
            <td className="py-1 pr-2 text-right tabular-nums">
              {fmtSnapshotGBP(row.projected_total, canSensitive)}
            </td>
            <td className={`py-1 pr-2 text-right tabular-nums ${row.is_overrun ? 'text-red-700 font-semibold' : ''}`}>
              {fmtSnapshotGBP(row.over_by, canSensitive)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}


export default function POApprovalPanel({ po }) {
  const { me } = useAuth();
  const canSensitive = canViewSensitivePO(me);
  const isPending = po?.status === 'pending_approval';

  // Only fetch /approvals when we're on a pending PO. Other statuses
  // either never had an approval row (auto-approved within budget) or
  // already have a resolved row (history-only).
  const { data: approvalsResp, isLoading } = usePOApprovals(
    po?.id, { enabled: !!po?.id && isPending },
  );

  const approvals = approvalsResp?.items ?? [];
  const openRow = approvals.find((a) => a.resolution == null) ?? null;
  const history = approvals.filter((a) => a.resolution != null);

  const approve = usePoTransition(po.id, 'approve');
  const reject = usePoTransition(po.id, 'reject');

  const [approveOpen, setApproveOpen] = useState(false);
  const [approveReason, setApproveReason] = useState('');
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const submitterMatches = isSubmitter(po, me);
  const canApprove = canApprovePO(me) && !submitterMatches;
  const canReject = canRejectPO(me) && !submitterMatches;

  const runApprove = async () => {
    try {
      const body = approveReason.trim() ? { reason: approveReason.trim() } : {};
      await approve.mutateAsync(body);
      toast.success('Approved');
      setApproveOpen(false);
    } catch (err) {
      toast.error(
        err?.response?.data?.detail?.message
        ?? err?.response?.data?.detail
        ?? err?.message ?? 'Approve failed',
      );
    }
  };

  const runReject = async () => {
    try {
      await reject.mutateAsync({ reason: rejectReason.trim() });
      toast.success('Rejected');
      setRejectOpen(false);
    } catch (err) {
      toast.error(
        err?.response?.data?.detail?.message
        ?? err?.response?.data?.detail
        ?? err?.message ?? 'Reject failed',
      );
    }
  };

  // Panel is conditional. When not pending, OR when pending but no open
  // row was returned, render just the resolved history (if any). Build
  // pack rule: render the panel iff approval && status==='pending_approval'.
  if (!isPending) {
    return <HistoryOnly approvals={po?.approvals ?? []} />;
  }

  if (isLoading) {
    return (
      <div className="text-sm text-sy-grey-500" data-testid="po-approval-panel-loading">
        Loading approval…
      </div>
    );
  }

  if (!openRow) {
    return <HistoryOnly approvals={history} />;
  }

  return (
    <div className="space-y-4" data-testid="po-approval-panel">
      <div className="rounded border border-sy-orange-200 bg-sy-orange-50 p-3">
        <div className="text-sm font-semibold text-sy-orange-800">
          Pending approval
        </div>
        <div className="text-xs text-sy-grey-700 mt-0.5">
          Submitted{' '}
          <span className="tabular-nums">
            {openRow.submitted_at?.slice(0, 16).replace('T', ' ')}
          </span>
          {openRow.submission_reason && (
            <> · <span className="italic">{openRow.submission_reason}</span></>
          )}
        </div>
        <BudgetSnapshotTable
          snapshot={openRow.budget_snapshot}
          canSensitive={canSensitive}
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {canApprove && (
          <Button
            type="button"
            className="bg-sy-teal-600 hover:bg-sy-teal-700 text-white"
            onClick={() => { setApproveReason(''); setApproveOpen(true); }}
            data-testid="po-approval-approve-btn"
          >Approve</Button>
        )}
        {canApprovePO(me) && submitterMatches && (
          <Button
            type="button" disabled
            className="bg-sy-teal-600 text-white opacity-40 cursor-not-allowed"
            title="You submitted this PO — another approver must action it"
            data-testid="po-approval-approve-self-disabled"
          >Approve</Button>
        )}
        {canReject && (
          <Button
            type="button" variant="outline"
            className="text-red-700 border-red-200 hover:bg-red-50"
            onClick={() => { setRejectReason(''); setRejectOpen(true); }}
            data-testid="po-approval-reject-btn"
          >Reject</Button>
        )}
      </div>

      <HistoryOnly approvals={history} />

      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent data-testid="po-approval-approve-dialog">
          <DialogHeader>
            <DialogTitle>Approve PO</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-sy-grey-700">
            Approving will move this PO to <b>approved</b>. A note is
            optional.
          </p>
          <Textarea
            value={approveReason}
            onChange={(e) => setApproveReason(e.target.value)}
            rows={3}
            placeholder="Note (optional)"
            data-testid="po-approval-approve-reason"
          />
          <DialogFooter>
            <Button
              type="button" variant="outline"
              onClick={() => setApproveOpen(false)}
              data-testid="po-approval-approve-cancel"
            >Cancel</Button>
            <Button
              type="button"
              disabled={approve.isPending}
              onClick={runApprove}
              data-testid="po-approval-approve-confirm"
            >Approve</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent data-testid="po-approval-reject-dialog">
          <DialogHeader>
            <DialogTitle>Reject PO</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-sy-grey-700">
            Rejection returns the PO to <b>draft</b>. Reason is required.
          </p>
          <Textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            rows={3}
            placeholder="Reason for rejection"
            data-testid="po-approval-reject-reason"
          />
          <DialogFooter>
            <Button
              type="button" variant="outline"
              onClick={() => setRejectOpen(false)}
              data-testid="po-approval-reject-cancel"
            >Cancel</Button>
            <Button
              type="button"
              disabled={!rejectReason.trim() || reject.isPending}
              onClick={runReject}
              data-testid="po-approval-reject-confirm"
            >Reject</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


function HistoryOnly({ approvals }) {
  if (!approvals || approvals.length === 0) {
    return (
      <div className="text-sm text-sy-grey-600" data-testid="po-approval-history-empty">
        No approval history.
      </div>
    );
  }
  return (
    <div data-testid="po-approval-history">
      <div className="text-xs font-semibold uppercase tracking-wider text-sy-grey-700 mb-1">
        History
      </div>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left text-xs text-sy-grey-700 border-b">
            <th className="py-1 pr-2">When</th>
            <th className="py-1 pr-2">By</th>
            <th className="py-1 pr-2">Resolution</th>
            <th className="py-1 pr-2">Notes</th>
          </tr>
        </thead>
        <tbody>
          {approvals.map((a) => (
            <tr key={a.id ?? a.approval_id} className="border-b last:border-0">
              <td className="py-1 pr-2 tabular-nums">
                {(a.resolved_at ?? a.submitted_at)?.slice(0, 10)}
              </td>
              <td className="py-1 pr-2">
                {a.resolved_by?.slice?.(0, 8) ?? a.submitted_by?.slice?.(0, 8) ?? '—'}
              </td>
              <td className="py-1 pr-2">{a.resolution ?? 'pending'}</td>
              <td className="py-1 pr-2">{a.resolution_notes ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
