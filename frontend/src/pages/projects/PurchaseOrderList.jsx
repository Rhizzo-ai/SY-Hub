/**
 * PurchaseOrderList — Chat 24 §R5.
 *
 * Project-scoped PO list. URL-bound status filter; clickable rows route
 * to the detail page. Sensitive columns (gross totals, supplier banking)
 * fall back to "—" when the user lacks pos.view_sensitive.
 *
 * TanStack Table is wired but the current list is small enough that we
 * just render a plain HTML table — the table abstraction graduates in
 * R6 when sorting/grouping arrives.
 */
import React from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { useAuth } from '@/context/AuthContext';
import { useProjectPOs } from '@/hooks/purchaseOrders';
import {
  canCreatePO, canViewPOs, canViewSensitivePO,
} from '@/lib/poCapability';
import POStatusPill from '@/components/po/POStatusPill';
import POApprovalsTab from '@/components/po/POApprovalsTab';
import SensitiveValue from '@/components/po/SensitiveValue';
import { fmtGBP } from '@/lib/poFormat';

const PO_STATUSES = [
  'draft', 'submitted', 'approved', 'issued',
  'partially_receipted', 'receipted', 'closed',
  'voided', 'rejected',
];

const TABS = ['all', 'approvals'];

export default function PurchaseOrderList() {
  const { id: projectId } = useParams();
  const { me } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const status = searchParams.get('status') || '';
  const tab = searchParams.get('tab') === 'approvals' ? 'approvals' : 'all';

  const canSensitive = canViewSensitivePO(me);
  const { data, isLoading, isError } = useProjectPOs(projectId, {
    params: status ? { status } : undefined,
    enabled: tab === 'all',
  });
  const rows = data?.items ?? [];

  if (!canViewPOs(me)) {
    return <div className="p-6 text-sm" data-testid="po-list-forbidden">
      You do not have permission to view purchase orders.
    </div>;
  }

  const setStatus = (v) => {
    const next = new URLSearchParams(searchParams);
    if (v) next.set('status', v); else next.delete('status');
    setSearchParams(next);
  };

  const setTab = (t) => {
    const next = new URLSearchParams(searchParams);
    if (t === 'approvals') next.set('tab', 'approvals'); else next.delete('tab');
    setSearchParams(next);
  };

  return (
    <div className="p-6 space-y-4" data-testid="po-list">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Purchase orders</h1>
        {canCreatePO(me) && (
          <Link
            to={`/projects/${projectId}/purchase-orders/new`}
            className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm"
            data-testid="po-list-new-btn"
          >+ New PO</Link>
        )}
      </header>

      {/* R7.5 — Tabs: All POs / Approvals dashboard */}
      <nav className="flex gap-2 border-b" data-testid="po-list-tabs">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-sm ${tab === t ? 'border-b-2 border-sy-teal-600 font-semibold' : 'text-sy-grey-700'}`}
            data-testid={`po-list-tab-${t}`}
          >{t === 'all' ? 'All POs' : 'Awaiting approval'}</button>
        ))}
      </nav>

      {tab === 'approvals' ? (
        <POApprovalsTab />
      ) : (
        <>
          <div className="flex gap-2 items-end">
            <label className="text-sm flex flex-col">
              <span className="text-xs text-sy-grey-600">Status</span>
              <select
                className="px-2 py-1 border rounded text-sm"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                data-testid="po-list-status-filter"
              >
                <option value="">All</option>
                {PO_STATUSES.map((s) => (
                  <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
                ))}
              </select>
            </label>
          </div>

          {isLoading && <div className="text-sm" data-testid="po-list-loading">Loading…</div>}
          {isError && <div className="text-sm text-red-600" data-testid="po-list-error">
            Failed to load purchase orders.
          </div>}

          {!isLoading && !isError && (
            <table className="w-full text-sm border-collapse" data-testid="po-list-table">
              <thead>
                <tr className="text-left text-xs text-sy-grey-700 border-b">
                  <th className="py-2 pr-2 w-32">Number</th>
                  <th className="py-2 pr-2">Supplier</th>
                  <th className="py-2 pr-2 w-40">Status</th>
                  <th className="py-2 pr-2 w-32 text-right">Gross</th>
                  <th className="py-2 pr-2 w-32">Issued</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={5} className="py-3 text-sy-grey-500" data-testid="po-list-empty">
                    No purchase orders match.
                  </td></tr>
                )}
                {rows.map((po) => (
                  <tr key={po.id} className="border-b last:border-0" data-testid={`po-row-${po.id}`}>
                    <td className="py-2 pr-2">
                      <Link
                        to={`/projects/${projectId}/purchase-orders/${po.id}`}
                        className="text-sy-teal-700 underline tabular-nums"
                      >{po.po_number ?? '—'}</Link>
                    </td>
                    <td className="py-2 pr-2">{po.supplier_name ?? '—'}</td>
                    <td className="py-2 pr-2"><POStatusPill status={po.status} /></td>
                    <td className="py-2 pr-2 text-right tabular-nums">
                      <SensitiveValue
                        value={po.gross_total}
                        format={fmtGBP}
                        hidden={!canSensitive}
                        testid={`po-row-${po.id}-gross`}
                      />
                    </td>
                    <td className="py-2 pr-2 tabular-nums">{po.issued_at?.slice(0, 10) ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
