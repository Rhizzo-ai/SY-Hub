/**
 * BudgetHeader — Prompt 2.4B-i §R5.2.
 *
 * Identity (version + status), 5 totals tiles (per backend schema E7),
 * variance row, and LifecycleActions.
 *
 * Sensitive figures (`total_actuals`, `total_committed_not_invoiced`,
 * `total_forecast_to_complete`, `forecast_final_cost`, `variance_vs_budget`,
 * `variance_pct`) are `.optional()` in the Zod schema. `formatMoney`
 * already renders "—" for null/undefined.
 *
 * No `superseded_by_id` exists on the backend payload (E7) — version
 * lineage is implied by `is_current=false`. Closing tag preserved
 * for future routes.
 */
import { StatusBadge } from './StatusBadge';
import { VarianceBadge, deriveVarianceStatus } from './VarianceBadge';
import { LifecycleActions } from './LifecycleActions';
import { formatMoney, formatPercent, formatDateTime } from '@/lib/format';

export function BudgetHeader({ budget, projectId }) {
  const tiles = [
    { key: 'total_budget',                       label: 'Total Budget',  value: budget.total_budget,                       hint: 'Project-level current budget (sum of line current budgets).' },
    { key: 'total_actuals',                      label: 'Actuals',       value: budget.total_actuals,                      hint: 'Total invoiced spend to date (sensitive).' },
    { key: 'total_committed_not_invoiced',       label: 'CNI',           value: budget.total_committed_not_invoiced,       hint: 'Committed not yet invoiced (sensitive).' },
    { key: 'total_forecast_to_complete',         label: 'FTC',           value: budget.total_forecast_to_complete,         hint: 'Forecast to complete (sensitive).' },
    { key: 'forecast_final_cost',                label: 'FFC',           value: budget.forecast_final_cost,                hint: 'Forecast final cost (sensitive).' },
  ];

  const varianceStatus = deriveVarianceStatus(budget.variance_pct);

  return (
    <div className="space-y-4" data-testid="budget-header">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1
              data-testid="budget-header-title"
              className="text-2xl font-semibold text-slate-900"
            >
              Budget v{budget.version_number}
            </h1>
            {budget.version_label && (
              <span className="text-sm text-slate-500">
                · {budget.version_label}
              </span>
            )}
            <StatusBadge status={budget.status} />
            {budget.is_current && (
              <span
                className="text-xs font-medium text-emerald-700"
                data-testid="budget-header-current"
              >
                ● Current
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500">
            {budget.summary_refreshed_at
              ? `Totals refreshed ${formatDateTime(budget.summary_refreshed_at)}`
              : 'Totals not yet refreshed.'}
          </p>
        </div>
        <LifecycleActions budget={budget} projectId={projectId} />
      </div>

      <div
        data-testid="budget-tiles"
        className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5"
      >
        {tiles.map((t) => (
          <div
            key={t.key}
            data-testid={`budget-tile-${t.key}`}
            className="rounded-lg border border-slate-200 bg-white p-3"
            title={t.hint}
          >
            <div className="text-xs uppercase tracking-wide text-slate-500">
              {t.label}
            </div>
            <div className="mt-1 font-mono text-lg text-slate-900">
              {formatMoney(t.value)}
            </div>
          </div>
        ))}
      </div>

      <div
        data-testid="budget-variance-row"
        className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-3"
      >
        <span className="text-xs uppercase tracking-wide text-slate-500">
          Variance (FFC − Budget)
        </span>
        <span
          className="font-mono text-lg text-slate-900"
          data-testid="budget-variance-value"
        >
          {budget.variance_vs_budget == null
            ? '—'
            : formatMoney(budget.variance_vs_budget)}
        </span>
        <span className="text-sm text-slate-500"
              data-testid="budget-variance-pct">
          {formatPercent(budget.variance_pct)}
        </span>
        <VarianceBadge
          status={varianceStatus}
          value={budget.variance_vs_budget}
          pct={budget.variance_pct}
        />
      </div>
    </div>
  );
}
