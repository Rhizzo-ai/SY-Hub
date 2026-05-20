/**
 * PurchaseOrderDetail — Chat 24 §R5.
 *
 * Tabs: Lines / Receipts / Approvals / Audit. Lifecycle action buttons
 * are gated by both the PO status (nextActionsForStatus) and the user
 * permissions (poCapability).
 *
 * Sensitive numerics fall back to <SensitiveValue/> when the caller
 * lacks pos.view_sensitive.
 */
import React, { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '@/context/AuthContext';
import {
  usePO, useReceipts, usePoTransition,
} from '@/hooks/purchaseOrders';
import {
  canApprovePO, canClosePO, canEditIssuedPO, canEditPO, canIssuePO,
  canRejectPO, canReceiptPO, canSubmitPO, canViewSensitivePO, canVoidPO,
  nextActionsForStatus,
} from '@/lib/poCapability';
import POStatusPill from '@/components/po/POStatusPill';
import SensitiveValue from '@/components/po/SensitiveValue';
import { fmtGBP, fmtNumber } from '@/lib/poFormat';

const TABS = ['lines', 'receipts', 'approvals', 'audit'];


export default function PurchaseOrderDetail() {
  const { id: projectId, po_id: poId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canSensitive = canViewSensitivePO(user);
  const [tab, setTab] = useState('lines');

  const { data: po, isLoading, isError } = usePO(poId);
  const { data: receipts } = useReceipts(poId, { enabled: tab === 'receipts' });

  const submit = usePoTransition(poId, 'submit');
  const approve = usePoTransition(poId, 'approve');
  const reject = usePoTransition(poId, 'reject');
  const issueTxn = usePoTransition(poId, 'issue');
  const voidTxn = usePoTransition(poId, 'void');
  const closeTxn = usePoTransition(poId, 'close');

  if (isLoading) return <div className="p-6 text-sm" data-testid="po-detail-loading">Loading…</div>;
  if (isError || !po) return <div className="p-6 text-sm text-red-600" data-testid="po-detail-error">
    Purchase order not found.
  </div>;

  const actions = nextActionsForStatus(po.status);
  const callTxn = async (m) => {
    try { await m.mutateAsync({}); }
    catch (err) {
      window.alert(err?.response?.data?.detail?.message ?? err?.response?.data?.detail ?? err.message);
    }
  };

  return (
    <div className="p-6 space-y-4" data-testid="po-detail">
      <header className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold tabular-nums" data-testid="po-detail-number">
            {po.po_number ?? '—'}
          </h1>
          <div className="text-xs text-sy-grey-600">
            {po.supplier_name ?? '—'} · <POStatusPill status={po.status} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {actions.includes('edit') && canEditPO(user) && (
            <Link
              to={`/projects/${projectId}/purchase-orders/${po.id}/edit`}
              className="px-3 py-1.5 rounded border text-sm"
              data-testid="po-detail-edit-btn"
            >Edit</Link>
          )}
          {actions.includes('edit_issued') && canEditIssuedPO(user) && (
            <Link
              to={`/projects/${projectId}/purchase-orders/${po.id}/edit`}
              className="px-3 py-1.5 rounded border text-sm"
              data-testid="po-detail-edit-issued-btn"
            >Edit (issued)</Link>
          )}
          {actions.includes('submit') && canSubmitPO(user) && (
            <button
              type="button" onClick={() => callTxn(submit)} disabled={submit.isPending}
              className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm"
              data-testid="po-detail-submit-btn"
            >Submit</button>
          )}
          {actions.includes('approve') && canApprovePO(user) && (
            <button
              type="button" onClick={() => callTxn(approve)} disabled={approve.isPending}
              className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm"
              data-testid="po-detail-approve-btn"
            >Approve</button>
          )}
          {actions.includes('reject') && canRejectPO(user) && (
            <button
              type="button"
              onClick={async () => {
                const reason = window.prompt('Rejection reason?');
                if (!reason) return;
                try { await reject.mutateAsync({ reason }); }
                catch (err) { window.alert(err?.response?.data?.detail?.message ?? err.message); }
              }}
              className="px-3 py-1.5 rounded border text-red-700 text-sm"
              data-testid="po-detail-reject-btn"
            >Reject</button>
          )}
          {actions.includes('receipt') && canReceiptPO(user) && (
            <Link
              to={`/projects/${projectId}/purchase-orders/${po.id}/receipts/new`}
              className="px-3 py-1.5 rounded bg-sy-orange-600 text-white text-sm"
              data-testid="po-detail-receipt-btn"
            >+ Receipt</Link>
          )}
          {actions.includes('void') && canVoidPO(user) && (
            <button
              type="button" onClick={() => callTxn(voidTxn)} disabled={voidTxn.isPending}
              className="px-3 py-1.5 rounded border text-red-700 text-sm"
              data-testid="po-detail-void-btn"
            >Void</button>
          )}
          {actions.includes('close') && canClosePO(user) && (
            <button
              type="button" onClick={() => callTxn(closeTxn)} disabled={closeTxn.isPending}
              className="px-3 py-1.5 rounded border text-sm"
              data-testid="po-detail-close-btn"
            >Close</button>
          )}
        </div>
      </header>

      <section className="grid grid-cols-4 gap-2 text-sm">
        <div data-testid="po-detail-net">
          <div className="text-xs text-sy-grey-700">Net</div>
          <SensitiveValue value={po.net_total} format={fmtGBP} hidden={!canSensitive} />
        </div>
        <div data-testid="po-detail-vat">
          <div className="text-xs text-sy-grey-700">VAT</div>
          <SensitiveValue value={po.vat_total} format={fmtGBP} hidden={!canSensitive} />
        </div>
        <div data-testid="po-detail-gross">
          <div className="text-xs text-sy-grey-700">Gross</div>
          <SensitiveValue value={po.gross_total} format={fmtGBP} hidden={!canSensitive} />
        </div>
        <div data-testid="po-detail-issued-at">
          <div className="text-xs text-sy-grey-700">Issued</div>
          <span className="tabular-nums">{po.issued_at?.slice(0, 10) ?? '—'}</span>
        </div>
      </section>

      <nav className="flex gap-2 border-b" data-testid="po-detail-tabs">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-sm ${tab === t ? 'border-b-2 border-sy-teal-600 font-semibold' : 'text-sy-grey-700'}`}
            data-testid={`po-detail-tab-${t}`}
          >{t}</button>
        ))}
      </nav>

      {tab === 'lines' && (
        <table className="w-full text-sm border-collapse" data-testid="po-detail-lines">
          <thead>
            <tr className="text-left text-xs text-sy-grey-700 border-b">
              <th className="py-1 pr-2">#</th>
              <th className="py-1 pr-2">Description</th>
              <th className="py-1 pr-2 w-20 text-right">Qty</th>
              <th className="py-1 pr-2 w-24 text-right">Rate</th>
              <th className="py-1 pr-2 w-16 text-right">VAT</th>
              <th className="py-1 pr-2 w-28 text-right">Net</th>
              <th className="py-1 pr-2 w-24 text-right">Receipted</th>
            </tr>
          </thead>
          <tbody>
            {(po.lines ?? []).map((l) => (
              <tr key={l.id} className="border-b last:border-0" data-testid={`po-line-row-${l.id}`}>
                <td className="py-1 pr-2 tabular-nums">{l.line_number}</td>
                <td className="py-1 pr-2">{l.description ?? '—'}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{fmtNumber(l.quantity, 4)}</td>
                <td className="py-1 pr-2 text-right">
                  <SensitiveValue value={l.unit_rate} format={fmtGBP} hidden={!canSensitive} />
                </td>
                <td className="py-1 pr-2 text-right tabular-nums">
                  {l.vat_rate != null ? `${l.vat_rate}%` : '—'}
                </td>
                <td className="py-1 pr-2 text-right">
                  <SensitiveValue value={l.line_net_value} format={fmtGBP} hidden={!canSensitive} />
                </td>
                <td className="py-1 pr-2 text-right tabular-nums">
                  {fmtNumber(l.receipted_quantity, 4) ?? '—'}
                  {l.is_fully_receipted && <span className="ml-1 text-sy-teal-700">✓</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === 'receipts' && (
        <div data-testid="po-detail-receipts">
          {(receipts?.items ?? []).length === 0 ? (
            <div className="text-sm text-sy-grey-500" data-testid="po-detail-receipts-empty">
              No receipts yet.
            </div>
          ) : (
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-xs text-sy-grey-700 border-b">
                  <th className="py-1 pr-2">Received</th>
                  <th className="py-1 pr-2">Delivery note</th>
                  <th className="py-1 pr-2 w-20 text-right">Lines</th>
                  <th className="py-1 pr-2 w-20 text-right">Photos</th>
                </tr>
              </thead>
              <tbody>
                {(receipts?.items ?? []).map((r) => (
                  <tr key={r.id} className="border-b last:border-0" data-testid={`po-receipt-row-${r.id}`}>
                    <td className="py-1 pr-2 tabular-nums">{r.received_date}</td>
                    <td className="py-1 pr-2">{r.delivery_note_reference ?? '—'}</td>
                    <td className="py-1 pr-2 text-right tabular-nums">{(r.lines ?? []).length}</td>
                    <td className="py-1 pr-2 text-right tabular-nums">{(r.photos ?? []).length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'approvals' && (
        <div className="text-sm text-sy-grey-600" data-testid="po-detail-approvals">
          {(po.approvals ?? []).length === 0
            ? 'No approval history.'
            : (
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-xs text-sy-grey-700 border-b">
                    <th className="py-1 pr-2">When</th>
                    <th className="py-1 pr-2">By</th>
                    <th className="py-1 pr-2">Resolution</th>
                    <th className="py-1 pr-2">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {(po.approvals ?? []).map((a) => (
                    <tr key={a.id} className="border-b last:border-0">
                      <td className="py-1 pr-2 tabular-nums">{a.created_at?.slice(0, 10)}</td>
                      <td className="py-1 pr-2">{a.approver_name ?? a.approver_user_id?.slice(0, 8)}</td>
                      <td className="py-1 pr-2">{a.resolution}</td>
                      <td className="py-1 pr-2">{a.reason ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </div>
      )}

      {tab === 'audit' && (
        <div className="text-sm text-sy-grey-600" data-testid="po-detail-audit">
          Audit history lives at <Link className="underline" to={`/audit?resource_id=${po.id}`}>/audit?resource_id={po.id}</Link>.
        </div>
      )}
    </div>
  );
}
