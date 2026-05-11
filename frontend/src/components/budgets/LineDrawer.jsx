/**
 * LineDrawer — Prompt 2.4B-i §R7 (placeholder for R6 to ship standalone).
 *
 * Renders a shadcn Sheet with a placeholder body when a row's overflow
 * menu fires "Open line drawer". §R7 fills in:
 *   - rhf + Zod form (line_description, notes, percentage_complete,
 *     ftc_method, forecast_to_complete, cost_code_id +
 *     cost_code_subcategory_id)
 *   - explicit Save with dirtyFields-only PATCH body
 *   - refetch-on-save + `updated_at` mismatch banner (E9)
 *   - LineItemsPanel sub-list
 *   - CostCodePicker (D13 / E5)
 *   - close-with-dirty confirm
 *
 * For now this exists so the grid's onOpenDrawer wiring is testable
 * end-to-end against a real shadcn Sheet.
 */
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet';

export function LineDrawer({ budget, lineId, focus, onClose, projectId }) {
  const open = !!lineId;
  const line = budget?.lines?.find((l) => l.id === lineId) ?? null;

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose?.(); }}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-xl"
        data-testid="line-drawer"
      >
        <SheetHeader>
          <SheetTitle>
            Line — {line?.line_description ?? 'Untitled'}
          </SheetTitle>
          <SheetDescription>
            Drawer form + items panel land in §R7. Focus: {focus ?? 'default'}.
          </SheetDescription>
        </SheetHeader>

        <div
          data-testid="line-drawer-placeholder"
          className="mt-6 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-500"
        >
          <p className="font-medium text-slate-700">
            §R7 LineDrawer — coming next
          </p>
          <ul className="mt-2 list-disc pl-5 text-xs">
            <li>line_description, notes, % complete (rhf + Zod)</li>
            <li>FTC method + value, forecast_to_complete</li>
            <li>Cost-code picker (D13)</li>
            <li>Items sub-list with CRUD</li>
            <li>Refetch-on-save + updated_at mismatch banner (E9)</li>
          </ul>
          {line && (
            <pre className="mt-3 overflow-x-auto rounded bg-white p-2 text-xs text-slate-600">
{JSON.stringify({
  id: line.id,
  cost_code_id: line.cost_code_id,
  original_budget: line.original_budget,
  current_budget: line.current_budget,
  forecast_to_complete: line.forecast_to_complete,
  ftc_method: line.ftc_method,
  updated_at: line.updated_at,
  items_count: line.items?.length ?? 0,
}, null, 2)}
            </pre>
          )}
        </div>
        {/* projectId reserved for §R7 cost-code picker; intentionally unused here. */}
        <input type="hidden" data-testid="line-drawer-project-id" value={projectId ?? ''} readOnly />
      </SheetContent>
    </Sheet>
  );
}
