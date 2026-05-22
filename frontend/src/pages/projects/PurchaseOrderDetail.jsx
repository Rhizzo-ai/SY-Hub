/**
 * PurchaseOrderDetail — Chat 24 §R5 + Chat 26 §R7.2/§R7.3.
 *
 * Tabs: Lines / Receipts / Approvals / Audit.
 *
 * R7.2 — inline lifecycle buttons now live in <POActionButtons/>
 * (status × perm × edit_tier × self-approval handled there).
 * R7.3 — the Approvals tab now mounts <POApprovalPanel/>, which surfaces
 * the over-budget snapshot + approve/reject controls when the PO is
 * pending. Send-back lives in <POActionButtons/> on the approved row.
 *
 * Sensitive numerics still fall back to <SensitiveValue/> when the
 * caller lacks pos.view_sensitive.
 */
import React, { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { useAuth } from '@/context/AuthContext';
import { usePO, useReceipts } from '@/hooks/purchaseOrders';
import { canViewSensitivePO } from '@/lib/poCapability';
import POStatusPill from '@/components/po/POStatusPill';
import POActionButtons from '@/components/po/POActionButtons';
import POApprovalPanel from '@/components/po/POApprovalPanel';
import SensitiveValue from '@/components/po/SensitiveValue';
import { fmtGBP, fmtNumber } from '@/lib/poFormat';

const TABS = ['lines', 'receipts', 'approvals', 'audit'];


export default function PurchaseOrderDetail() {
  const { id: projectId, po_id: poId } = useParams();
  const { me } = useAuth();
  const canSensitive = canViewSensitivePO(me);
  const [tab, setTab] = useState('lines');

  const { data: po, isLoading, isError } = usePO(poId);
  const { data: receipts } = useReceipts(poId, { enabled: tab === 'receipts' });

  if (isLoading) return <div className="p-6 text-sm" data-testid="po-detail-loading">Loading…</div>;
  if (isError || !po) return <div className="p-6 text-sm text-red-600" data-testid="po-detail-error">
    Purchase order not found.
  </div>;

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
        <POActionButtons po={po} projectId={projectId} />
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
        <div data-testid="po-detail-approvals">
          <POApprovalPanel po={po} />
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
