/**
 * <SupplierSelect/> — Chat 24 §R5.
 *
 * Combobox over the active supplier directory with a "+ create new" affordance.
 * Used by PurchaseOrderForm. Renders a plain <select> in this first
 * pass — we'll graduate to cmdk if R6 needs typeahead-over-1000-suppliers,
 * but a select-with-search-filter is the lightest accessible option
 * here and keeps the test surface clean.
 *
 * Props:
 *   - value, onChange:   controlled select value
 *   - allowCreate:       show the "+ create new inline" button (gated on perm)
 *   - onCreateRequested: handler that opens a dialog / inline form
 */
import React, { useState, useMemo } from 'react';

import { useSuppliers } from '@/hooks/purchaseOrders';

export function SupplierSelect({
  value, onChange,
  allowCreate = false, onCreateRequested,
  disabled = false,
  testid = 'supplier-select',
}) {
  const [filter, setFilter] = useState('');
  const { data, isLoading, isError } = useSuppliers({ params: { status: 'Active' } });
  const items = useMemo(() => {
    const all = data?.items ?? [];
    if (!filter.trim()) return all;
    const q = filter.trim().toLowerCase();
    return all.filter((s) => (s.name ?? '').toLowerCase().includes(q));
  }, [data, filter]);

  return (
    <div className="space-y-1" data-testid={testid}>
      <input
        type="search"
        placeholder="Filter suppliers…"
        className="w-full px-2 py-1 border rounded text-sm"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        disabled={disabled}
        data-testid={`${testid}-filter`}
      />
      <select
        className="w-full px-2 py-1 border rounded text-sm"
        value={value ?? ''}
        onChange={(e) => onChange?.(e.target.value || null)}
        disabled={disabled || isLoading || isError}
        data-testid={`${testid}-select`}
      >
        <option value="">
          {isLoading ? 'Loading…' : isError ? 'Error loading suppliers' : '— Select supplier —'}
        </option>
        {items.map((s) => (
          <option key={s.id} value={s.id}>{s.name}</option>
        ))}
      </select>
      {allowCreate && (
        <button
          type="button"
          onClick={onCreateRequested}
          disabled={disabled}
          className="text-xs underline text-sy-teal-700"
          data-testid={`${testid}-create-new`}
        >
          + Create new supplier
        </button>
      )}
    </div>
  );
}

export default SupplierSelect;
