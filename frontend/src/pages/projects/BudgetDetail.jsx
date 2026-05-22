/**
 * BudgetDetail — Prompt 2.4B-i §R5.7 + Chat 23 §R3 (BudgetGridV2).
 *
 * Shell for the per-budget detail page. Renders:
 *   - breadcrumb + header (BudgetHeader)
 *   - SensitiveBanner when user lacks budgets.view_sensitive
 *   - BudgetGridV2 (Chat 23 R3 replacement for v1's BudgetLinesGrid)
 *
 * Hooks-first ordering preserved (Rules of Hooks).
 */
import { useEffect } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useBudget } from '@/hooks/budgets';
import { BudgetHeader } from '@/components/budgets/BudgetHeader';
import { SensitiveBanner } from '@/components/budgets/SensitiveBanner';
import { BudgetGridV2 } from '@/components/budgets/grid/BudgetGridV2';

export default function BudgetDetail() {
  const { projectId, budgetId } = useParams();
  const { me } = useAuth();
  const canView = !!me?.permissions?.includes('budgets.view');

  // R6 — Legacy deep-link redirect: pre-R6 share links used `?line=` or
  // `?drilldown=` to deep-link into a single line's drilldown panel.
  // Rewrite those into `?expanded=` (the R6 URL contract) using
  // `router.replace` so we don't pollute history.
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    const legacy = searchParams.get('line') ?? searchParams.get('drilldown');
    if (!legacy || searchParams.get('expanded')) return;
    const next = new URLSearchParams(searchParams);
    next.set('expanded', legacy);
    next.delete('line');
    next.delete('drilldown');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

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
          <BudgetGridV2 budget={budget} projectId={projectId} />
        </>
      ) : null}
    </div>
  );
}
