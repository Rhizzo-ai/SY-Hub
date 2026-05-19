/**
 * BudgetGridMobileReadOnly — Chat 23 R8 (stub, lands fully in R8).
 *
 * Mobile users get a read-only card list instead of the desktop grid.
 * For R3 this is a minimal placeholder that shows the budget summary +
 * a banner explaining the read-only treatment. R8 swaps in the full
 * card list.
 */
import { formatMoney } from '@/lib/format';

export function BudgetGridMobileReadOnly({ budget }) {
  return (
    <div className="space-y-4" data-testid="bg2-mobile">
      <div className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600">
        Read-only on mobile. Open on a desktop to edit.
      </div>
      <div className="space-y-3">
        {(budget.lines ?? []).map((line) => (
          <div
            key={line.id}
            className="rounded-lg border border-slate-200 bg-white p-3 text-sm"
            data-testid={`bg2-mobile-line-${line.id}`}
          >
            <div className="font-medium text-slate-900">
              {line.line_description ?? 'Untitled line'}
            </div>
            <div className="mt-1 grid grid-cols-2 gap-1 text-xs text-slate-600">
              <span>Current:</span>
              <span className="text-right font-mono">{formatMoney(line.current_budget)}</span>
              <span>Variance:</span>
              <span className="text-right font-mono">{formatMoney(line.variance_value)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
