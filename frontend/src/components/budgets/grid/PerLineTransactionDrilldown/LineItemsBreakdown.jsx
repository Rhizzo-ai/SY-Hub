/**
 * LineItemsBreakdown — Chat 23 R4.1.
 *
 * Renders the line's `budget_line_items` (the 4 defaults from R1.2 plus
 * any user-added items). Editable inline on desktop when `canEdit`,
 * read-only otherwise.
 *
 * Editable fields per row: description, amount, notes.
 * Row actions: Delete (asks confirmation if amount > 0 or notes
 * present). Bottom action: "+ Add item".
 *
 * Source of truth = `line.items` from the budget-detail response.
 * Mutations invalidate the parent budget cache so totals recompute on
 * the next render.
 */
import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import {
  useCreateLineItem, usePatchLineItem, useDeleteLineItem,
} from '@/hooks/budgets';
import { formatMoney } from '@/lib/format';

function ItemRow({ item, lineId, budgetId, canEdit }) {
  const [descDraft, setDescDraft] = useState(item.description ?? '');
  const [amtDraft, setAmtDraft] = useState(String(item.amount ?? '0'));
  const [notesDraft, setNotesDraft] = useState(item.notes ?? '');
  const [confirmDelete, setConfirmDelete] = useState(false);

  const patchMut = usePatchLineItem(lineId, budgetId);
  const deleteMut = useDeleteLineItem(lineId, budgetId);

  function commit(field, raw) {
    const original = item[field] ?? '';
    const nextRaw = raw?.trim() === '' && field !== 'amount' ? null : raw;
    if (String(nextRaw ?? '') === String(original ?? '')) return;
    patchMut.mutate({ itemId: item.id, body: { [field]: nextRaw } });
  }

  function doDelete() {
    const hasContent =
      Number(item.amount ?? 0) > 0 || (item.notes ?? '').trim() !== '';
    if (hasContent && !confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    deleteMut.mutate(item.id);
  }

  if (!canEdit) {
    return (
      <tr className="border-t border-slate-100" data-testid={`bg2-item-${item.id}`}>
        <td className="px-2 py-1 text-slate-700">{item.description ?? '—'}</td>
        <td className="px-2 py-1 text-right font-mono tabular-nums">
          {formatMoney(item.amount)}
        </td>
        <td className="px-2 py-1 text-xs text-slate-500" colSpan={2}>
          {item.notes ?? ''}
        </td>
      </tr>
    );
  }

  return (
    <tr
      className="border-t border-slate-100"
      data-testid={`bg2-item-row-${item.id}`}
    >
      <td className="px-2 py-1">
        <Input
          value={descDraft}
          onChange={(e) => setDescDraft(e.target.value)}
          onBlur={() => commit('description', descDraft)}
          className="h-7 text-sm"
          data-testid={`bg2-item-desc-${item.id}`}
        />
      </td>
      <td className="px-2 py-1">
        <Input
          value={amtDraft}
          onChange={(e) => setAmtDraft(e.target.value)}
          onBlur={() => commit('amount', amtDraft)}
          inputMode="decimal"
          className="h-7 text-right font-mono tabular-nums text-sm"
          data-testid={`bg2-item-amt-${item.id}`}
        />
      </td>
      <td className="px-2 py-1">
        <Input
          value={notesDraft}
          onChange={(e) => setNotesDraft(e.target.value)}
          onBlur={() => commit('notes', notesDraft)}
          className="h-7 text-sm"
          placeholder="Notes"
          data-testid={`bg2-item-notes-${item.id}`}
        />
      </td>
      <td className="px-2 py-1 text-right">
        <button
          type="button"
          onClick={doDelete}
          disabled={deleteMut.isPending}
          className={`inline-flex items-center gap-1 rounded p-1 text-xs ${
            confirmDelete
              ? 'bg-sy-orange text-white hover:bg-sy-orange/90'
              : 'text-slate-500 hover:text-rose-600'
          }`}
          aria-label={confirmDelete ? 'Confirm delete item' : 'Delete item'}
          data-testid={`bg2-item-delete-${item.id}`}
        >
          <Trash2 size={12} />
          {confirmDelete && <span>Confirm?</span>}
        </button>
      </td>
    </tr>
  );
}

export function LineItemsBreakdown({ line, budget, canEdit }) {
  const items = line?.items ?? [];
  const createMut = useCreateLineItem(line.id, budget.id);

  function addItem() {
    createMut.mutate({
      description: 'New item',
      amount: '0',
      display_order: items.length,
    });
  }

  return (
    <div data-testid={`bg2-breakdown-${line.id}`}>
      <table className="w-full text-sm">
        <thead className="text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-2 py-1 text-left">Description</th>
            <th className="px-2 py-1 text-right">Amount</th>
            <th className="px-2 py-1 text-left" colSpan={canEdit ? 1 : 2}>
              Notes
            </th>
            {canEdit && <th className="px-2 py-1" />}
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={4} className="p-3 text-center text-xs text-slate-500">
                No items on this line yet.
              </td>
            </tr>
          ) : (
            items.map((it) => (
              <ItemRow
                key={it.id}
                item={it}
                lineId={line.id}
                budgetId={budget.id}
                canEdit={canEdit}
              />
            ))
          )}
        </tbody>
      </table>
      {canEdit && (
        <div className="mt-2">
          <button
            type="button"
            onClick={addItem}
            disabled={createMut.isPending}
            className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
            data-testid={`bg2-item-add-${line.id}`}
          >
            <Plus size={12} /> Add item
          </button>
        </div>
      )}
    </div>
  );
}
