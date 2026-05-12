/**
 * BudgetLinesGrid — Prompt 2.4B-i §R6.3.
 *
 * Parent component for the lines grid:
 *   - dnd-kit DnD with PointerSensor + KeyboardSensor (a11y, C8)
 *   - LineDrawer state (`openLineId`, `drawerFocus`) lifted here
 *   - cost-code map fetched once for label rendering (E7 client-side join)
 *
 * Edit / reorder gating:
 *   dragDisabled       = !editable || !canEdit || reorderMut.isPending
 *   inlineEditEnabled  = canEdit (status check happens inside the row)
 *   canEdit            = budgets.edit + isDesktop  (E8)
 *   editable           = isBudgetEditable(status)  (Draft + Active)
 *
 * `buildReorderedIds` is exported pure-fn for §R8 unit tests (H8).
 */
import { useMemo, useState } from 'react';
import {
  DndContext, closestCenter,
  PointerSensor, KeyboardSensor,
  useSensor, useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { SortableLineRow } from './SortableLineRow';
import { LineDrawer } from './LineDrawer';
import { useReorderBudgetLines } from '@/hooks/budgets';
import { useCostCodes, buildCostCodeMap } from '@/hooks/costCodes';
import { useAuth } from '@/context/AuthContext';
import { useIsDesktop } from '@/lib/useIsDesktop';
import {
  isBudgetEditable, canEditLines,
} from '@/lib/budgetCapability';
import { buildReorderedIds } from '@/lib/buildReorderedIds';

// Re-exported for back-compat with §R6 imports.
export { buildReorderedIds };

export function BudgetLinesGrid({ budget, projectId }) {
  const { me } = useAuth();
  const isDesktop = useIsDesktop();
  const canEdit = canEditLines(me, budget.status) && isDesktop;
  const editable = isBudgetEditable(budget.status);

  const [openLineId, setOpenLineId] = useState(null);
  const [drawerFocus, setDrawerFocus] = useState(null);

  const reorderMut = useReorderBudgetLines(budget.id, projectId);
  const { data: costCodes = [] } = useCostCodes(projectId);
  const costCodeMap = useMemo(() => buildCostCodeMap(costCodes), [costCodes]);

  // C8: KeyboardSensor + sortableKeyboardCoordinates for keyboard a11y
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // B3: memoise sorted lines + itemIds so SortableContext receives a
  // stable array identity across renders.
  const lines = useMemo(
    () => (budget.lines ?? [])
      .slice()
      .sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0)),
    [budget.lines],
  );
  const itemIds = useMemo(() => lines.map((l) => l.id), [lines]);

  function handleDragEnd(event) {
    const orderedIds = buildReorderedIds(lines, event);
    if (orderedIds) reorderMut.mutate(orderedIds);
  }

  function openDrawer(lineId, opts = {}) {
    setOpenLineId(lineId);
    setDrawerFocus(opts.focus ?? null);
  }

  const dragDisabled = !editable || !canEdit || reorderMut.isPending;
  const inlineEditEnabled = canEdit;

  return (
    <div className="space-y-3" data-testid="budget-lines-grid">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">Lines</h2>
        <span
          className="text-xs text-slate-500"
          data-testid="budget-lines-count"
        >
          {lines.length} {lines.length === 1 ? 'line' : 'lines'}
        </span>
      </div>

      {!isDesktop && (
        <div
          data-testid="budget-lines-mobile-banner"
          className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600"
        >
          Read-only on mobile.
        </div>
      )}

      {reorderMut.isError && (
        <div
          data-testid="budget-lines-reorder-error"
          className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700"
        >
          Reorder failed — the original order has been restored.
          {' '}
          {reorderMut.error?.message}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <caption className="sr-only">Budget lines</caption>
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="w-8" scope="col" aria-label="Drag handle" />
              <th className="px-3 py-2 text-left" scope="col">Cost Code</th>
              <th className="px-3 py-2 text-left" scope="col">Description</th>
              <th className="px-3 py-2 text-right" scope="col">Original</th>
              <th className="px-3 py-2 text-right" scope="col">Current</th>
              <th className="px-3 py-2 text-right" scope="col">Actuals</th>
              <th className="px-3 py-2 text-right" scope="col">CNI</th>
              <th className="px-3 py-2 text-right" scope="col">FTC</th>
              <th className="px-3 py-2 text-right" scope="col">FFC</th>
              <th className="px-3 py-2 text-left" scope="col">Variance</th>
              <th className="px-3 py-2 text-left" scope="col">% Complete</th>
              <th className="w-8" scope="col" aria-label="Row actions" />
            </tr>
          </thead>

          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={itemIds}
              strategy={verticalListSortingStrategy}
            >
              <tbody>
                {lines.map((line) => (
                  <SortableLineRow
                    key={line.id}
                    line={line}
                    budget={budget}
                    onOpenDrawer={openDrawer}
                    dragDisabled={dragDisabled}
                    inlineEditEnabled={inlineEditEnabled}
                    costCodeMap={costCodeMap}
                  />
                ))}
                {lines.length === 0 && (
                  <tr>
                    <td
                      colSpan={12}
                      className="p-12 text-center text-slate-500"
                      data-testid="budget-lines-empty"
                    >
                      No lines on this budget yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </SortableContext>
          </DndContext>
        </table>
      </div>

      <LineDrawer
        budget={budget}
        projectId={projectId}
        lineId={openLineId}
        focus={drawerFocus}
        onClose={() => { setOpenLineId(null); setDrawerFocus(null); }}
      />
    </div>
  );
}
