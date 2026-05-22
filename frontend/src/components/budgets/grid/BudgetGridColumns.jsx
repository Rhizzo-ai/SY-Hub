/**
 * BudgetGridColumns — Chat 23 R3.2.
 *
 * 12-column definition for TanStack Table. 6 default-visible (per Q1).
 * `forecast_profit` + `forecast_margin_pct` are conditionally created:
 * if the user lacks `budgets.view_sensitive`, those columns don't exist
 * at all (safer than relying on hide-visibility for security).
 *
 * The Notes column is the ONLY non-display column with inline edit
 * (Q7); all other field edits route through LineDrawer via the
 * actions menu (`⋯` icon).
 */
import { createColumnHelper } from '@tanstack/react-table';
import { ChevronDown, ChevronRight, MoreHorizontal } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { MoneyCell } from './MoneyCell';
import { VarianceCell } from './VarianceCell';
import { NotesCell } from './NotesCell';

const ch = createColumnHelper();

export function makeColumns({
  costCodeMap,
  canEdit,
  canViewSensitive,
  budgetId,
  onOpenDrawer,
}) {
  const cols = [
    ch.display({
      id: 'select',
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllRowsSelected()}
          onCheckedChange={(v) => table.toggleAllRowsSelected(Boolean(v))}
          aria-label="Select all rows"
          data-testid="bg2-select-all"
        />
      ),
      cell: ({ row }) => (
        row.original.isGroup ? null : (
          <Checkbox
            checked={row.getIsSelected()}
            onCheckedChange={(v) => row.toggleSelected(Boolean(v))}
            aria-label={`Select line`}
            data-testid={`bg2-select-row-${row.original.id}`}
          />
        )
      ),
      enableHiding: false,
      enableSorting: false,
      size: 32,
    }),
    ch.display({
      id: 'expand',
      header: '',
      cell: ({ row }) => {
        // R6: Group rows expand via TanStack. Line-row expansion now
        // lives on the leading column's dedicated `bg2-line-expand-*`
        // button (URL-backed via ?expanded=), so this column cell only
        // renders for groups.
        const orig = row.original;
        if (!orig.isGroup) return null;
        if (!row.getCanExpand()) return null;
        return (
          <button
            type="button"
            onClick={() => row.toggleExpanded()}
            aria-label={row.getIsExpanded() ? 'Collapse' : 'Expand'}
            className="text-slate-500 hover:text-slate-700"
            data-testid={`bg2-expand-${orig.groupKey ?? orig.id}`}
          >
            {row.getIsExpanded()
              ? <ChevronDown size={14} />
              : <ChevronRight size={14} />}
          </button>
        );
      },
      enableHiding: false,
      enableSorting: false,
      size: 24,
    }),
    ch.accessor((row) => row.cost_code_id, {
      id: 'cost_code',
      header: 'Cost code',
      cell: ({ getValue, row }) => {
        if (row.original.isGroup) return null;
        if (row.original.isItem) {
          // Items display their own description in this column slot so
          // the cost-code column isn't blank for sub-rows.
          return (
            <span className="pl-4 text-xs text-slate-500">
              ↳ {row.original.description}
            </span>
          );
        }
        return (
          <span className="font-mono text-xs text-slate-700">
            {costCodeMap.get(getValue())?.code ?? '—'}
          </span>
        );
      },
      size: 130,
    }),
    ch.accessor('line_description', {
      id: 'line_description',
      header: 'Description',
      cell: ({ getValue, row }) => {
        if (row.original.isGroup) {
          return (
            <span className="font-semibold text-slate-900">
              {row.original.groupLabel}
            </span>
          );
        }
        if (row.original.isItem) return null;
        return <span className="text-sm text-slate-700">{getValue() ?? '—'}</span>;
      },
      size: 260,
    }),

    ch.accessor('original_budget', {
      id: 'original_budget',
      header: 'Original budget',
      cell: (info) => (
        <MoneyCell
          value={info.row.original.isGroup
            ? info.row.original.totals?.original_budget
            : info.getValue()}
        />
      ),
    }),
    ch.accessor('current_budget', {
      id: 'current_budget',
      header: 'Current budget',
      cell: (info) => (
        <MoneyCell
          value={info.row.original.isGroup
            ? info.row.original.totals?.current_budget
            : info.getValue()}
        />
      ),
    }),
    ch.accessor('approved_changes', {
      id: 'pending_changes',
      header: 'Pending changes',
      cell: (info) => (
        <MoneyCell
          value={info.row.original.isGroup
            ? info.row.original.totals?.approved_changes
            : info.getValue()}
        />
      ),
    }),
    ch.accessor('committed_value', {
      id: 'committed',
      header: 'Committed',
      cell: (info) => (
        <MoneyCell
          value={info.row.original.isGroup
            ? info.row.original.totals?.committed_value
            : info.getValue()}
        />
      ),
    }),
    ch.accessor('actuals_to_date', {
      id: 'actual_spent',
      header: 'Actual spent',
      cell: (info) => (
        <MoneyCell
          value={info.row.original.isGroup
            ? info.row.original.totals?.actuals_to_date
            : info.getValue()}
        />
      ),
    }),
    ch.accessor('variance_value', {
      id: 'variance_to_budget',
      header: 'Variance to budget',
      cell: ({ row, getValue }) => {
        if (row.original.isItem) return null;
        return (
          <VarianceCell
            value={row.original.isGroup
              ? row.original.totals?.variance_value
              : getValue()}
            status={row.original.variance_status}
            pct={row.original.variance_pct}
          />
        );
      },
    }),
    ch.accessor('forecast_final_cost', {
      id: 'forecast_cost',
      header: 'Forecast cost',
      cell: ({ row, getValue }) => (
        <MoneyCell
          value={row.original.isGroup
            ? row.original.totals?.forecast_final_cost
            : getValue()}
          tintByStatus={row.original.variance_status}
        />
      ),
    }),
    ch.accessor('forecast_to_complete', {
      id: 'cost_to_complete',
      header: 'Cost to complete',
      cell: (info) => (
        <MoneyCell
          value={info.row.original.isGroup
            ? info.row.original.totals?.forecast_to_complete
            : info.getValue()}
        />
      ),
    }),
    ch.display({
      id: 'variance_to_forecast',
      header: 'Variance to forecast',
      cell: ({ row }) => {
        if (row.original.isItem) return null;
        const ffc = Number(row.original.forecast_final_cost ?? row.original.totals?.forecast_final_cost ?? 0);
        const orig = Number(row.original.original_budget ?? row.original.totals?.original_budget ?? 0);
        const v = ffc - orig;
        return (
          <VarianceCell
            value={v}
            status={row.original.variance_status}
            pct={orig > 0 ? (v / orig) * 100 : 0}
          />
        );
      },
    }),
  ];

  // R3.9: Profit + Margin columns ONLY when the user can view sensitive
  // fields. Backend strips `_allocated_sale_price_provisional` from
  // non-sensitive responses (R3.9b), so even if these columns existed
  // for non-sensitive users they'd compute to NaN.
  if (canViewSensitive) {
    cols.push(
      ch.display({
        id: 'forecast_profit',
        header: 'Forecast profit',
        cell: ({ row }) => {
          if (row.original.isItem || row.original.isGroup) return null;
          const sale = Number(row.original._allocated_sale_price_provisional ?? 0);
          const ffc = Number(row.original.forecast_final_cost ?? 0);
          return <MoneyCell value={sale - ffc} />;
        },
      }),
      ch.display({
        id: 'forecast_margin_pct',
        header: 'Forecast margin %',
        cell: ({ row }) => {
          if (row.original.isItem || row.original.isGroup) return null;
          const sale = Number(row.original._allocated_sale_price_provisional ?? 0);
          const ffc = Number(row.original.forecast_final_cost ?? 0);
          if (sale <= 0) return <span className="block text-right text-slate-400">—</span>;
          const margin = ((sale - ffc) / sale) * 100;
          return (
            <span className="block text-right font-mono tabular-nums">
              {margin.toFixed(1)}%
            </span>
          );
        },
      }),
    );
  }

  cols.push(
    ch.accessor('ftc_method', {
      id: 'projection_reference',
      header: 'Projection reference',
      cell: ({ getValue, row }) => {
        if (row.original.isGroup || row.original.isItem) return null;
        return <span className="text-xs text-slate-600">{getValue() ?? '—'}</span>;
      },
    }),
    ch.accessor('notes', {
      id: 'notes',
      header: 'Notes',
      cell: ({ row, getValue }) => {
        if (row.original.isGroup || row.original.isItem) return null;
        return (
          <NotesCell
            value={getValue()}
            canEdit={canEdit}
            lineId={row.original.id}
            budgetId={budgetId}
          />
        );
      },
    }),
    ch.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => {
        if (row.original.isGroup || row.original.isItem) return null;
        return (
          <button
            type="button"
            onClick={() => onOpenDrawer?.(row.original.id)}
            aria-label="Open line details"
            className="text-slate-400 hover:text-slate-700"
            data-testid={`bg2-actions-${row.original.id}`}
          >
            <MoreHorizontal size={16} />
          </button>
        );
      },
      enableHiding: false,
      enableSorting: false,
      size: 36,
    }),
  );

  return cols;
}

// Default visibility (6 money columns + always-on rails).
export const INITIAL_COLUMN_VISIBILITY = {
  select: true,
  expand: true,
  cost_code: true,
  line_description: true,
  current_budget: true,
  committed: true,
  actual_spent: true,
  variance_to_budget: true,
  forecast_cost: true,
  cost_to_complete: true,
  notes: true,
  actions: true,
  // Default-hidden:
  original_budget: false,
  pending_changes: false,
  variance_to_forecast: false,
  forecast_profit: false,
  forecast_margin_pct: false,
  projection_reference: false,
};
