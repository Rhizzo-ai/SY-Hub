/**
 * <POReceiptDialog/> — R7 Batch 2 §R7.4.
 *
 * Modal form for capturing a receipt against an `issued` /
 * `partially_receipted` PO. Posts to POST /v1/purchase-orders/{id}/receipts
 * via `useCreateReceipt`, which now coarse-invalidates `['budgets']`
 * on success (AC5 — committed → actual movement).
 *
 * Form shape mirrors the backend ReceiptCreate schema:
 *   - received_date (date, required)
 *   - delivery_note_reference (optional)
 *   - notes (optional)
 *   - lines: [{ po_line_id, quantity_received: float > 0 }]
 *
 * Only PO lines with remaining quantity (quantity - receipted_quantity)
 * appear in the form. The user fills the row(s) they're receiving; rows
 * left blank or set to 0 are excluded from the payload (backend
 * requires at least one line with qty > 0).
 *
 * Dialog primitive matches the send-back / reject pattern already used
 * by <POActionButtons/>.
 */
import React, { useMemo, useState } from 'react';
import { toast } from 'sonner';

import { useCreateReceipt } from '@/hooks/purchaseOrders';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';


function remainingQty(line) {
  const ordered = Number(line.quantity ?? 0);
  const received = Number(line.receipted_quantity ?? 0);
  // Keep a small floor: floating-point noise on partials can read as
  // 0.000000001 — clamp anything under 0.0001 to "fully receipted".
  const rem = ordered - received;
  return rem > 0.0001 ? rem : 0;
}


export default function POReceiptDialog({ open, onOpenChange, po }) {
  const today = new Date().toISOString().slice(0, 10);
  const create = useCreateReceipt(po?.id);

  const [date, setDate] = useState(today);
  const [deliveryRef, setDeliveryRef] = useState('');
  const [notes, setNotes] = useState('');
  // Map of po_line_id -> string qty (string for input control).
  const [qtyMap, setQtyMap] = useState({});

  // Reset form whenever the dialog re-opens.
  React.useEffect(() => {
    if (open) {
      setDate(today);
      setDeliveryRef('');
      setNotes('');
      setQtyMap({});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const eligibleLines = useMemo(() => {
    return (po?.lines ?? []).filter((l) => remainingQty(l) > 0);
  }, [po?.lines]);

  // Build payload lines from the qtyMap (qty > 0 only).
  const payloadLines = useMemo(() => {
    return Object.entries(qtyMap)
      .map(([po_line_id, qty]) => {
        const n = Number(qty);
        if (!Number.isFinite(n) || n <= 0) return null;
        return { po_line_id, quantity_received: n };
      })
      .filter(Boolean);
  }, [qtyMap]);

  const canSubmit =
    !!date && payloadLines.length > 0 && !create.isPending;

  const onSubmit = async () => {
    try {
      const body = {
        received_date: date,
        lines: payloadLines,
      };
      if (deliveryRef.trim()) body.delivery_note_reference = deliveryRef.trim();
      if (notes.trim()) body.notes = notes.trim();
      await create.mutateAsync(body);
      toast.success('Receipt recorded');
      onOpenChange(false);
    } catch (err) {
      toast.error(
        err?.response?.data?.detail?.message
        ?? err?.response?.data?.detail
        ?? err?.message
        ?? 'Receipt failed',
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-2xl"
        data-testid="po-receipt-dialog"
      >
        <DialogHeader>
          <DialogTitle>Record receipt</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-sy-grey-700">
          Enter quantities received against each PO line. Leave a line
          blank or zero to skip it. Once submitted, the budget's
          committed column refreshes.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Received date *</span>
            <input
              type="date"
              className="w-full px-2 py-1 border rounded text-sm"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              data-testid="po-receipt-date"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs text-sy-grey-700">Delivery note ref.</span>
            <input
              type="text"
              className="w-full px-2 py-1 border rounded text-sm"
              value={deliveryRef}
              onChange={(e) => setDeliveryRef(e.target.value)}
              placeholder="Optional"
              data-testid="po-receipt-delivery-ref"
            />
          </label>
        </div>

        <div>
          <div className="text-xs text-sy-grey-700 mb-1">Lines</div>
          {eligibleLines.length === 0 ? (
            <div
              className="text-sm text-sy-grey-500"
              data-testid="po-receipt-no-lines"
            >
              All lines on this PO are fully receipted.
            </div>
          ) : (
            <table
              className="w-full text-sm border-collapse"
              data-testid="po-receipt-lines"
            >
              <thead>
                <tr className="text-left text-xs text-sy-grey-700 border-b">
                  <th className="py-1 pr-2">#</th>
                  <th className="py-1 pr-2">Description</th>
                  <th className="py-1 pr-2 w-24 text-right">Remaining</th>
                  <th className="py-1 pr-2 w-28 text-right">Qty to receive</th>
                </tr>
              </thead>
              <tbody>
                {eligibleLines.map((l) => {
                  const rem = remainingQty(l);
                  return (
                    <tr
                      key={l.id}
                      className="border-b last:border-0"
                      data-testid={`po-receipt-line-${l.id}`}
                    >
                      <td className="py-1 pr-2 tabular-nums">{l.line_number}</td>
                      <td className="py-1 pr-2">{l.description ?? '—'}</td>
                      <td className="py-1 pr-2 text-right tabular-nums">
                        {rem.toFixed(4)}
                      </td>
                      <td className="py-1 pr-2 text-right">
                        <input
                          type="number"
                          min="0"
                          step="any"
                          className="w-24 px-2 py-1 border rounded text-sm text-right tabular-nums"
                          value={qtyMap[l.id] ?? ''}
                          onChange={(e) =>
                            setQtyMap((m) => ({ ...m, [l.id]: e.target.value }))
                          }
                          data-testid={`po-receipt-qty-${l.id}`}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <label className="block text-sm">
          <span className="text-xs text-sy-grey-700">Notes</span>
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="Optional notes"
            data-testid="po-receipt-notes"
          />
        </label>

        <DialogFooter>
          <Button
            type="button" variant="outline"
            onClick={() => onOpenChange(false)}
            data-testid="po-receipt-cancel"
          >Cancel</Button>
          <Button
            type="button"
            disabled={!canSubmit}
            onClick={onSubmit}
            data-testid="po-receipt-confirm"
          >Record receipt</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
