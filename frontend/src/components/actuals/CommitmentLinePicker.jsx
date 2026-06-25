/**
 * CommitmentLinePicker (C1-front · Chat 64 §R4.2).
 *
 * Forces the bill-entry choice: when posting a bill on a budget line the user
 * must either pick one of the open PO lines on that line, or explicitly choose
 * "No PO available" (standalone cost). The gate itself lives in the parent
 * (CreateActualSheet §R4.3); this component renders the choice and surfaces a
 * parent-supplied error.
 *
 * Eligibility (client-side — see the `?status=` note below):
 *   - parent PO status ∈ PO_COMMITTED_STATUSES
 *   - line.budget_line_id === budgetLineId (a PO can touch several lines)
 * Fully-invoiced lines (remaining "0.00" AND fully receipted) are shown greyed
 * and not selectable rather than hidden — hiding makes POs "disappear".
 *
 * Money sensitivity: remaining_amount / net_amount come back null for callers
 * without pos.view_sensitive; we then render the label WITHOUT a money suffix
 * (never "£null"). Selection is by id, so the gate still works.
 */
import { useEffect, useMemo } from 'react';
import { usePurchaseOrdersForBudgetLine } from '@/hooks/purchaseOrders';
import { formatMoney } from '@/lib/format';

// Kept in lock-step with the backend tuple
// budgets_reconciliation.PO_COMMITTED_STATUSES — PO statuses whose lines hold a
// live commitment a bill can pay down. Filtered client-side because the wire
// form of an array `?status=` param is unverified (no paramsSerializer in
// api.js); we fetch all POs for the line and narrow here.
export const PO_COMMITTED_STATUSES = [
  'approved', 'issued', 'partially_receipted', 'receipted',
];

export function CommitmentLinePicker({
  projectId,
  budgetLineId,
  value,
  onChange,
  standalone,
  onStandaloneChange,
  error,
  disabled,
}) {
  const enabled = !!budgetLineId && !disabled;
  const { data, isLoading } = usePurchaseOrdersForBudgetLine(budgetLineId, {
    enabled,
  });

  // Flatten returned POs → eligible PO lines on THIS budget line.
  const eligibleLines = useMemo(() => {
    const items = data?.items ?? [];
    const out = [];
    for (const po of items) {
      if (!PO_COMMITTED_STATUSES.includes(po.status)) continue;
      for (const line of po.lines ?? []) {
        if (String(line.budget_line_id) !== String(budgetLineId)) continue;
        const fullyInvoiced =
          line.remaining_amount === '0.00' && !!line.is_fully_receipted;
        out.push({
          id: line.id,
          poNumber: po.po_number,
          description: line.description,
          remaining: line.remaining_amount, // string | null
          netAmount: line.net_amount,       // string | null
          fullyInvoiced,
        });
      }
    }
    return out;
  }, [data, budgetLineId]);

  const isEmpty = enabled && !isLoading && eligibleLines.length === 0;

  // §R4.2(4) — no eligible lines ⇒ auto-treat as standalone so submit is
  // unblocked, without forcing a tick. Guard so we only flip once.
  useEffect(() => {
    if (isEmpty && !standalone) {
      onStandaloneChange(true);
    }
  }, [isEmpty]);

  if (!budgetLineId || disabled) {
    return (
      <p
        className="text-sm text-slate-400"
        data-testid="commitment-picker-hint"
      >
        Select a budget line first.
      </p>
    );
  }

  if (isLoading) {
    return (
      <div
        className="text-sm text-slate-500"
        data-testid="commitment-picker-loading"
      >
        Loading purchase orders…
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div
        data-testid="commitment-picker-empty"
        className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600"
      >
        No open purchase orders on this budget line — this will be recorded as a
        standalone cost.
      </div>
    );
  }

  const renderMoney = (line) => {
    // No money perms → omit the suffix entirely (never "£null").
    if (line.netAmount == null) return null;
    return (
      <span className="text-xs text-slate-500">
        {formatMoney(line.remaining)} remaining of {formatMoney(line.netAmount)}
      </span>
    );
  };

  return (
    <div data-testid="commitment-picker" className="space-y-1.5">
      <div
        className="rounded-md border border-slate-200 divide-y divide-slate-100"
        role="radiogroup"
        aria-label="Purchase order this bill pays"
        aria-required="true"
      >
        {eligibleLines.map((line) => {
          const checked = !standalone && value === line.id;
          return (
            <label
              key={line.id}
              data-testid={`commitment-picker-line-${line.id}`}
              className={[
                'flex items-center justify-between gap-3 px-3 py-2 text-sm',
                line.fullyInvoiced
                  ? 'cursor-not-allowed opacity-50'
                  : 'cursor-pointer hover:bg-slate-50',
              ].join(' ')}
            >
              <span className="flex items-center gap-2 min-w-0">
                <input
                  type="radio"
                  name="commitment-line"
                  className="shrink-0 accent-sy-teal"
                  checked={checked}
                  disabled={line.fullyInvoiced}
                  onChange={() => {
                    if (line.fullyInvoiced) return;
                    onStandaloneChange(false);
                    onChange(line.id);
                  }}
                />
                <span className="truncate">
                  <span className="font-medium">{line.poNumber}</span>
                  {' · '}
                  {line.description}
                  {line.fullyInvoiced && (
                    <span className="ml-1 text-xs text-slate-400">
                      (fully invoiced)
                    </span>
                  )}
                </span>
              </span>
              {renderMoney(line)}
            </label>
          );
        })}

        <label
          data-testid="commitment-picker-standalone"
          className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-slate-50"
        >
          <input
            type="radio"
            name="commitment-line"
            className="shrink-0 accent-sy-teal"
            checked={!!standalone}
            onChange={() => {
              onChange(null);
              onStandaloneChange(true);
            }}
          />
          <span>No PO available</span>
        </label>
      </div>

      {error && (
        <p
          className="text-sm text-rose-600"
          data-testid="commitment-picker-error"
        >
          {error}
        </p>
      )}
    </div>
  );
}
