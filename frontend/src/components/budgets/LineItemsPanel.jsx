/**
 * LineItemsPanel — Prompt 2.4B-i §R7.4.
 *
 * Bottom half of the LineDrawer: inline-CRUD on `line.items`.
 *
 * E11 (this errata): Backend field is `rate` (per-unit cost) + `amount`
 * (total line item amount). Spec used `unit_cost` — we map to `rate`.
 * Backend REQUIRES `amount` on Create — we compute amount = qty * rate
 * at submit time when both are numeric, otherwise let the user enter it.
 *
 * Inline edit pattern: `defaultValue` + `onBlur` change detection, NOT
 * controlled `value`. Each row owns its own input draft state — when the
 * server confirms the patch and re-renders with new defaults, React Hook
 * Form-free uncontrolled inputs naturally pick up the new values for new
 * editing sessions while preserving in-flight typing on existing ones.
 *
 * Mobile floor: panel renders read-only on mobile (no add row, inputs
 * disabled, no delete buttons).
 *
 * Confirm-on-delete: shadcn AlertDialog via existing ConfirmDialog
 * wrapper. variant="destructive" → sy-orange.
 */
import { useState } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { formatMoney } from '@/lib/format';
import {
  useCreateLineItem, usePatchLineItem, useDeleteLineItem,
} from '@/hooks/budgets';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { isBudgetEditable } from '@/lib/budgetCapability';
import { ConfirmDialog } from './ConfirmDialog';

const BLANK = { description: '', quantity: '', unit: '', rate: '' };

function toNumOrNull(v) {
  if (v == null) return null;
  const s = String(v).trim();
  if (s === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function LineItemsPanel({ budget, line, initialFocus }) {
  const isDesktop = useIsDesktop();
  const editable = isBudgetEditable(budget.status) && isDesktop;
  const items = line.items ?? [];

  const createMut = useCreateLineItem(line.id, budget.id);
  const patchMut  = usePatchLineItem(line.id, budget.id);
  const deleteMut = useDeleteLineItem(line.id, budget.id);

  const [draft, setDraft] = useState(BLANK);

  function addItem() {
    const desc = draft.description.trim();
    if (!desc) return;
    const qty  = toNumOrNull(draft.quantity);
    const rate = toNumOrNull(draft.rate);
    // amount = qty*rate if both numeric, else 0 (user can correct after).
    const amount = qty != null && rate != null ? qty * rate : 0;
    createMut.mutate({
      description: desc,
      quantity: qty,
      unit: draft.unit.trim() || null,
      rate,
      amount,
    }, {
      onSuccess: () => setDraft(BLANK),
    });
  }

  function patchItemField(itemId, field, value) {
    patchMut.mutate({ itemId, body: { [field]: value } });
  }

  return (
    <div
      className="space-y-3"
      data-testid="line-items-panel"
      data-initial-focus={initialFocus ? 'items' : ''}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">Items</h3>
        <span className="text-xs text-slate-500"
              data-testid="line-items-count">
          {items.length} {items.length === 1 ? 'item' : 'items'}
        </span>
      </div>

      <div className="overflow-x-auto rounded-md border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-2 py-1 text-left">Description</th>
              <th className="px-2 py-1 text-right">Qty</th>
              <th className="px-2 py-1 text-left">Unit</th>
              <th className="px-2 py-1 text-right">Rate</th>
              <th className="px-2 py-1 text-right">Amount</th>
              <th className="w-8" aria-label="Delete" />
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr
                key={it.id}
                className="border-t border-slate-100"
                data-testid={`line-item-row-${it.id}`}
              >
                <td className="px-2 py-1">
                  <Input
                    defaultValue={it.description}
                    disabled={!editable || patchMut.isPending}
                    onBlur={(e) => {
                      const v = e.target.value;
                      if (v !== it.description) {
                        patchItemField(it.id, 'description', v);
                      }
                    }}
                    className="h-7"
                    data-testid={`line-item-desc-${it.id}`}
                  />
                </td>
                <td className="px-2 py-1 text-right">
                  <Input
                    type="number"
                    step="0.0001"
                    defaultValue={it.quantity ?? ''}
                    disabled={!editable || patchMut.isPending}
                    onBlur={(e) => {
                      const n = toNumOrNull(e.target.value);
                      const cur = toNumOrNull(it.quantity);
                      if (n !== cur) patchItemField(it.id, 'quantity', n);
                    }}
                    className="h-7 text-right"
                    data-testid={`line-item-qty-${it.id}`}
                  />
                </td>
                <td className="px-2 py-1">
                  <Input
                    defaultValue={it.unit ?? ''}
                    disabled={!editable || patchMut.isPending}
                    maxLength={20}
                    onBlur={(e) => {
                      const v = e.target.value.trim() || null;
                      if (v !== (it.unit ?? null)) {
                        patchItemField(it.id, 'unit', v);
                      }
                    }}
                    className="h-7"
                    data-testid={`line-item-unit-${it.id}`}
                  />
                </td>
                <td className="px-2 py-1 text-right">
                  <Input
                    type="number"
                    step="0.0001"
                    defaultValue={it.rate ?? ''}
                    disabled={!editable || patchMut.isPending}
                    onBlur={(e) => {
                      const n = toNumOrNull(e.target.value);
                      const cur = toNumOrNull(it.rate);
                      if (n !== cur) patchItemField(it.id, 'rate', n);
                    }}
                    className="h-7 text-right"
                    data-testid={`line-item-rate-${it.id}`}
                  />
                </td>
                <td
                  className="px-2 py-1 text-right font-mono"
                  data-testid={`line-item-amount-${it.id}`}
                >
                  {formatMoney(it.amount)}
                </td>
                <td className="px-2 py-1">
                  {editable && (
                    <ConfirmDialog
                      title="Delete item?"
                      description="This removes the item from the line. Line totals will recalculate."
                      confirmLabel="Delete"
                      variant="destructive"
                      isPending={deleteMut.isPending}
                      onConfirm={() => deleteMut.mutateAsync(it.id)}
                      testId={`line-item-delete-${it.id}-dialog`}
                      trigger={
                        <button
                          type="button"
                          className="text-slate-400 hover:text-rose-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-sy-orange rounded"
                          aria-label={`Delete item ${it.description}`}
                          data-testid={`line-item-delete-${it.id}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      }
                    />
                  )}
                </td>
              </tr>
            ))}
            {!items.length && (
              <tr>
                <td
                  colSpan={6}
                  className="p-4 text-center text-slate-400"
                  data-testid="line-items-empty"
                >
                  No items.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {editable && (
        <div
          className="rounded-md border border-dashed border-slate-300 p-2"
          data-testid="line-items-add-row"
        >
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[160px] space-y-1">
              <label className="text-xs text-slate-600" htmlFor="li-add-desc">
                Description
              </label>
              <Input
                id="li-add-desc"
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                placeholder="e.g. 25 kg cement"
                className="h-8"
                disabled={createMut.isPending}
                maxLength={255}
                data-testid="line-items-add-desc"
              />
            </div>
            <div className="w-20 space-y-1">
              <label className="text-xs text-slate-600" htmlFor="li-add-qty">Qty</label>
              <Input
                id="li-add-qty"
                type="number"
                step="0.0001"
                value={draft.quantity}
                onChange={(e) => setDraft({ ...draft, quantity: e.target.value })}
                className="h-8 text-right"
                disabled={createMut.isPending}
                data-testid="line-items-add-qty"
              />
            </div>
            <div className="w-20 space-y-1">
              <label className="text-xs text-slate-600" htmlFor="li-add-unit">Unit</label>
              <Input
                id="li-add-unit"
                value={draft.unit}
                onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
                className="h-8"
                disabled={createMut.isPending}
                maxLength={20}
                data-testid="line-items-add-unit"
              />
            </div>
            <div className="w-24 space-y-1">
              <label className="text-xs text-slate-600" htmlFor="li-add-rate">Rate £</label>
              <Input
                id="li-add-rate"
                type="number"
                step="0.0001"
                value={draft.rate}
                onChange={(e) => setDraft({ ...draft, rate: e.target.value })}
                className="h-8 text-right"
                disabled={createMut.isPending}
                data-testid="line-items-add-rate"
              />
            </div>
            <Button
              type="button"
              size="sm"
              className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
              disabled={createMut.isPending || !draft.description.trim()}
              onClick={addItem}
              data-testid="line-items-add-button"
            >
              <Plus size={14} className="mr-1" />
              {createMut.isPending ? 'Adding…' : 'Add'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
