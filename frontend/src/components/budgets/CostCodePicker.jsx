/**
 * CostCodePicker — B107 §7 (was a shadcn Select; now a type-to-search
 * combobox).
 *
 * Grow-as-you-type combobox over the project's cost-code list, built on
 * @/components/ui/command + @/components/ui/popover (the same pattern as
 * <TradePicker/>). Filters CLIENT-SIDE over the already-fetched
 * `useCostCodes` list — matching on BOTH `code` and `name` (typing
 * "ground" surfaces "1500 — Groundworks").
 *
 * §0.4 TRAP (already solved here): `useCostCodes` returns
 * `ProjectCostCodeRead` rows whose `id` is the project_cost_codes mapping
 * row id. `budget_lines.cost_code_id` references the underlying
 * `cost_codes.id` — exposed as the row's `cost_code_id` field. The picker
 * MUST key on / emit `cost_code_id`, NEVER `id`.
 *
 * Value contract unchanged from the Select era: value in / value out is a
 * `cost_code_id`. Disabled (`is_enabled=false`) codes are hidden UNLESS
 * they are the current value (so the picker never silently loses state).
 */
import React, { useMemo, useState } from 'react';
import { ChevronsUpDown } from 'lucide-react';

// B107 FIX 1 — install the ResizeObserver loop guard (side-effect import).
// Radix Popover + cmdk below drive the benign "ResizeObserver loop …"
// notice that CRA escalates into a red overlay; this defers the observer
// callback to the next frame so the loop never occurs. See the util for
// the full rationale.
import '@/lib/resizeObserverFix';

import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command';
import {
  Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';
import { useCostCodes } from '@/hooks/costCodes';

export function CostCodePicker({
  projectId, value, onChange, disabled, testid = 'cost-code-picker',
}) {
  const { data: codes = [], isLoading } = useCostCodes(projectId);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const selected = codes.find((c) => c.cost_code_id === value);
  const selectedLabel = selected
    ? `${selected.code} — ${selected.name}`
    : value ? `Code ${String(value).slice(-6)}` : null;

  const lowered = query.trim().toLowerCase();
  const options = useMemo(() => (
    codes
      .filter((c) => c.is_enabled || c.cost_code_id === value)
      .filter((c) => {
        if (!lowered) return true;
        const hay = `${c.code ?? ''} ${c.name ?? ''}`.toLowerCase();
        return hay.includes(lowered);
      })
  ), [codes, value, lowered]);

  const choose = (ccId) => {
    onChange?.(ccId);
    setOpen(false);
    setQuery('');
  };

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQuery(''); }}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled || isLoading}
          className="w-full inline-flex items-center justify-between gap-2 px-2 py-1 border rounded text-sm bg-white disabled:opacity-50"
          data-testid={`${testid}-trigger`}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <span className={selectedLabel ? 'truncate' : 'truncate text-slate-500'}>
            {isLoading ? 'Loading cost codes…' : (selectedLabel ?? 'Select a cost code')}
          </span>
          <ChevronsUpDown size={14} className="shrink-0 text-slate-500" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="p-0 w-[--radix-popover-trigger-width] min-w-[260px]"
        data-testid={`${testid}-content`}
      >
        <Command shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Search code or name…"
            data-testid={`${testid}-search`}
          />
          <CommandList>
            <CommandEmpty data-testid={`${testid}-empty`}>
              No cost codes match.
            </CommandEmpty>
            <CommandGroup>
              {options.map((c) => (
                <CommandItem
                  key={c.cost_code_id}
                  value={`${c.code} ${c.name} ${c.cost_code_id}`}
                  onSelect={() => choose(c.cost_code_id)}
                  data-testid={`cost-code-option-${c.cost_code_id}`}
                >
                  <span className="mr-2 font-mono text-xs">{c.code}</span>
                  <span className="truncate">{c.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

export default CostCodePicker;
