/**
 * ColumnVisibilityMenu — toggle column visibility (Chat 23 R3.2/R3.7).
 * Always-on columns (select/expand/cost_code/line_description/actions)
 * are excluded from the toggle list since hiding them would break the
 * grid skeleton.
 */
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent,
  DropdownMenuLabel, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Columns, ChevronDown } from 'lucide-react';

const ALWAYS_ON = new Set(['select', 'expand', 'actions']);
const LABELS = {
  cost_code: 'Cost code',
  line_description: 'Description',
  original_budget: 'Original budget',
  current_budget: 'Current budget',
  pending_changes: 'Pending changes',
  committed: 'Committed',
  actual_spent: 'Actual spent',
  variance_to_budget: 'Variance to budget',
  forecast_cost: 'Forecast cost',
  cost_to_complete: 'Cost to complete',
  variance_to_forecast: 'Variance to forecast',
  forecast_profit: 'Forecast profit',
  forecast_margin_pct: 'Forecast margin %',
  projection_reference: 'Projection reference',
  notes: 'Notes',
};

export function ColumnVisibilityMenu({ table }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        data-testid="bg2-column-visibility-trigger"
      >
        <Columns size={14} /> Columns <ChevronDown size={12} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56 max-h-96 overflow-y-auto">
        <DropdownMenuLabel>Toggle columns</DropdownMenuLabel>
        {table.getAllLeafColumns()
          .filter((c) => !ALWAYS_ON.has(c.id) && c.getCanHide())
          .map((col) => (
            <DropdownMenuCheckboxItem
              key={col.id}
              checked={col.getIsVisible()}
              onCheckedChange={(v) => col.toggleVisibility(Boolean(v))}
              data-testid={`bg2-col-toggle-${col.id}`}
            >
              {LABELS[col.id] ?? col.id}
            </DropdownMenuCheckboxItem>
          ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
