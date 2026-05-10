/**
 * BudgetDetail — Prompt 2.4B-i §R5.7.
 *
 * Shell for the per-budget detail page. Renders:
 *   - breadcrumb + header (BudgetHeader)
 *   - SensitiveBanner when user lacks budgets.view_sensitive
 *   - Placeholder for BudgetLinesGrid (§R6 — lands next pause cycle)
 *
 * Hooks-first ordering preserved (Rules of Hooks).
 */
import { useParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useBudget } from '@/hooks/budgets';
import { BudgetHeader } from '@/components/budgets/BudgetHeader';
import { SensitiveBanner } from '@/components/budgets/SensitiveBanner';

export default function BudgetDetail() {
  const { projectId, budgetId } = useParams();
  const { me } = useAuth();
  const canView = !!me?.permissions?.includes('budgets.view');

  const { data: budget, isLoading, isError, error } = useBudget(budgetId, {
    enabled: canView,
  });

  if (!canView) {
    return (
      <div
        data-testid="budget-detail-no-perm"
        className="m-6 rounded-lg border border-slate-200 bg-slate-50 p-6 text-slate-600"
      >
        You don't have access to budgets.
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <nav
        data-testid="budget-detail-breadcrumb"
        className="text-sm text-slate-600"
      >
        <Link to="/projects" className="hover:underline">Projects</Link>
        <span className="mx-1.5 text-slate-400">/</span>
        <Link to={`/projects/${projectId}`} className="hover:underline">
          Project
        </Link>
        <span className="mx-1.5 text-slate-400">/</span>
        <Link
          to={`/projects/${projectId}/budgets`}
          className="hover:underline"
        >
          Budgets
        </Link>
        <span className="mx-1.5 text-slate-400">/</span>
        <span className="text-slate-900 truncate">
          {budget ? `v${budget.version_number}` : budgetId}
        </span>
      </nav>

      {isLoading ? (
        <div
          data-testid="budget-detail-loading"
          className="rounded-lg border border-slate-200 p-12 text-center text-slate-500"
        >
          Loading budget…
        </div>
      ) : isError ? (
        <div
          data-testid="budget-detail-error"
          className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700"
        >
          Failed to load budget: {error?.message ?? 'Unknown error.'}
        </div>
      ) : budget ? (
        <>
          <BudgetHeader budget={budget} projectId={projectId} />
          <SensitiveBanner />

          {/* §R6 BudgetLinesGrid lands in the next implementation pause. */}
          <div
            data-testid="budget-lines-grid-placeholder"
            className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-12 text-center text-sm text-slate-500"
          >
            <p className="font-medium text-slate-700">
              Budget lines grid (§R6) — coming next
            </p>
            <p className="mt-1 text-xs">
              {budget.lines?.length ?? 0} lines loaded · drag-orderable grid
              and inline edit land in the next implementation cycle.
            </p>
          </div>
        </>
      ) : null}
    </div>
  );
}
