/**
 * ReceiptsSection — R6 (Buildertrend-style inline expandable row).
 *
 * Lazy-fetches receipts for a single PO via:
 *
 *     GET /api/v1/purchase-orders/{po_id}/receipts
 *
 * Mounted lazily by POsSection only when a PO is in a receiptable
 * status. Sensitive amount columns fall back to "—" via
 * <SensitiveValue/> when the server returns `null`.
 */
import { useReceipts } from '@/hooks/purchaseOrders';
import SensitiveValue from '@/components/po/SensitiveValue';
import { fmtGBP } from '@/lib/poFormat';
import { ReceiptPhotoThumb } from './ReceiptPhotoThumb';

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toISOString().slice(0, 10);
}

export function ReceiptsSection({ poId }) {
  const { data, isLoading, isError, error, refetch, isFetching } = useReceipts(poId);

  if (isLoading) {
    return (
      <div
        className="px-2 py-1 text-xs text-slate-400"
        data-testid={`bg2-receipts-loading-${poId}`}
      >
        Loading receipts…
      </div>
    );
  }
  if (isError) {
    return (
      <div
        className="flex items-center justify-between px-2 py-1 text-xs text-rose-700"
        data-testid={`bg2-receipts-error-${poId}`}
      >
        <span>
          Failed to load receipts. {error?.friendlyMessage ?? error?.message ?? ''}
        </span>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="ml-2 rounded border border-rose-300 bg-white px-1.5 py-0.5 text-[10px] font-medium text-rose-700 hover:bg-rose-50 disabled:cursor-progress disabled:opacity-60"
          data-testid={`bg2-receipts-retry-${poId}`}
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
        className="px-2 py-1 text-xs text-slate-400"
        data-testid={`bg2-receipts-empty-${poId}`}
      >
        No receipts logged against this PO yet.
      </div>
    );
  }

  return (
    <table
      className="w-full text-xs"
      data-testid={`bg2-receipts-table-${poId}`}
    >
      <thead className="text-[10px] uppercase tracking-wide text-slate-400">
        <tr>
          <th className="px-2 py-1 text-left">Photo</th>
          <th className="px-2 py-1 text-left">Date</th>
          <th className="px-2 py-1 text-left">Reference</th>
          <th className="px-2 py-1 text-right">Amount</th>
          <th className="px-2 py-1 text-left">Logged by</th>
        </tr>
      </thead>
      <tbody>
        {items.map((r) => (
          <tr
            key={r.id}
            className="border-t border-slate-100"
            data-testid={`bg2-receipt-${r.id}`}
          >
            <td className="px-2 py-1">
              <ReceiptPhotoThumb
                photo={(r.photos ?? [])[0] ?? null}
                receiptId={r.id}
              />
            </td>
            <td className="px-2 py-1 text-slate-600">
              {formatDate(r.received_at ?? r.received_date ?? r.created_at)}
            </td>
            <td className="px-2 py-1">{r.delivery_note_reference ?? r.reference ?? '—'}</td>
            <td className="px-2 py-1 text-right font-mono tabular-nums">
              <SensitiveValue
                value={r.amount}
                format={fmtGBP}
                testid={`bg2-receipt-amt-${r.id}`}
              />
            </td>
            <td className="px-2 py-1 text-slate-500">
              {r.created_by_name ?? '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default ReceiptsSection;
