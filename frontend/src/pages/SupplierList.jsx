/**
 * SupplierList — Chat 24 §R5 · Chat 40 §R2 D3/D5 + §R4.1 ADD half.
 *
 * Filters row:
 *   - Type (All / Supplier / Subcontractor) → `supplier_type` param
 *     (omit on All). Seeded from `?type=` query string so the nav
 *     "Subcontractors" link lands pre-filtered.
 *   - Show-archived toggle → `include_archived`
 *   - Free-text search    → `q`
 *
 * CIS column shows CISStatusBadge on subcontractor rows; suppliers
 * read "—". §R6 unverified cue: amber dot + tooltip on
 * subcontractor rows whose `current_cis_status` is null/Unverified/
 * Unmatched, plus a header summary line counting them.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';

import { useSuppliers } from '@/hooks/purchaseOrders';
import { useAuth } from '@/context/AuthContext';
import { canCreateSupplier, canViewSuppliers } from '@/lib/poCapability';
import CISStatusBadge from '@/components/suppliers/CISStatusBadge';

const TYPE_OPTIONS = [
  { value: 'All', label: 'All' },
  { value: 'Supplier', label: 'Suppliers' },
  { value: 'Subcontractor', label: 'Subcontractors' },
];

const UNVERIFIED_STATES = new Set([null, undefined, 'Unverified', 'Unmatched']);

export default function SupplierList() {
  const { me } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // §R4.1 — Seed Type filter from `?type=Subcontractor` so the nav
  // link lands pre-filtered. Default 'All'.
  const initialType = (() => {
    const t = searchParams.get('type');
    return TYPE_OPTIONS.some((o) => o.value === t) ? t : 'All';
  })();
  const [typeFilter, setTypeFilter] = useState(initialType);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [search, setSearch] = useState('');

  // Keep the URL in sync so the filter is shareable/bookmarkable.
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (typeFilter === 'All') {
      next.delete('type');
    } else {
      next.set('type', typeFilter);
    }
    // Only update when actually different to avoid noisy history.
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typeFilter]);

  const { data, isLoading, isError } = useSuppliers({
    params: {
      include_archived: includeArchived || undefined,
      q: search || undefined,
      supplier_type: typeFilter === 'All' ? undefined : typeFilter,
    },
  });

  const rows = useMemo(() => data?.items ?? [], [data]);

  // §R6 unverified cue — only meaningful when Type=Subcontractor.
  const unverifiedCount = useMemo(() => {
    if (typeFilter !== 'Subcontractor') return 0;
    return rows.filter((s) => UNVERIFIED_STATES.has(s.current_cis_status)).length;
  }, [rows, typeFilter]);

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
        <h1 className="text-xl font-semibold">
          {typeFilter === 'Subcontractor' ? 'Subcontractors'
            : typeFilter === 'Supplier' ? 'Suppliers'
            : 'Suppliers'}
        </h1>
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

      <div className="flex gap-3 items-end flex-wrap">
        <label className="text-sm flex flex-col">
          <span className="text-xs text-sy-grey-600">Type</span>
          <select
            className="px-2 py-1 border rounded text-sm"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            data-testid="supplier-list-type-filter"
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
        <label className="text-sm flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
            data-testid="supplier-list-archived-toggle"
          />
          <span>Show archived</span>
        </label>
        <label className="text-sm flex flex-col flex-1 min-w-[160px]">
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

      {unverifiedCount > 0 && (
        <div
          className="flex items-center gap-2 text-sm text-orange-800 bg-orange-50 border border-orange-200 rounded p-2"
          data-testid="supplier-list-unverified-summary"
        >
          <AlertCircle size={14} />
          <span>
            {unverifiedCount} subcontractor{unverifiedCount === 1 ? '' : 's'} need CIS verification
          </span>
        </div>
      )}

      {isLoading && <div className="text-sm" data-testid="supplier-list-loading">Loading…</div>}
      {isError && <div className="text-sm text-red-600">Failed to load suppliers.</div>}

      {!isLoading && !isError && (
        <table className="w-full text-sm border-collapse" data-testid="supplier-list-table">
          <thead>
            <tr className="text-left text-xs text-sy-grey-700 border-b">
              <th className="py-2 pr-2">Name</th>
              <th className="py-2 pr-2">Type</th>
              <th className="py-2 pr-2">CIS</th>
              <th className="py-2 pr-2">Status</th>
              <th className="py-2 pr-2 w-32">Default VAT</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={5} className="py-3 text-sy-grey-500" data-testid="supplier-list-empty">
                No suppliers match.
              </td></tr>
            )}
            {rows.map((s) => {
              const isSub = s.supplier_type === 'Subcontractor';
              // §R4.1 / §R6b — cue only when the user is looking at the
              // subcontractor view (Type filter = Subcontractor). On the
              // mixed list the cue would be noise.
              const needsCis = typeFilter === 'Subcontractor'
                && isSub
                && UNVERIFIED_STATES.has(s.current_cis_status);
              return (
                <tr key={s.id} className="border-b last:border-0" data-testid={`supplier-row-${s.id}`}>
                  <td className="py-2 pr-2">
                    <span className="inline-flex items-center gap-2">
                      <Link to={`/suppliers/${s.id}`} className="text-sy-teal-700 underline">
                        {s.name}
                      </Link>
                      {needsCis && (
                        <span
                          className="inline-block w-2 h-2 rounded-full bg-orange-500"
                          title="CIS not verified"
                          data-testid={`supplier-row-unverified-${s.id}`}
                        />
                      )}
                    </span>
                  </td>
                  <td className="py-2 pr-2">{s.supplier_type ?? 'Supplier'}</td>
                  <td className="py-2 pr-2">
                    {isSub
                      ? <CISStatusBadge status={s.current_cis_status} testid={`supplier-row-cis-${s.id}`} />
                      : <span>—</span>}
                  </td>
                  <td className="py-2 pr-2">
                    {s.is_archived
                      ? <span className="text-sy-grey-500" data-testid={`supplier-row-archived-${s.id}`}>Archived</span>
                      : <span>Active</span>}
                  </td>
                  <td className="py-2 pr-2 tabular-nums">
                    {s.default_vat_rate != null ? `${s.default_vat_rate}%` : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
