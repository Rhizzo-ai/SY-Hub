/**
 * SortableLineRow — Prompt 2.4B-i §R6.2.
 *
 * One row in the budget-lines grid. Two responsibilities:
 *   1. Render the line in its current state (with sensitive-field guards
 *      → "—" when omitted via Zod's nullable+optional).
 *   2. Allow inline edit of `line_description` and `percentage_complete`
 *      with optimistic UI (rollback on error handled by the hook).
 *
 * Drag-handle wiring (C8/C9): `setActivatorNodeRef` is given to the grip
 * <button> so screen-readers focus the activator (not the whole row).
 * `attributes` + `listeners` only apply to the handle.
 *
 * E7 field rename map respected throughout:
 *   line_description     (NOT description)
 *   display_order        (NOT position)
 *   actuals_to_date      (sensitive)
 *   committed_not_invoiced (sensitive)
 *   forecast_to_complete   (always returned at line level)
 *   forecast_final_cost  (sensitive)
 *   variance_value, variance_pct (sensitive)
 *   variance_status      (always returned)
 *
 * E8: perm gate is `budgets.edit` (passed in via `inlineEditEnabled`).
 *
 * Sensitive renders: `formatMoney(undefined)` returns "—" already; we
 * don't need a separate branch — the schema's `.optional()` lets the
 * field be absent without exploding.
 */
import { useState } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, MoreHorizontal } from 'lucide-react';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { VarianceBadge } from './VarianceBadge';
import { formatMoney, formatPercent } from '@/lib/format';
import { usePatchBudgetLine } from '@/hooks/budgets';
import { isBudgetEditable } from '@/lib/budgetCapability';

export function SortableLineRow({
  line, budget, onOpenDrawer,
  dragDisabled, inlineEditEnabled, costCodeMap,
}) {
  const patchMut = usePatchBudgetLine(budget.id);

  const {
    attributes, listeners, setNodeRef, setActivatorNodeRef,
    transform, transition, isDragging,
  } = useSortable({ id: line.id, disabled: dragDisabled });

  const [editingDesc, setEditingDesc] = useState(false);
  const [draftDesc, setDraftDesc] = useState(line.line_description ?? '');
  const [editingPct, setEditingPct] = useState(false);
  const [draftPct, setDraftPct] = useState(
    line.percentage_complete == null ? '' : String(line.percentage_complete),
  );

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const canInlineEdit = inlineEditEnabled && isBudgetEditable(budget.status);

  // H7: commit functions guard against double-fire (Enter + onBlur).
  // E9: no `version` field — server arbitrates via updated_at on next refetch.
  function commitDesc() {
    if (!editingDesc) return;
    setEditingDesc(false);
    const next = draftDesc.trim() === '' ? null : draftDesc;
    if (next === (line.line_description ?? null)) return;
    patchMut.mutate({ lineId: line.id, body: { line_description: next } });
  }

  function commitPct() {
    if (!editingPct) return;
    setEditingPct(false);
    const trimmed = draftPct.trim();
    const n = trimmed === '' ? null : Number(trimmed);
    if (n === (line.percentage_complete ?? null)) return;
    if (n != null && (Number.isNaN(n) || n < 0 || n > 100)) {
      // Reject + revert draft. Do not call mutate.
      setDraftPct(line.percentage_complete == null
        ? '' : String(line.percentage_complete));
      return;
    }
    patchMut.mutate({ lineId: line.id, body: { percentage_complete: n } });
  }

  // B1 fix: re-sync drafts when entering edit mode so a second edit
  // after a save doesn't show stale text.
  function startEditDesc() {
    if (!canInlineEdit) return;
    setDraftDesc(line.line_description ?? '');
    setEditingDesc(true);
  }
  function startEditPct() {
    if (!canInlineEdit) return;
    setDraftPct(line.percentage_complete == null
      ? '' : String(line.percentage_complete));
    setEditingPct(true);
  }

  // Cost-code label — join client-side via the map passed by the grid.
  // Backend returns `cost_code_id` only (E7). Falls back to a 6-char
  // suffix if the cost code is not in the project's enabled list.
  const cc = costCodeMap?.get(line.cost_code_id);
  const costCodeLabel = cc
    ? (cc.code || cc.label || line.cost_code_id.slice(-6))
    : line.cost_code_id.slice(-6);

  return (
    <tr
      ref={setNodeRef}
      style={style}
      className="border-t border-slate-100 hover:bg-slate-50"
      data-testid={`budget-line-row-${line.id}`}
    >
      <td className="w-8 px-2">
        {!dragDisabled && (
          <button
            ref={setActivatorNodeRef}
            {...attributes}
            {...listeners}
            type="button"
            className="cursor-grab text-slate-400 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sy-teal rounded"
            aria-label={`Drag to reorder line ${costCodeLabel}`}
            data-testid={`budget-line-drag-${line.id}`}
          >
            <GripVertical size={16} />
          </button>
        )}
      </td>

      <td
        className="px-3 py-2 font-mono text-xs text-slate-600"
        data-testid={`budget-line-cost-code-${line.id}`}
      >
        {costCodeLabel}
      </td>

      <td className="px-3 py-2">
        {editingDesc && canInlineEdit ? (
          <Input
            autoFocus
            value={draftDesc}
            onChange={(e) => setDraftDesc(e.target.value)}
            onBlur={commitDesc}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                commitDesc();
              } else if (e.key === 'Escape') {
                e.preventDefault();
                setDraftDesc(line.line_description ?? '');
                setEditingDesc(false);
              }
            }}
            className="h-7 text-sm"
            disabled={patchMut.isPending}
            data-testid={`budget-line-desc-input-${line.id}`}
          />
        ) : (
          <span
            className={canInlineEdit ? 'cursor-text' : ''}
            onClick={startEditDesc}
            data-testid={`budget-line-desc-${line.id}`}
          >
            {line.line_description ? (
              line.line_description
            ) : canInlineEdit ? (
              <em className="text-slate-400">Click to add description</em>
            ) : (
              <span className="text-slate-400">—</span>
            )}
          </span>
        )}
      </td>

      <td className="px-3 py-2 text-right font-mono">
        {formatMoney(line.original_budget)}
      </td>
      <td className="px-3 py-2 text-right font-mono">
        {formatMoney(line.current_budget)}
      </td>
      <td className="px-3 py-2 text-right font-mono">
        {formatMoney(line.actuals_to_date)}
      </td>
      <td className="px-3 py-2 text-right font-mono">
        {formatMoney(line.committed_not_invoiced)}
      </td>
      <td className="px-3 py-2 text-right font-mono">
        {formatMoney(line.forecast_to_complete)}
      </td>
      <td className="px-3 py-2 text-right font-mono">
        {formatMoney(line.forecast_final_cost)}
      </td>

      <td className="px-3 py-2">
        <VarianceBadge
          status={line.variance_status}
          value={line.variance_value}
          pct={line.variance_pct}
        />
      </td>

      <td className="px-3 py-2 w-24">
        {editingPct && canInlineEdit ? (
          <Input
            type="number"
            min={0}
            max={100}
            step={1}
            autoFocus
            value={draftPct}
            onChange={(e) => setDraftPct(e.target.value)}
            onBlur={commitPct}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                commitPct();
              } else if (e.key === 'Escape') {
                e.preventDefault();
                setDraftPct(line.percentage_complete == null
                  ? '' : String(line.percentage_complete));
                setEditingPct(false);
              }
            }}
            className="h-7 text-sm"
            disabled={patchMut.isPending}
            data-testid={`budget-line-pct-input-${line.id}`}
          />
        ) : (
          <span
            className={`tabular-nums ${canInlineEdit ? 'cursor-text' : ''}`}
            onClick={startEditPct}
            data-testid={`budget-line-pct-${line.id}`}
          >
            {formatPercent(line.percentage_complete)}
          </span>
        )}
      </td>

      <td className="w-8 px-2">
        <DropdownMenu>
          <DropdownMenuTrigger
            className="text-slate-400 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sy-teal rounded"
            aria-label="Line actions"
            data-testid={`budget-line-menu-${line.id}`}
          >
            <MoreHorizontal size={16} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={() => onOpenDrawer(line.id)}
              data-testid={`budget-line-menu-open-${line.id}`}
            >
              Open line drawer
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={!isBudgetEditable(budget.status) || !inlineEditEnabled}
              onClick={() => onOpenDrawer(line.id, { focus: 'items' })}
              data-testid={`budget-line-menu-items-${line.id}`}
            >
              Edit items ({line.items?.length ?? 0})
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </td>
    </tr>
  );
}
