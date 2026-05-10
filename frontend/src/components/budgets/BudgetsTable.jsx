/**
 * BudgetsTable — Prompt 2.4B-i §R4.4.
 *
 * TanStack Table v8 grid. Columns reflect the backend summary shape (E7):
 *   version (link) · status · current/most-recent? · total_budget ·
 *   forecast_final_cost (sensitive) · variance_vs_budget (sensitive) ·
 *   variance_pct (sensitive)
 *
 * Sensitive fields are `.optional()` in the Zod schema — when stripped,
 * the formatter renders "—". No client-side sensitivity flag is computed.
 */
import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { StatusBadge } from './StatusBadge';
import { VarianceBadge, deriveVarianceStatus } from './VarianceBadge';
import { formatMoney, formatPercent } from '@/lib/format';

export function BudgetsTable({ budgets, projectId }) {
  const columns = useMemo(() => [
    {
      accessorKey: 'version_number',
      header: 'Version',
      cell: ({ row }) => (
        <Link
          to={`/projects/${projectId}/budgets/${row.original.id}`}
          className="font-mono text-sm text-slate-900 hover:underline"
          data-testid={`budget-row-link-${row.original.id}`}
        >
          v{row.original.version_number}
          {row.original.version_label && (
            <span className="ml-1 text-slate-500">
              · {row.original.version_label}
            </span>
          )}
        </Link>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    },
    {
      accessorKey: 'is_current',
      header: 'Current?',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.is_current ? (
          <span className="text-xs font-medium text-emerald-700"
                data-testid="budget-row-current-marker">
            ● Current
          </span>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
    },
    {
      accessorKey: 'total_budget',
      header: 'Total budget',
      cell: ({ row }) => (
        <span className="font-mono text-sm text-slate-900">
          {formatMoney(row.original.total_budget)}
        </span>
      ),
    },
    {
      accessorKey: 'forecast_final_cost',
      header: 'FFC',
      cell: ({ row }) => (
        <span className="font-mono text-sm text-slate-900">
          {formatMoney(row.original.forecast_final_cost)}
        </span>
      ),
    },
    {
      accessorKey: 'variance_vs_budget',
      header: 'Variance',
      cell: ({ row }) => {
        const v = row.original.variance_vs_budget;
        const pct = row.original.variance_pct;
        const status = deriveVarianceStatus(pct);
        return (
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm">
              {v == null
                ? '—'
                : formatMoney(v)}
            </span>
            <VarianceBadge status={status} value={v} pct={pct} />
          </div>
        );
      },
    },
  ], [projectId]);

  const table = useReactTable({
    data: budgets,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    initialState: {
      sorting: [{ id: 'version_number', desc: true }],
    },
  });

  if (!budgets.length) {
    return (
      <div
        data-testid="budgets-table-empty"
        className="rounded-lg border border-slate-200 p-12 text-center text-slate-500"
      >
        No budgets yet. Create one from an approved appraisal.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200"
         data-testid="budgets-table">
      <table className="w-full text-sm">
        <thead className="bg-slate-50">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th
                  key={h.id}
                  scope="col"
                  className={`px-4 py-2 text-left font-medium text-slate-700 ${h.column.getCanSort() ? 'cursor-pointer select-none' : ''}`}
                  onClick={h.column.getCanSort() ? h.column.getToggleSortingHandler() : undefined}
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                  {h.column.getIsSorted() === 'asc' && ' ▲'}
                  {h.column.getIsSorted() === 'desc' && ' ▼'}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              data-testid={`budget-row-${row.original.id}`}
              className="border-t border-slate-100 hover:bg-slate-50"
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-2 align-middle">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
