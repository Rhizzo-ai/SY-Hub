/**
 * BillsSection — Chat 23 R4.4 (LIVE).
 *
 * Reads bills (actuals) linked to a budget line via the existing
 * `/api/v1/actuals?budget_line_id=...` endpoint. Renders the table
 * shape mandated by Build Pack §R4.4: Reference / Supplier / Amount
 * / Status / Date / Open-link.
 *
 * Empty state + loading + error pinned to the same shell so the
 * column widths stay stable across states (avoids drilldown shift).
 */
import { Link } from 'react-router-dom';
import { formatMoney } from '@/lib/format';
import { useActualsForBudgetLine } from '@/hooks/actuals';
import { BillStatusBadge } from './BillStatusBadge';

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toISOString().slice(0, 10);
}

export function BillsSection({ budgetLineId, projectId }) {
  const { data, isLoading, isError, error } = useActualsForBudgetLine(
    budgetLineId, projectId,
  );

  if (isLoading) {
    return (
      <div className="p-3 text-sm text-slate-500" data-testid="bg2-bills-loading">
        Loading bills…
      </div>
    );
  }
  if (isError) {
    return (
      <div className="p-3 text-sm text-rose-600" data-testid="bg2-bills-error">
        Failed to load bills. {error?.message ?? ''}
      </div>
    );
  }

  const bills = data?.items ?? [];
  if (!bills.length) {
    return (
      <div
        className="rounded border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500"
        data-testid="bg2-bills-empty"
      >
        No bills posted to this line yet.
      </div>
    );
  }

  return (
    <table className="w-full text-sm" data-testid="bg2-bills-table">
      <thead className="text-xs uppercase tracking-wide text-slate-500">
        <tr>
          <th className="px-2 py-1 text-left">Reference</th>
          <th className="px-2 py-1 text-left">Supplier</th>
          <th className="px-2 py-1 text-right">Amount</th>
          <th className="px-2 py-1 text-left">Status</th>
          <th className="px-2 py-1 text-left">Date</th>
          <th className="px-2 py-1" />
        </tr>
      </thead>
      <tbody>
        {bills.map((bill) => (
          <tr
            key={bill.id}
            className="border-t border-slate-100"
            data-testid={`bg2-bill-${bill.id}`}
          >
            <td className="px-2 py-2">
              {bill.supplier_invoice_ref ?? bill.source_reference ?? '—'}
            </td>
            <td className="px-2 py-2">{bill.supplier_name_snapshot ?? '—'}</td>
            <td className="px-2 py-2 text-right font-mono tabular-nums">
              {formatMoney(bill.gross_amount)}
            </td>
            <td className="px-2 py-2">
              <BillStatusBadge status={bill.status} />
            </td>
            <td className="px-2 py-2 text-slate-600">
              {formatDate(bill.posted_at ?? bill.transaction_date ?? bill.created_at)}
            </td>
            <td className="px-2 py-2 text-right">
              <Link
                to={`/projects/${projectId}/actuals/${bill.id}`}
                className="text-sky-700 hover:underline"
                data-testid={`bg2-bill-open-${bill.id}`}
              >
                Open
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
