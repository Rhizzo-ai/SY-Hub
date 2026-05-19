/**
 * Pure handler — originally extracted from the v1 BudgetLinesGrid
 * (§R6.3 H8 fix) so it could be unit-tested with zero
 * React / dnd-kit / shadcn imports.
 *
 * Returns the new ordered id array from a dnd-kit-style DragEndEvent,
 * or `null` when nothing changed.
 *
 * Now consumed by `grid/BudgetGridV2Desktop.jsx::SortableLineRowBody`
 * — the v1 grid was removed in Chat 23 §R10 G38, but this helper
 * remains the single source of truth for the reorder transform.
 */
import { arrayMove } from '@dnd-kit/sortable';

export function buildReorderedIds(lines, event) {
  const { active, over } = event;
  if (!over || active.id === over.id) return null;
  const oldIdx = lines.findIndex((l) => l.id === active.id);
  const newIdx = lines.findIndex((l) => l.id === over.id);
  if (oldIdx < 0 || newIdx < 0) return null;
  return arrayMove(lines, oldIdx, newIdx).map((l) => l.id);
}
