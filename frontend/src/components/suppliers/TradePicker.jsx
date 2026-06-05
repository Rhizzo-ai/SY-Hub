/**
 * <TradePicker/> — Chat 41 §R2 (Build Pack 2.7-FE-revision).
 *
 * Grow-as-you-type combobox over the trade vocabulary. Built on
 * @/components/ui/command + @/components/ui/popover (both confirmed
 * present).
 *
 * §R2 DECISION — filter CLIENT-SIDE. Trades are a small vocabulary
 *   (tens, not thousands). We fetch the full live list once
 *   (`include_archived:false`) and filter in-memory by the typed text.
 *   Simpler, no debounce race, instant. The server `q` param stays
 *   available but unused here.
 *
 * §R2 NOTE — archived trades:
 *   The pick-list hides archived (we send `include_archived:false`),
 *   but an existing supplier whose stored `trade` is archived must
 *   still DISPLAY on detail/list. That display reads from the
 *   supplier row, independent of the picker — so unaffected.
 *
 * Canonical-name rule:
 *   The backend POST /v1/trades is idempotent + case-insensitive
 *   (a "groundworks" submit when "Groundworks" exists resolves to the
 *   existing row). The picker MUST therefore reflect the returned
 *   row's `name`, not the typed casing.
 *
 * Permission gate:
 *   The "Add" affordance is HIDDEN (not disabled-with-error) for users
 *   without `trades.create`. A user with `trades.view` only can pick
 *   existing trades but cannot add new ones.
 */
import React, { useMemo, useState } from 'react';
import { ChevronsUpDown, Plus } from 'lucide-react';

import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/ui/command';
import {
  Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';
import { useAuth } from '@/context/AuthContext';
import { useTrades, useCreateTrade } from '@/hooks/trades';
import { canCreateTrades } from '@/lib/poCapability';

export default function TradePicker({
  value = '',
  onChange,
  disabled = false,
  testid = 'trade-picker',
}) {
  const { me } = useAuth();
  const allowAdd = canCreateTrades(me);

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');

  const { data } = useTrades({ params: { include_archived: false } });
  const items = useMemo(() => data?.items ?? [], [data]);
  const createTrade = useCreateTrade();

  const typed = query.trim();
  const lowered = typed.toLowerCase();

  // Client-side filter (substring, case-insensitive). When the typed
  // text is empty, show the whole list.
  const filtered = useMemo(() => {
    if (!lowered) return items;
    return items.filter((t) => (t.name || '').toLowerCase().includes(lowered));
  }, [items, lowered]);

  // Case-insensitive canonical match: if the typed text exactly equals
  // an existing trade name (any casing), we hide the "Add" affordance
  // — selecting the existing item is the right outcome.
  const exactMatch = useMemo(() => {
    if (!lowered) return null;
    return items.find((t) => (t.name || '').toLowerCase() === lowered) ?? null;
  }, [items, lowered]);

  const showAddItem = allowAdd && typed.length > 0 && !exactMatch;

  const closeAndReset = () => {
    setOpen(false);
    setQuery('');
  };

  const selectExisting = (name) => {
    onChange?.(name);
    closeAndReset();
  };

  const clear = () => {
    onChange?.('');
    closeAndReset();
  };

  const addTyped = async () => {
    const name = typed;
    if (!name) return;
    try {
      const created = await createTrade.mutateAsync(name);
      // Use the backend's canonical `name` (handles the case-insensitive
      // get-or-create — typed "electrician" when "Electrician" exists
      // returns the existing row, and we reflect THAT casing).
      onChange?.(created?.name ?? name);
      closeAndReset();
    } catch {
      // Surface nothing here — the parent form's onSubmit will surface
      // a 422 when the backend rejects (the picker stays open so the
      // user can re-type). Silent failure on the create is acceptable
      // because the picker re-renders with the disabled state.
    }
  };

  const label = value || 'Select trade…';

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className="w-full inline-flex items-center justify-between gap-2 px-2 py-1 border rounded text-sm bg-white disabled:opacity-50"
          data-testid={`${testid}-trigger`}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <span className={value ? '' : 'text-sy-grey-500'}>{label}</span>
          <ChevronsUpDown size={14} className="text-sy-grey-500" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="p-0 w-[--radix-popover-trigger-width] min-w-[240px]"
        data-testid={`${testid}-content`}
      >
        <Command shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Type to search or add…"
            data-testid={`${testid}-input`}
          />
          <CommandList>
            <CommandEmpty data-testid={`${testid}-empty`}>
              {allowAdd ? 'Type to add a new trade.' : 'No trades match.'}
            </CommandEmpty>
            <CommandGroup>
              <CommandItem
                value="__none__"
                onSelect={clear}
                data-testid={`${testid}-clear`}
              >
                <span className="text-sy-grey-500">— None —</span>
              </CommandItem>
              {filtered.map((t) => (
                <CommandItem
                  key={t.id}
                  value={t.name}
                  onSelect={() => selectExisting(t.name)}
                  data-testid={`${testid}-option-${t.id}`}
                >
                  {t.name}
                </CommandItem>
              ))}
              {showAddItem && (
                <CommandItem
                  value={`__add__${typed}`}
                  onSelect={addTyped}
                  disabled={createTrade.isPending}
                  data-testid={`${testid}-add`}
                >
                  <Plus size={14} className="mr-1" />
                  <span>Add &quot;{typed}&quot;</span>
                </CommandItem>
              )}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
