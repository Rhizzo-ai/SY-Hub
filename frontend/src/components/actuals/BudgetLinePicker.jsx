/**
 * BudgetLinePicker (Chat 19B §R3.1).
 *
 * Per Q4 / D25: thin wrapper around the project's current budget. Selects
 * a `budget_line_id` directly (the Actuals API requires a line, not a
 * cost-code).
 *
 * Two queries:
 *   1. `useProjectBudgets`  — list summary, no `lines` field
 *   2. `useBudget(currentBudget.id)` — detail with `lines`, gated by
 *      `enabled: !!currentBudget.id`. Both share QueryClient cache with the
 *      ActualsList page (no duplicate network traffic).
 *
 * Empty / no-budget states render a tight amber hint.
 */
import { useMemo } from 'react';
import { useProjectBudgets, useBudget } from '@/hooks/budgets';

export function BudgetLinePicker({ projectId, value, onChange, error, disabled }) {
  const { data: listData, isLoading: listLoading } = useProjectBudgets(projectId);

  const currentBudget = useMemo(() => {
    const items = listData?.items ?? [];
    return (
      items.find((b) => b.is_current && (b.status === 'Active' || b.status === 'Locked')) ||
      items.find((b) => b.status === 'Active') ||
      items.find((b) => b.status === 'Locked') ||
      null
    );
  }, [listData]);

  const { data: detail, isLoading: detailLoading } = useBudget(
    currentBudget?.id,
    { enabled: !!currentBudget?.id },
  );

  const lines = detail?.lines ?? [];
  const isLoading = listLoading || (currentBudget && detailLoading);

  if (isLoading) {
    return (
      <div className="text-sm text-slate-500" data-testid="budget-line-picker-loading">
        Loading budget lines…
      </div>
    );
  }

  if (!currentBudget || lines.length === 0) {
    return (
      <div
        data-testid="budget-line-picker-empty"
        className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
      >
        No active or locked budget on this project. Create or activate a budget
        before posting actuals.
      </div>
    );
  }

  return (
    <div data-testid="budget-line-picker">
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={disabled}
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-sy-teal focus:outline-none focus:ring-2 focus:ring-sy-teal"
      >
        <option value="">Select a budget line…</option>
        {lines.map((line) => (
          <option key={line.id} value={line.id}>
            {line.display_order ? `${line.display_order}. ` : ''}
            {line.line_description ?? '(unnamed)'}
          </option>
        ))}
      </select>
      {error && (
        <p className="mt-1 text-sm text-rose-600" data-testid="budget-line-picker-error">
          {error}
        </p>
      )}
    </div>
  );
}
