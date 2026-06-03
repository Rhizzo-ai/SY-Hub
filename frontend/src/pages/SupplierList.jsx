/**
 * SupplierList — Chat 24 §R5 · Chat 40 §R2 D3/D5 fixes.
 *
 * Lightweight supplier directory (table). Free-text search + a
 * show-archived toggle, "+ New supplier" gated on suppliers.create.
 * Sensitive columns (bank, VAT) are not in the list view — they only
 * appear on SupplierDetail.
 *
 * §R2 D3 — backend has no `status` field; it has `is_archived: bool`.
 *   The 2.5 client read `s.status` and compared to the string
 *   'Archived', which never matched → archived rows looked active and
 *   the filter was a no-op.
 * §R2 D5 — backend list params are `{q, include_archived, supplier_type, limit, offset}`,
 *   not `{status, search}`. The 2.5 client sent params the router
 *   ignored, so filters appeared to work locally but had no effect on
 *   the query. We now send `{q, include_archived}`. The `supplier_type`
 *   filter UI is part of the 2.7-FE ADD half (§R4.1) and is not wired
 *   here yet.
 */
import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { useSuppliers } from '@/hooks/purchaseOrders';
import { useAuth } from '@/context/AuthContext';
import { canCreateSupplier, canViewSuppliers } from '@/lib/poCapability';

export default function SupplierList() {
  const { me } = useAuth();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [search, setSearch] = useState('');

  const { data, isLoading, isError } = useSuppliers({
    params: {
      include_archived: includeArchived || undefined,
      q: search || undefined,
    },
  });

  const rows = useMemo(() => data?.items ?? [], [data]);

  if (!canViewSuppliers(me)) {
    return (
      <div className="p-6 text-sm" data-testid="supplier-list-forbidden">
        You do not have permission to view suppliers.
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4" data-testid="supplier-list">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Suppliers</h1>
        {canCreateSupplier(me) && (
          <Link
            to="/suppliers/new"
            className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm"
            data-testid="supplier-list-new-btn"
          >
            + New supplier
          </Link>
        )}
      </header>

      <div className="flex gap-3 items-end">
        <label className="text-sm flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
            data-testid="supplier-list-archived-toggle"
          />
          <span>Show archived</span>
        </label>
        <label className="text-sm flex flex-col flex-1">
          <span className="text-xs text-sy-grey-600">Search</span>
          <input
            type="search"
            className="px-2 py-1 border rounded text-sm"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Supplier name…"
            data-testid="supplier-list-search"
          />
        </label>
      </div>

      {isLoading && <div className="text-sm" data-testid="supplier-list-loading">Loading…</div>}
      {isError && <div className="text-sm text-red-600">Failed to load suppliers.</div>}

      {!isLoading && !isError && (
        <table className="w-full text-sm border-collapse" data-testid="supplier-list-table">
          <thead>
            <tr className="text-left text-xs text-sy-grey-700 border-b">
              <th className="py-2 pr-2">Name</th>
              <th className="py-2 pr-2">CIS</th>
              <th className="py-2 pr-2">Status</th>
              <th className="py-2 pr-2 w-32">Default VAT</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={4} className="py-3 text-sy-grey-500" data-testid="supplier-list-empty">
                No suppliers match.
              </td></tr>
            )}
            {rows.map((s) => (
              <tr key={s.id} className="border-b last:border-0" data-testid={`supplier-row-${s.id}`}>
                <td className="py-2 pr-2">
                  <Link to={`/suppliers/${s.id}`} className="text-sy-teal-700 underline">
                    {s.name}
                  </Link>
                </td>
                <td className="py-2 pr-2">{s.cis_status ?? '—'}</td>
                <td className="py-2 pr-2">
                  {s.is_archived
                    ? <span className="text-sy-grey-500" data-testid={`supplier-row-archived-${s.id}`}>Archived</span>
                    : <span>Active</span>}
                </td>
                <td className="py-2 pr-2 tabular-nums">
                  {s.default_vat_rate != null ? `${s.default_vat_rate}%` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
