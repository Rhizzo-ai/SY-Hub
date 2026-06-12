/**
 * CostCodePicker — Prompt 2.4B-i §R7.3.
 *
 * shadcn Select wrapping the project's cost-code list. Filters to
 * `is_enabled` codes but always keeps the currently-selected code
 * visible even if it's been disabled (so the picker doesn't silently
 * lose state when an admin disables a code mid-edit).
 *
 * D13 / E5: `useCostCodes(projectId)` from `hooks/costCodes.js` —
 * returns `ProjectCostCodeRead` rows whose `id` is the
 * `project_cost_codes` mapping row id, NOT the underlying cost code
 * id. `BudgetLine.cost_code_id` references the underlying
 * `cost_codes.id`, so the picker MUST key on `cost_code_id` (not
 * `id`). Backend canonical field names:
 *
 *     id                  — project_cost_codes mapping row id (NOT used here)
 *     cost_code_id        — underlying cost_codes.id (FK target — use THIS)
 *     code                — short code string ("SUB-01")
 *     name                — long label
 *     is_enabled          — enabled-for-this-project flag
 *
 * B88 Pack 2 follow-up (Chat 51, Gate 2 re-eyeball Defect 1):
 *   The legacy picker compared `c.id === value` (wrong column) and
 *   `c.enabled` / `c.label` (wrong field names) — the dropdown was
 *   blank on every edit since inception. Fixed to canonical names.
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
  const selected = codes.find((c) => c.cost_code_id === value);
  const selectedLabel = selected
    ? `${selected.code} — ${selected.name}`
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
          .filter((c) => c.is_enabled || c.cost_code_id === value)
          .map((c) => (
            <SelectItem
              key={c.cost_code_id}
              value={c.cost_code_id}
              data-testid={`cost-code-option-${c.cost_code_id}`}
            >
              {`${c.code} — ${c.name}`}
            </SelectItem>
          ))}
      </SelectContent>
    </Select>
  );
}
