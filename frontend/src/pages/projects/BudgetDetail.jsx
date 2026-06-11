/**
 * BudgetDetail — Prompt 2.4B-i §R5.7 + Chat 23 §R3 + Chat 51 §R7
 * (B88 Pack 2 Job-Costing grid) + Prompt 2.6-FE §R1 (BCR Changes +
 * Change Log tabs).
 *
 * Shell for the per-budget detail page. Renders:
 *   - breadcrumb + header (BudgetHeader)
 *   - SensitiveBanner when user lacks budgets.view_sensitive
 *   - Tabbed body:
 *       lines       — BudgetJobCostingGrid (B88 Pack 2)
 *                     Two screens served by the SAME component:
 *                       * Full Budget — Tier 1 default
 *                       * Construction Budget — Tier 2 default,
 *                         Tier 1 preview via ?scope=construction
 *                     Backend clamps the scope; Tier 2 callers cannot
 *                     widen via the URL.
 *                     The legacy flat grid (BudgetGridV2 +
 *                     BudgetGridV2Desktop + BudgetGridMobileReadOnly)
 *                     is left in the tree, unreferenced; operator
 *                     deprecation decision pending.
 *       changes     — <BudgetChangeQueue/>
 *       change-log  — <BudgetChangeLogPanel/>
 *
 * Tab state is URL-driven via ?tab=. Scope is URL-driven via ?scope=.
 * Hooks-first ordering preserved (Rules of Hooks).
 */
import { useEffect } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useBudget } from '@/hooks/budgets';
import { BudgetHeader } from '@/components/budgets/BudgetHeader';
import { SensitiveBanner } from '@/components/budgets/SensitiveBanner';
import { BudgetJobCostingGrid } from '@/components/budgets/BudgetJobCostingGrid';
import { canViewBCR } from '@/lib/budgetChangeCapability';
import { getBudgetScope } from '@/lib/budgetCapability';
import BudgetChangeQueue
  from '@/components/budgetChanges/BudgetChangeQueue';
import BudgetChangeLogPanel
  from '@/components/budgetChanges/BudgetChangeLogPanel';

const TABS = [
  { key: 'lines',      label: 'Budget lines',  perm: 'budgets.view' },
  { key: 'changes',    label: 'Changes',       perm: 'budget_changes.view' },
  { key: 'change-log', label: 'Change log',    perm: 'budget_changes.view' },
];

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

  const activeTab = searchParams.get('tab') ?? 'lines';
  const setTab = (key) => {
    const next = new URLSearchParams(searchParams);
    if (key === 'lines') next.delete('tab');
    else next.set('tab', key);
    setSearchParams(next, { replace: true });
  };

  const visibleTabs = TABS.filter((t) =>
    me?.permissions?.includes(t.perm),
  );

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

          {/* Tab bar */}
          {visibleTabs.length > 1 ? (
            <div
              className="flex gap-1 border-b border-slate-200"
              data-testid="budget-detail-tabs"
              role="tablist"
            >
              {visibleTabs.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === t.key}
                  onClick={() => setTab(t.key)}
                  className={`relative px-4 py-2 text-sm transition ${
                    activeTab === t.key
                      ? 'font-semibold text-slate-900'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                  data-testid={`budget-detail-tab-${t.key}`}
                >
                  {t.label}
                  {activeTab === t.key ? (
                    <span className="absolute inset-x-2 -bottom-px h-0.5 bg-sy-teal-600" />
                  ) : null}
                </button>
              ))}
            </div>
          ) : null}

          {/* Tab body */}
          {activeTab === 'changes' && canViewBCR(me) ? (
            <div data-testid="budget-detail-tab-body-changes">
              <BudgetChangeQueue budgetId={budgetId} projectId={projectId} />
            </div>
          ) : activeTab === 'change-log' && canViewBCR(me) ? (
            <div data-testid="budget-detail-tab-body-change-log">
              <BudgetChangeLogPanel budgetId={budgetId} />
            </div>
          ) : (
            <div data-testid="budget-detail-tab-body-lines">
              {/* B88 Pack 2 (Chat 51) — Job-Costing grouped grid.
                  ?scope=construction lets a Tier-1 user preview the
                  Construction Budget; backend clamps Tier 2 callers. */}
              <div className="mb-3 flex items-center gap-2">
                {getBudgetScope(me) === 'full' ? (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        const next = new URLSearchParams(searchParams);
                        next.delete('scope');
                        setSearchParams(next, { replace: true });
                      }}
                      className={`rounded-md border px-3 py-1 text-sm ${
                        searchParams.get('scope') !== 'construction'
                          ? 'border-sy-teal-600 bg-sy-teal-50 text-sy-teal-800 font-semibold'
                          : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                      }`}
                      data-testid="budget-scope-toggle-full"
                    >
                      Full Budget
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        const next = new URLSearchParams(searchParams);
                        next.set('scope', 'construction');
                        setSearchParams(next, { replace: true });
                      }}
                      className={`rounded-md border px-3 py-1 text-sm ${
                        searchParams.get('scope') === 'construction'
                          ? 'border-sy-teal-600 bg-sy-teal-50 text-sy-teal-800 font-semibold'
                          : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                      }`}
                      data-testid="budget-scope-toggle-construction"
                    >
                      Construction Budget
                    </button>
                  </>
                ) : null}
              </div>
              <BudgetJobCostingGrid
                key={searchParams.get('scope') || 'full'}
                budgetId={budgetId}
                scope={searchParams.get('scope') || undefined}
              />
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
