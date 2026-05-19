/**
 * BulkActionsBar — Chat 23 §R7.2.
 *
 * Renders BELOW the header tiles and ABOVE the toolbar when ≥1 line is
 * selected. Three actions: Export CSV, Delete selected, Clear selection.
 *
 * Locked decisions baked in:
 *   - Selection is line-level only (groups + items aren't selectable —
 *     that gate is already enforced in BudgetGridColumns + the table's
 *     `enableRowSelection` predicate). This bar trusts the parent to
 *     pass a clean line-only `selectedLines` array.
 *   - Bulk delete fan-out is sequential (max 100 rows). While the fan-out
 *     runs, the bar swaps in a live progress meter — "Deleted X of N…" —
 *     so a 50-row delete shows continuous feedback instead of a single
 *     spinner blob.
 *   - CSV export is on-screen-only (current visible columns + filtered
 *     rows OR selected rows). Sensitive-field gating is automatic because
 *     Profit/Margin columns aren't even constructed for non-sensitive
 *     users (see BudgetGridColumns.jsx).
 */
import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { toCsv, downloadCsv } from '@/lib/csv';
import { deleteBudgetLine } from '@/lib/api/budgets';
import { useQueryClient } from '@tanstack/react-query';
import { budgetsKeys } from '@/hooks/budgets';
import { BulkDeleteConfirmDialog } from './BulkDeleteConfirmDialog';

export const BULK_DELETE_MAX = 100;

function buildCsvText(table, selectedLines, costCodeMap) {
  // Visible leaf columns drive both header and body. We deliberately
  // drop columns whose value is purely UI (select, expand, actions)
  // because they don't carry data the user would want in a spreadsheet.
  const SKIP_COLUMN_IDS = new Set(['select', 'expand', 'actions']);
  const cols = table
    .getVisibleLeafColumns()
    .filter((c) => !SKIP_COLUMN_IDS.has(c.id));

  const header = cols.map((c) => {
    const h = c.columnDef.header;
    return typeof h === 'string' ? h : c.id;
  });

  const rows = selectedLines.map((line) => cols.map((c) => {
    // The `cost_code` column uses `ch.accessor(fn, {...})` (accessorFn
    // form) rather than the string `accessorKey` form, so `accessorKey`
    // is undefined. The on-screen cell looks the FK up in costCodeMap
    // and renders the short `code` (e.g. "ACQ-01"). The CSV must do
    // the same resolution; without this the column lands as a blank
    // in every exported row. Regression pin: see
    // BulkActionsBar.test.jsx::"CSV resolves cost_code FK to the
    // human-readable code (regression pin from §R7 spot-check)".
    if (c.id === 'cost_code') {
      return costCodeMap?.get(line.cost_code_id)?.code ?? '';
    }
    // Prefer the raw accessor value where present; for `display` columns
    // (variance_to_forecast, forecast_profit, forecast_margin_pct) we
    // fall back to a sensible field-level read so the CSV captures the
    // numeric signal even though the on-screen cell is a synthesised
    // JSX node.
    const acc = c.columnDef.accessorKey;
    if (acc) return line[acc] ?? '';
    if (c.id === 'variance_to_forecast') {
      const ffc = Number(line.forecast_final_cost ?? 0);
      const orig = Number(line.original_budget ?? 0);
      return ffc - orig;
    }
    if (c.id === 'forecast_profit') {
      const sale = Number(line._allocated_sale_price_provisional ?? 0);
      const ffc = Number(line.forecast_final_cost ?? 0);
      return sale - ffc;
    }
    if (c.id === 'forecast_margin_pct') {
      const sale = Number(line._allocated_sale_price_provisional ?? 0);
      const ffc = Number(line.forecast_final_cost ?? 0);
      if (sale <= 0) return '';
      return (((sale - ffc) / sale) * 100).toFixed(1);
    }
    return '';
  }));

  return toCsv([header, ...rows]);
}

export function BulkActionsBar({
  selectedLines,
  table,
  budget,
  costCodeMap,
  canEdit,
  editable,
  onClear,
}) {
  const qc = useQueryClient();
  const count = selectedLines.length;
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [progress, setProgress] = useState(null);
    // null → idle; { done, failed, total } during fan-out.

  const canDelete = canEdit && editable && !progress;
  const overCap = count > BULK_DELETE_MAX;

  const exportLabel = useMemo(
    () => `Export CSV (${count})`,
    [count],
  );

  function handleExport() {
    try {
      const csv = buildCsvText(table, selectedLines, costCodeMap);
      const stamp = new Date().toISOString().slice(0, 10);
      const name = `budget-${budget?.id?.slice(0, 8) ?? 'lines'}-${stamp}.csv`;
      downloadCsv(csv, name);
      toast.success(`Exported ${count} ${count === 1 ? 'line' : 'lines'} to CSV`);
    } catch (e) {
      toast.error(`CSV export failed: ${e?.message ?? 'unknown error'}`);
    }
  }

  async function runBulkDelete() {
    setConfirmOpen(false);
    const ids = selectedLines.map((l) => l.id);
    const total = ids.length;
    setProgress({ done: 0, failed: 0, total });
    const failed = [];
    for (let i = 0; i < ids.length; i += 1) {
      try {
        // eslint-disable-next-line no-await-in-loop
        await deleteBudgetLine(ids[i]);
        setProgress({ done: i + 1, failed: failed.length, total });
      } catch (e) {
        failed.push({ id: ids[i], message: e?.response?.data?.detail ?? e?.message });
        setProgress({ done: i + 1, failed: failed.length, total });
      }
    }
    // Single cache invalidation at the end (not per-row) — the budget
    // detail will refetch once with the final state.
    qc.invalidateQueries({ queryKey: budgetsKeys.detail(budget.id) });
    qc.invalidateQueries({ queryKey: budgetsKeys.all });
    if (failed.length === 0) {
      toast.success(
        `Deleted ${total} ${total === 1 ? 'line' : 'lines'}`,
      );
    } else if (failed.length === total) {
      toast.error(`Bulk delete failed — 0 of ${total} lines deleted`);
    } else {
      toast.error(
        `Bulk delete partial — ${total - failed.length} of ${total} deleted, ${failed.length} failed`,
      );
    }
    setProgress(null);
    onClear?.();
  }

  // While the fan-out is in flight, swap the static bar for a live
  // progress meter so the user sees per-row updates ("Deleted 12 of 50…").
  if (progress) {
    const { done, failed, total } = progress;
    const pct = Math.round((done / total) * 100);
    return (
      <div
        className="flex items-center justify-between rounded bg-slate-100 px-3 py-2"
        data-testid="bg2-bulk-bar-progress"
      >
        <div className="flex flex-col gap-1">
          <span className="text-sm text-slate-700" data-testid="bg2-bulk-progress-label">
            Deleted {done} of {total}{failed > 0 ? ` (${failed} failed)` : ''}…
          </span>
          <div
            className="h-1 w-48 overflow-hidden rounded bg-slate-200"
            aria-label="Bulk delete progress"
          >
            <div
              className="h-full bg-sy-teal transition-all"
              style={{ width: `${pct}%` }}
              data-testid="bg2-bulk-progress-bar"
            />
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div
        className="flex items-center justify-between rounded bg-slate-100 px-3 py-2"
        data-testid="bg2-bulk-bar"
      >
        <span className="text-sm text-slate-700" data-testid="bg2-bulk-count">
          {count} {count === 1 ? 'line' : 'lines'} selected
          {overCap && (
            <span className="ml-2 text-rose-700">
              — over {BULK_DELETE_MAX}-line cap; refine your selection
            </span>
          )}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleExport}
            disabled={count === 0}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            data-testid="bg2-bulk-export"
          >
            {exportLabel}
          </button>
          {canDelete && (
            <button
              type="button"
              onClick={() => setConfirmOpen(true)}
              disabled={count === 0 || overCap}
              className="rounded bg-sy-orange px-3 py-1.5 text-sm font-medium text-white hover:brightness-110 active:brightness-95 disabled:opacity-50"
              data-testid="bg2-bulk-delete"
            >
              Delete selected
            </button>
          )}
          <button
            type="button"
            onClick={onClear}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            data-testid="bg2-bulk-clear"
          >
            Clear
          </button>
        </div>
      </div>
      <BulkDeleteConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        count={count}
        onConfirm={runBulkDelete}
      />
    </>
  );
}

// Export the inner CSV builder so tests can exercise it without a DOM.
export const __test__ = { buildCsvText };
