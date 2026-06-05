/**
 * <ColumnPicker/> — Chat 41 §R6 (Build Pack 2.7-FE-revision).
 *
 * Session-only optional-column visibility toggle for the Suppliers
 * list table. Built on @/components/ui/popover.
 *
 * The component is CONTROLLED: parent owns the visible-Set and the
 * options array; toggling fires `onToggle(key)`. Nothing is persisted
 * — closing/reloading the page resets to the defaults.
 *
 * Core columns (Name/Type/Status) are LOCKED and NOT listed here, to
 * keep the popover uncluttered. Per-user persistence is backlog item
 * B-COLS (operator-owned).
 */
import React, { useState } from 'react';
import { Columns3 } from 'lucide-react';

import {
  Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';

export default function ColumnPicker({
  options = [],
  visible,
  onToggle,
  testid = 'supplier-list-column-picker',
}) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 px-2 py-1 border rounded text-sm bg-white"
          data-testid={testid}
          aria-haspopup="dialog"
          aria-expanded={open}
        >
          <Columns3 size={14} className="text-sy-grey-600" />
          <span>Columns</span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-56"
        data-testid={`${testid}-content`}
      >
        <div className="text-xs uppercase tracking-wide text-sy-grey-600 mb-2">
          Optional columns
        </div>
        <ul className="space-y-1.5">
          {options.map((opt) => (
            <li key={opt.key}>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={visible.has(opt.key)}
                  onChange={() => onToggle?.(opt.key)}
                  data-testid={`column-toggle-${opt.key}`}
                />
                <span>{opt.label}</span>
              </label>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
