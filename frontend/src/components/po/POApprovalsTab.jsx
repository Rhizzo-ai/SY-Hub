/**
 * <POApprovalsTab/> — R7 Batch 2 §R7.5 (per-project approvals dashboard).
 *
 * Tab inside the per-project PO list page. Lists POs in
 * `pending_approval` that the current user can action and links each
 * row to its PO detail page (where <POApprovalPanel/> from Batch 1
 * surfaces the over-budget snapshot + Approve/Reject controls).
 *
 * Data source: `useProjectPOs(projectId, { params: { status:
 * 'pending_approval' } })`. Per the build pack: if the backend
 * `/v1/projects/{id}/purchase-orders` endpoint does not yet honour
 * `status`, we fall back to a client-side filter on the returned
 * list. Per-project PO counts are small enough for that to be
 * acceptable.
 *
 * Read-only list + action affordance — no new mutation logic; reuses
 * Batch 1's <POApprovalPanel/> via the row link to PO detail.
 *
 * Persona perm gating: the list shows pending POs to any user with
 * `pos.view`. The per-row "Action" affordance only appears when the
 * user has `pos.approve` AND is NOT the submitter (the destination
 * panel re-asserts both, so this is just a UI affordance).
 *
 * All-projects global view is OUT OF SCOPE (build pack §CARRIED
 * FORWARD).
 */
import React from 'react';
import { Link, useParams } from 'react-router-dom';

import { useAuth } from '@/context/AuthContext';
import { useProjectPOs } from '@/hooks/purchaseOrders';
import {
  canApprovePO, canViewPOs, canViewSensitivePO,
} from '@/lib/poCapability';
import POStatusPill from '@/components/po/POStatusPill';
import SensitiveValue from '@/components/po/SensitiveValue';
import { fmtGBP } from '@/lib/poFormat';


export default function POApprovalsTab() {
  const { id: projectId } = useParams();
  const { user } = useAuth();
  const canSensitive = canViewSensitivePO(user);
  const canApprove   = canApprovePO(user);

  // Pass the status filter through. Backend already honours
  // `status_in` via the `/purchase-orders?project_id=X&status=...`
  // path, but `listProjectPOs` hits the project-scoped URL — if that
  // route ignores the param, we filter client-side below.
  const { data, isLoading, isError } = useProjectPOs(projectId, {
    params: { status: 'pending_approval' },
  });

  if (!canViewPOs(user)) {
    return (
      <div className="text-sm" data-testid="po-approvals-forbidden">
        You do not have permission to view purchase orders.
      </div>
    );
  }

  // Client-side fallback filter — if the backend ignores `status` on
  // the project-scoped path, the response will include non-pending
  // rows. Drop them here.
  const allRows = data?.items ?? [];
  const rows = allRows.filter((p) => p.status === 'pending_approval');

  return (
    <div className="space-y-3" data-testid="po-approvals-tab">
      <div className="text-sm text-sy-grey-700">
        POs awaiting approval on this project. Open a row to review the
        over-budget snapshot and Approve / Reject.
      </div>

      {isLoading && (
        <div className="text-sm" data-testid="po-approvals-loading">Loading…</div>
      )}
      {isError && (
        <div className="text-sm text-red-600" data-testid="po-approvals-error">
          Failed to load approvals.
        </div>
      )}

      {!isLoading && !isError && (
        <table className="w-full text-sm border-collapse" data-testid="po-approvals-table">
          <thead>
            <tr className="text-left text-xs text-sy-grey-700 border-b">
              <th className="py-2 pr-2 w-32">Number</th>
              <th className="py-2 pr-2">Supplier</th>
              <th className="py-2 pr-2 w-40">Status</th>
              <th className="py-2 pr-2 w-32 text-right">Gross</th>
              <th className="py-2 pr-2 w-24">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="py-3 text-sy-grey-500"
                  data-testid="po-approvals-empty"
                >
                  No POs awaiting approval on this project.
                </td>
              </tr>
            ) : (
              rows.map((po) => (
                <tr
                  key={po.id}
                  className="border-b last:border-0"
                  data-testid={`po-approvals-row-${po.id}`}
                >
                  <td className="py-2 pr-2">
                    <Link
                      to={`/projects/${projectId}/purchase-orders/${po.id}`}
                      className="text-sy-teal-700 underline tabular-nums"
                      data-testid={`po-approvals-row-${po.id}-link`}
                    >{po.po_number ?? '—'}</Link>
                  </td>
                  <td className="py-2 pr-2">{po.supplier_name ?? '—'}</td>
                  <td className="py-2 pr-2"><POStatusPill status={po.status} /></td>
                  <td className="py-2 pr-2 text-right tabular-nums">
                    <SensitiveValue
                      value={po.gross_total}
                      format={fmtGBP}
                      hidden={!canSensitive}
                    />
                  </td>
                  <td className="py-2 pr-2">
                    {canApprove ? (
                      <Link
                        to={`/projects/${projectId}/purchase-orders/${po.id}?tab=approvals`}
                        className="text-sy-teal-700 underline"
                        data-testid={`po-approvals-row-${po.id}-action`}
                      >Review</Link>
                    ) : (
                      <span
                        className="text-sy-grey-500"
                        data-testid={`po-approvals-row-${po.id}-readonly`}
                      >Read-only</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
