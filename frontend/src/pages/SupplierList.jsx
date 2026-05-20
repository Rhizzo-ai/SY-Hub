/**
 * SupplierList — Chat 24 §R5.
 *
 * Lightweight supplier directory (table). Status filter (Active /
 * Archived), free-text search, "+ New supplier" gated on
 * suppliers.create. Sensitive columns (bank, VAT) are not in the list
 * view — they only appear on SupplierDetail.
 */
import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { useSuppliers } from '@/hooks/purchaseOrders';
import { useAuth } from '@/context/AuthContext';
import { canCreateSupplier, canViewSuppliers } from '@/lib/poCapability';

export default function SupplierList() {
  const { user } = useAuth();
  const [statusFilter, setStatusFilter] = useState('Active');
  const [search, setSearch] = useState('');

  const { data, isLoading, isError } = useSuppliers({
    params: { status: statusFilter, search: search || undefined },
  });

  const rows = useMemo(() => data?.items ?? [], [data]);

  if (!canViewSuppliers(user)) {
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
        {canCreateSupplier(user) && (
          <Link
            to="/suppliers/new"
            className="px-3 py-1.5 rounded bg-sy-teal-600 text-white text-sm"
            data-testid="supplier-list-new-btn"
          >
            + New supplier
          </Link>
        )}
      </header>

      <div className="flex gap-2 items-end">
        <label className="text-sm flex flex-col">
          <span className="text-xs text-sy-grey-600">Status</span>
          <select
            className="px-2 py-1 border rounded text-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            data-testid="supplier-list-status-filter"
          >
            <option value="Active">Active</option>
            <option value="Archived">Archived</option>
            <option value="">All</option>
          </select>
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
                <td className="py-2 pr-2">{s.status ?? '—'}</td>
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
