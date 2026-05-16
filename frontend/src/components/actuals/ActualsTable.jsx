/**
 * ActualsTable (Chat 19B §R2.4).
 *
 * TanStack Table v8. Single-column sort (date desc default). Row click
 * navigates to `/projects/:projectId/actuals/:actualId`.
 */
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  flexRender, getCoreRowModel, getSortedRowModel, useReactTable,
} from '@tanstack/react-table';
import { fmtGBP } from '@/lib/format';
import { ActualStatusBadge } from './ActualStatusBadge';

export function ActualsTable({ actuals, projectId, lineLookup }) {
  const navigate = useNavigate();

  const columns = useMemo(() => [
    {
      accessorKey: 'transaction_date',
      header: 'Date',
      cell: ({ getValue }) => (
        <span className="tabular text-sm">{getValue()}</span>
      ),
    },
    {
      accessorKey: 'supplier_name_snapshot',
      header: 'Supplier',
      cell: ({ getValue }) => (
        <span className="font-medium text-slate-900">{getValue() || '—'}</span>
      ),
    },
    {
      accessorKey: 'description',
      header: 'Description',
      cell: ({ getValue }) => {
        const v = getValue() || '';
        return (
          <span title={v} className="text-slate-700">
            {v.length > 60 ? v.slice(0, 60) + '…' : v}
          </span>
        );
      },
    },
    {
      accessorKey: 'net_amount',
      header: () => <span className="block text-right">Net</span>,
      cell: ({ getValue }) => (
        <span className="block text-right tabular">{fmtGBP(getValue())}</span>
      ),
    },
    {
      accessorKey: 'vat_amount',
      header: () => <span className="block text-right">VAT</span>,
      cell: ({ getValue }) => (
        <span className="block text-right tabular text-slate-600">{fmtGBP(getValue())}</span>
      ),
    },
    {
      accessorKey: 'gross_amount',
      header: () => <span className="block text-right">Gross</span>,
      cell: ({ getValue }) => (
        <span className="block text-right tabular font-medium">{fmtGBP(getValue())}</span>
      ),
    },
    {
      accessorKey: 'budget_line_id',
      header: 'Cost line',
      cell: ({ getValue }) => {
        const lineId = getValue();
        const name = lineLookup?.get(lineId);
        if (name) return <span className="text-sm text-slate-700">{name}</span>;
        return (
          <span className="text-xs font-mono text-slate-400" title={lineId}>
            {lineId?.slice(0, 8)}…
          </span>
        );
      },
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <ActualStatusBadge status={getValue()} />,
    },
  ], [lineLookup]);

  const table = useReactTable({
    data: actuals,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    initialState: {
      sorting: [{ id: 'transaction_date', desc: true }],
    },
  });

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200" data-testid="actuals-table">
        <thead className="bg-slate-50">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th
                  key={h.id}
                  className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600"
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              data-testid={`actual-row-${row.original.id}`}
              onClick={() => navigate(`/projects/${projectId}/actuals/${row.original.id}`)}
              className="cursor-pointer hover:bg-slate-50"
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2 text-sm">
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
