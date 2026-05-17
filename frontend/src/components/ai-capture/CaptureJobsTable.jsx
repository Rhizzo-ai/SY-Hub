// frontend/src/components/ai-capture/CaptureJobsTable.jsx — Chat 19C §R2.6
//
// TanStack Table render of the inbox. Columns: Received (relative time),
// Supplier guess, Net guess, Confidence, Status, Attempts. Whole row is
// clickable; onRowClick navigates to the detail page.
import { useMemo } from 'react';
import {
  flexRender, getCoreRowModel, getSortedRowModel, useReactTable,
} from '@tanstack/react-table';
import { format, formatDistanceToNow, parseISO } from 'date-fns';
import { CaptureStatusBadge } from './CaptureStatusBadge';
import { ConfidencePill } from './ConfidencePill';
import { fmtGBP } from '@/lib/format';

export function CaptureJobsTable({ jobs, total, onRowClick }) {
  const columns = useMemo(() => [
    {
      accessorKey: 'created_at',
      header: 'Received',
      cell: ({ getValue }) => {
        const v = getValue();
        if (!v) return '—';
        try {
          return formatDistanceToNow(parseISO(v), { addSuffix: true });
        } catch {
          return v;
        }
      },
    },
    {
      id: 'supplier',
      header: 'Supplier (AI guess)',
      cell: ({ row }) => row.original?.extracted_data?.supplier_name ?? '—',
    },
    {
      id: 'net',
      header: 'Net (AI guess)',
      cell: ({ row }) => fmtGBP(row.original?.extracted_data?.net_amount),
    },
    {
      id: 'overall_confidence',
      header: 'Confidence',
      cell: ({ row }) => (
        <ConfidencePill value={row.original?.confidence_scores?.overall} />
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <CaptureStatusBadge status={getValue()} />,
    },
    {
      accessorKey: 'attempts',
      header: 'Attempts',
      cell: ({ getValue }) => getValue() ?? 0,
    },
  ], []);

  const table = useReactTable({
    data: jobs,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (!jobs?.length) {
    return (
      <div
        className="rounded-md border border-slate-200 bg-white p-8 text-center text-sm text-slate-500"
        data-testid="capture-jobs-empty"
      >
        No capture jobs match this filter.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
      <table className="w-full text-sm" data-testid="capture-jobs-table">
        <thead className="bg-slate-50 text-left">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id} className="px-4 py-2 font-medium text-slate-600">
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              data-testid={`capture-row-${row.original.id}`}
              className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
              onClick={() => onRowClick(row.original)}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-2">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="px-4 py-2 text-xs text-slate-500" data-testid="capture-jobs-total">
        {jobs.length} of {total}
      </div>
    </div>
  );
}
