/**
 * CostCodePicker — Prompt 2.4B-i §R7.3.
 *
 * shadcn Select wrapping the project's cost-code list. Filters to
 * `enabled` codes but always keeps the currently-selected code visible
 * even if it's been disabled (so the picker doesn't silently lose state
 * when an admin disables a code mid-edit).
 *
 * D13 / E5: `useCostCodes(projectId)` from `hooks/costCodes.js`.
 * Backend returns `{ id, code, label, enabled }` per row — we render
 * "<code> — <label>" in each option.
 *
 * Loading: shows "Loading cost codes…" placeholder while fetch is
 * in-flight. Missing-label fallback: "Code <last-6>" (matches §R6 grid).
 */
import { useCostCodes } from '@/hooks/costCodes';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

export function CostCodePicker({ projectId, value, onChange, disabled }) {
  const { data: codes = [], isLoading } = useCostCodes(projectId);
  const selected = codes.find((c) => c.id === value);
  const selectedLabel = selected
    ? `${selected.code} — ${selected.label}`
    : value ? `Code ${value.slice(-6)}` : null;

  return (
    <Select
      value={value || ''}
      onValueChange={onChange}
      disabled={disabled || isLoading}
    >
      <SelectTrigger data-testid="cost-code-picker-trigger">
        <SelectValue
          placeholder={
            isLoading
              ? 'Loading cost codes…'
              : selectedLabel ?? 'Select a cost code'
          }
        />
      </SelectTrigger>
      <SelectContent>
        {codes
          .filter((c) => c.enabled || c.id === value)
          .map((c) => (
            <SelectItem
              key={c.id}
              value={c.id}
              data-testid={`cost-code-option-${c.id}`}
            >
              {`${c.code} — ${c.label}`}
            </SelectItem>
          ))}
      </SelectContent>
    </Select>
  );
}
