/**
 * Pure handler — extracted from BudgetLinesGrid (§R6.3 H8 fix) so it
 * can be unit-tested with zero React / dnd-kit / shadcn imports.
 *
 * Returns the new ordered id array from a dnd-kit-style DragEndEvent,
 * or `null` when nothing changed.
 *
 * Single source of truth — `BudgetLinesGrid.jsx` re-exports this for
 * back-compat and consumes it directly.
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
