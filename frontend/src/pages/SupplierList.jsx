/**
 * SupplierList — Chat 24 §R5 · Chat 40 §R2 · Chat 41 §R5
 *   (Build Pack 2.7-FE-revision).
 *
 * Filters row:
 *   - Type: 4-way (All / Contractor / Supplier / Consultant / Other)
 *     → `supplier_type` param (omit on All). Seeded from `?type=`. A
 *     stale `?type=Subcontractor` falls back to 'All' (the existing
 *     guard rejects unknown values).
 *   - Show-archived toggle  → `include_archived`
 *   - Free-text search      → `q`
 *   - <ColumnPicker/>       → session-only optional-column visibility
 *
 * Columns:
 *   - CORE (locked, always shown): Name, Type, Status
 *   - OPTIONAL (toggleable): Trade (default-on), CIS (default-on),
 *     VAT registered, Payment terms, Email, Phone
 *
 * CIS badge + the §R6 unverified cue (amber dot + summary banner)
 * gate on `Contractor` rather than the prior `Subcontractor` literal.
 *
 * Per-user column persistence is backlog item B-COLS (operator-owned).
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AlertCircle, ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

import { useSuppliers } from '@/hooks/purchaseOrders';
import { useAuth } from '@/context/AuthContext';
import { canCreateSupplier, canViewSuppliers } from '@/lib/poCapability';
import CISStatusBadge from '@/components/suppliers/CISStatusBadge';
import ColumnPicker from '@/components/suppliers/ColumnPicker';

const TYPE_OPTIONS = [
  { value: 'All', label: 'All' },
  { value: 'Contractor', label: 'Contractors' },
  { value: 'Supplier', label: 'Suppliers' },
  { value: 'Consultant', label: 'Consultants' },
  { value: 'Other', label: 'Other' },
];

const CORE_COLS = ['name', 'type', 'status'];
const OPTIONAL_COLS = [
  { key: 'trade',          label: 'Trade',          default: true  },
  { key: 'cis',            label: 'CIS',            default: true  },
  { key: 'payment_terms',  label: 'Payment terms',  default: false },
  { key: 'email',          label: 'Email',          default: false },
  { key: 'phone',          label: 'Phone',          default: false },
];

const UNVERIFIED_STATES = new Set([null, undefined, 'Unverified', 'Unmatched']);

export default function SupplierList() {
  const { me } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Seed Type filter from `?type=`. Unknown / dropped values (e.g. a
  // stale "?type=Subcontractor" bookmark) fall back to 'All'.
  const initialType = (() => {
    const t = searchParams.get('type');
    return TYPE_OPTIONS.some((o) => o.value === t) ? t : 'All';
  })();
  const [typeFilter, setTypeFilter] = useState(initialType);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [search, setSearch] = useState('');

  // §R5.4 — Session-only optional-column visibility. Per-user
  // persistence is backlog B-COLS.
  const [visible, setVisible] = useState(
    () => new Set(OPTIONAL_COLS.filter((c) => c.default).map((c) => c.key)),
  );
  const toggleCol = (key) => setVisible((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  // Keep the URL in sync so the filter is shareable/bookmarkable.
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (typeFilter === 'All') {
      next.delete('type');
    } else {
      next.set('type', typeFilter);
    }
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

  // Chat 41 §R-eyeball-Step2B Part 2 — click-to-sort.
  // Cycle: unsorted → asc → desc → unsorted (third click clears).
  // Clicking a different column resets to asc. Sort is CLIENT-SIDE
  // over the currently-loaded rows (the list isn't paginated-heavy yet).
  //
  // CIS sorts on `current_cis_status` (the badge value), Trade on the
  // serialised `trade` name; null/empty values sink to the bottom of
  // an asc sort regardless of direction (a stable convention used by
  // most data-grid libraries).
  const SORT_VALUE_GETTERS = useMemo(() => ({
    name:          (s) => (s.name || '').toLowerCase(),
    type:          (s) => (s.supplier_type || '').toLowerCase(),
    trade:         (s) => (s.trade || '').toLowerCase(),
    cis:           (s) => (s.current_cis_status || ''),
    payment_terms: (s) => (s.payment_terms_days ?? Number.POSITIVE_INFINITY),
    email:         (s) => (s.contact_email || '').toLowerCase(),
    phone:         (s) => (s.contact_phone || '').toLowerCase(),
  }), []);

  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState(null); // 'asc' | 'desc' | null

  // When a hidden column was the active sort, drop it on the next
  // render so the indicator doesn't ghost into the visible header set.
  useEffect(() => {
    if (sortKey && sortKey !== 'name' && sortKey !== 'type' && !visible.has(sortKey)) {
      setSortKey(null); setSortDir(null);
    }
  }, [visible, sortKey]);

  const onHeaderClick = (key) => {
    if (sortKey !== key) {
      setSortKey(key); setSortDir('asc'); return;
    }
    if (sortDir === 'asc')  { setSortDir('desc'); return; }
    if (sortDir === 'desc') { setSortKey(null); setSortDir(null); return; }
    setSortDir('asc');
  };

  const sortedRows = useMemo(() => {
    if (!sortKey || !sortDir) return rows;
    const getValue = SORT_VALUE_GETTERS[sortKey];
    if (!getValue) return rows;
    // Slice first — never mutate the React-Query cache result.
    const copy = rows.slice();
    copy.sort((a, b) => {
      const va = getValue(a);
      const vb = getValue(b);
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ?  1 : -1;
      return 0;
    });
    return copy;
  }, [rows, sortKey, sortDir, SORT_VALUE_GETTERS]);

  // Unverified cue — only meaningful on the Contractor view.
  const unverifiedCount = useMemo(() => {
    if (typeFilter !== 'Contractor') return 0;
    return rows.filter((s) => UNVERIFIED_STATES.has(s.current_cis_status)).length;
  }, [rows, typeFilter]);

  // Heading label is driven by the selected type — "Contractors",
  // "Consultants", "Other" when filtered, else "Suppliers" (the
  // app-wide name for the contact book).
  const headingLabel = (() => {
    if (typeFilter === 'All') return 'Suppliers';
    const opt = TYPE_OPTIONS.find((o) => o.value === typeFilter);
    return opt?.label ?? 'Suppliers';
  })();

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
        <h1 className="text-xl font-semibold">{headingLabel}</h1>
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
        <div className="ml-auto">
          <ColumnPicker
            options={OPTIONAL_COLS}
            visible={visible}
            onToggle={toggleCol}
          />
        </div>
      </div>

      {unverifiedCount > 0 && (
        <div
          className="flex items-center gap-2 text-sm text-orange-800 bg-orange-50 border border-orange-200 rounded p-2"
          data-testid="supplier-list-unverified-summary"
        >
          <AlertCircle size={14} />
          <span>
            {unverifiedCount} contractor{unverifiedCount === 1 ? '' : 's'} need CIS verification
          </span>
        </div>
      )}

      {isLoading && <div className="text-sm" data-testid="supplier-list-loading">Loading…</div>}
      {isError && <div className="text-sm text-red-600">Failed to load suppliers.</div>}

      {!isLoading && !isError && (
        <table className="w-full text-sm border-collapse" data-testid="supplier-list-table">
          <thead>
            <tr className="text-left text-xs text-sy-grey-700 border-b">
              <SortableTH colKey="name" label="Name" sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
              <SortableTH colKey="type" label="Type" sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
              <th className="py-2 pr-2" data-testid="supplier-list-col-status">Status</th>
              {visible.has('trade') && (
                <SortableTH colKey="trade" label="Trade" sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
              )}
              {visible.has('cis') && (
                <SortableTH colKey="cis" label="CIS" sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
              )}
              {visible.has('payment_terms') && (
                <SortableTH colKey="payment_terms" label="Payment terms" className="w-32" sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
              )}
              {visible.has('email') && (
                <SortableTH colKey="email" label="Email" sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
              )}
              {visible.has('phone') && (
                <SortableTH colKey="phone" label="Phone" sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
              )}
            </tr>
          </thead>
          <tbody>
            {sortedRows.length === 0 && (
              <tr><td
                colSpan={CORE_COLS.length + visible.size}
                className="py-3 text-sy-grey-500"
                data-testid="supplier-list-empty"
              >
                No suppliers match.
              </td></tr>
            )}
            {sortedRows.map((s) => {
              const isContractor = s.supplier_type === 'Contractor';
              // Cue only when the user is looking at the Contractor
              // view (Type filter = Contractor). On the mixed list the
              // cue would be noise.
              const needsCis = typeFilter === 'Contractor'
                && isContractor
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
                    {s.is_archived
                      ? <span className="text-sy-grey-500" data-testid={`supplier-row-archived-${s.id}`}>Archived</span>
                      : <span>Active</span>}
                  </td>
                  {visible.has('trade') && (
                    <td className="py-2 pr-2" data-testid={`supplier-row-trade-${s.id}`}>
                      {s.trade ?? '—'}
                    </td>
                  )}
                  {visible.has('cis') && (
                    <td className="py-2 pr-2">
                      {isContractor
                        ? <CISStatusBadge status={s.current_cis_status} testid={`supplier-row-cis-${s.id}`} />
                        : <span>—</span>}
                    </td>
                  )}
                  {visible.has('payment_terms') && (
                    <td className="py-2 pr-2 tabular-nums" data-testid={`supplier-row-payment-terms-${s.id}`}>
                      {s.payment_terms_days != null ? `${s.payment_terms_days} days` : '—'}
                    </td>
                  )}
                  {visible.has('email') && (
                    <td className="py-2 pr-2" data-testid={`supplier-row-email-${s.id}`}>
                      {s.contact_email ?? '—'}
                    </td>
                  )}
                  {visible.has('phone') && (
                    <td className="py-2 pr-2" data-testid={`supplier-row-phone-${s.id}`}>
                      {s.contact_phone ?? '—'}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

// Chat 41 §R-eyeball-Step2B Part 2 (Prompt 2.7-FE-revision) — clickable
// header cell with arrow indicator. Lives at module scope (not nested
// in render) so the JSX stays tidy; props are controlled by the parent
// SupplierList.
function SortableTH({ colKey, label, className = '', sortKey, sortDir, onClick }) {
  const active = sortKey === colKey;
  const Icon = !active ? ArrowUpDown : sortDir === 'asc' ? ArrowUp : ArrowDown;
  const ariaSort = !active ? 'none' : (sortDir === 'asc' ? 'ascending' : 'descending');
  return (
    <th
      className={`py-2 pr-2 ${className}`}
      data-testid={`supplier-list-col-${colKey}`}
      aria-sort={ariaSort}
    >
      <button
        type="button"
        onClick={() => onClick(colKey)}
        className="inline-flex items-center gap-1 hover:text-sy-teal-700"
        data-testid={`supplier-list-sort-${colKey}`}
      >
        <span>{label}</span>
        <Icon
          size={12}
          className={active ? 'text-sy-teal-700' : 'text-sy-grey-400'}
          data-testid={`supplier-list-sort-${colKey}-${active ? sortDir : 'none'}`}
        />
      </button>
    </th>
  );
}
