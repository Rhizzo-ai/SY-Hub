/**
 * ViewPresetsDropdown — Chat 23 R3.3 + R6.4 (saved views CRUD).
 *
 * Renders:
 *   - 4 starter presets (Quick / Standard / Full / Profit)
 *     Profit hidden when !canViewSensitive.
 *   - User's saved views (R6) — each can be applied; "Save current
 *     view…" footer opens SaveViewDialog; "Manage saved views…"
 *     opens ManageViewsDialog.
 */
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ChevronDown, Plus, Settings2 } from 'lucide-react';
import { INITIAL_COLUMN_VISIBILITY } from './BudgetGridColumns';

export const VIEW_PRESETS = {
  Quick: {
    visibility: {
      cost_code: true, line_description: true,
      current_budget: true, actual_spent: true,
      variance_to_budget: true, notes: true,
      select: true, expand: true, actions: true,
    },
    columnOrder: [
      'select', 'expand', 'cost_code', 'line_description',
      'current_budget', 'actual_spent', 'variance_to_budget',
      'notes', 'actions',
    ],
    sorting: [],
    filters: {},
  },
  Standard: {
    visibility: INITIAL_COLUMN_VISIBILITY,
    columnOrder: null,
    sorting: [],
    filters: {},
  },
  Full: {
    visibility: Object.fromEntries(
      Object.keys(INITIAL_COLUMN_VISIBILITY).map((k) => [k, true]),
    ),
    columnOrder: null,
    sorting: [],
    filters: {},
  },
  Profit: {
    visibility: {
      cost_code: true, line_description: true,
      current_budget: true, actual_spent: true,
      forecast_cost: true, forecast_profit: true,
      forecast_margin_pct: true, notes: true,
      select: true, expand: true, actions: true,
    },
    columnOrder: [
      'select', 'expand', 'cost_code', 'line_description',
      'current_budget', 'actual_spent', 'forecast_cost',
      'forecast_profit', 'forecast_margin_pct', 'notes', 'actions',
    ],
    sorting: [],
    filters: {},
  },
};

export function ViewPresetsDropdown({
  canViewSensitive, onApplyPreset,
  savedViews = [], onApplyView, onOpenSaveView, onOpenManageViews,
}) {
  const presetNames = ['Quick', 'Standard', 'Full'];
  if (canViewSensitive) presetNames.push('Profit');

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        data-testid="bg2-view-presets-trigger"
      >
        Views <ChevronDown size={14} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Starter presets</DropdownMenuLabel>
        {presetNames.map((name) => (
          <DropdownMenuItem
            key={name}
            onClick={() => onApplyPreset?.(name, VIEW_PRESETS[name])}
            data-testid={`bg2-preset-${name.toLowerCase()}`}
          >
            {name}
          </DropdownMenuItem>
        ))}

        <DropdownMenuSeparator />
        <DropdownMenuLabel>Saved views</DropdownMenuLabel>
        {savedViews.length === 0 ? (
          <DropdownMenuItem
            disabled
            className="text-xs text-slate-400"
            data-testid="bg2-saved-views-empty"
          >
            (none yet)
          </DropdownMenuItem>
        ) : (
          savedViews.map((view) => (
            <DropdownMenuItem
              key={view.id}
              onClick={() => onApplyView?.(view)}
              data-testid={`bg2-saved-view-${view.name}`}
            >
              {view.name}
            </DropdownMenuItem>
          ))
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() => onOpenSaveView?.()}
          data-testid="bg2-open-save-view"
        >
          <Plus size={14} className="mr-2" /> Save current view…
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => onOpenManageViews?.()}
          data-testid="bg2-open-manage-views"
        >
          <Settings2 size={14} className="mr-2" /> Manage saved views…
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
