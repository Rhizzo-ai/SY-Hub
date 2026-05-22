/**
 * POsSection — R6 (Buildertrend-style inline expandable budget-line grid).
 *
 * Lazy-fetches purchase orders scoped to a single budget line via the
 * R5.5 endpoint:
 *
 *     GET /api/v1/budget-lines/{line_id}/purchase-orders
 *
 * Mounting is gated by the parent expanded-row, so the hook only fires
 * on first expand and React Query's cache makes subsequent expands
 * instant.
 *
 * Sensitive money columns (line totals, supplier banking) come back
 * as `null` for callers without `pos.view_sensitive` — <SensitiveValue/>
 * keeps the layout stable with a stable em-dash placeholder.
 */
import { Link } from 'react-router-dom';
import { useBudgetLinePOs } from '@/hooks/purchaseOrders';
import POStatusPill from '@/components/po/POStatusPill';
import SensitiveValue from '@/components/po/SensitiveValue';
import { fmtGBP } from '@/lib/poFormat';
import { ReceiptsSection } from './ReceiptsSection';

export function POsSection({ lineId, projectId }) {
  const query = useBudgetLinePOs(lineId);
  const { data, isLoading, isError, error, refetch, isFetching } = query;

  if (isLoading) {
    return (
      <div className="p-3 text-sm text-slate-500" data-testid="bg2-pos-loading">
        Loading purchase orders…
      </div>
    );
  }
  if (isError) {
    return (
      <div
        className="flex items-center justify-between rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
        data-testid="bg2-pos-error"
      >
        <span>
          Failed to load purchase orders. {error?.friendlyMessage ?? error?.message ?? ''}
        </span>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="ml-3 rounded border border-rose-300 bg-white px-2 py-1 text-xs font-medium text-rose-700 hover:bg-rose-100 disabled:cursor-progress disabled:opacity-60"
          data-testid="bg2-pos-retry"
        >
          {isFetching ? 'Retrying…' : 'Retry'}
        </button>
      </div>
    );
  }

  const items = data?.items ?? [];
  if (!items.length) {
    return (
      <div
        className="rounded border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500"
        data-testid="bg2-pos-empty"
      >
        No purchase orders raised against this line yet.
      </div>
    );
  }

  return (
    <table className="w-full text-sm" data-testid="bg2-pos-table">
      <thead className="text-xs uppercase tracking-wide text-slate-500">
        <tr>
          <th className="px-2 py-1 text-left">PO #</th>
          <th className="px-2 py-1 text-left">Supplier</th>
          <th className="px-2 py-1 text-left">Status</th>
          <th className="px-2 py-1 text-right">Gross</th>
          <th className="px-2 py-1 text-left">Issued</th>
          <th className="px-2 py-1" />
        </tr>
      </thead>
      <tbody>
        {items.map((po) => (
          <PORow key={po.id} po={po} projectId={projectId} />
        ))}
      </tbody>
    </table>
  );
}

function PORow({ po, projectId }) {
  // Sensitive money fields come back as `null` for users without
  // pos.view_sensitive. We pass `hidden=false` and rely on
  // SensitiveValue's own null-handling to render "—" — i.e. the
  // server-side gating IS the source of truth.
  return (
    <>
      <tr
        className="border-t border-slate-100"
        data-testid={`bg2-po-${po.id}`}
      >
        <td className="px-2 py-2 font-mono tabular-nums">
          <Link
            to={`/projects/${projectId}/purchase-orders/${po.id}`}
            className="text-sky-700 hover:underline"
            data-testid={`bg2-po-open-${po.id}`}
          >
            {po.po_number ?? '—'}
          </Link>
        </td>
        <td className="px-2 py-2">{po.supplier_name ?? '—'}</td>
        <td className="px-2 py-2">
          <POStatusPill status={po.status} />
        </td>
        <td className="px-2 py-2 text-right font-mono tabular-nums">
          <SensitiveValue
            value={po.gross_total}
            format={fmtGBP}
            testid={`bg2-po-gross-${po.id}`}
          />
        </td>
        <td className="px-2 py-2 text-slate-600">
          {po.issued_at?.slice(0, 10) ?? '—'}
        </td>
        <td className="px-2 py-2" />
      </tr>
      {/* Receipts roll up directly under each issued PO so site
          managers can verify what's been delivered without leaving
          the line. */}
      {['issued', 'partially_receipted', 'receipted', 'closed'].includes(po.status) && (
        <tr
          className="bg-white"
          data-testid={`bg2-po-receipts-row-${po.id}`}
        >
          <td colSpan={6} className="px-2 py-1">
            <ReceiptsSection poId={po.id} />
          </td>
        </tr>
      )}
    </>
  );
}

export default POsSection;
