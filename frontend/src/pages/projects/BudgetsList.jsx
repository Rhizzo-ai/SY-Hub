/**
 * BudgetsList — Prompt 2.4B-i §R4.6.
 *
 * Per-project budgets listing. TanStack Table for the grid + lazy
 * create-from-appraisal dialog. Mobile renders a read-only banner.
 *
 * Permission gates:
 *   - View page: budgets.view (E7 — backend uses .view, not .read)
 *   - Refresh attention: budgets.admin
 *   - Create from appraisal: budgets.create + desktop
 *
 * Rules of Hooks: every hook is called unconditionally above any early
 * return. The `enabled` flag stops a wasted 403 fetch for users without
 * budgets.view (the backend would 403 anyway, but we skip the round-trip).
 */
import { useParams, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import { useIsDesktop } from '@/lib/useIsDesktop';
import {
  useProjectBudgets,
  useRefreshAttention,
} from '@/hooks/budgets';
import {
  canCreateFromAppraisal,
  canRefreshAttention,
} from '@/lib/budgetCapability';
import { BudgetsTable } from '@/components/budgets/BudgetsTable';
import { CreateFromAppraisalDialog } from '@/components/budgets/CreateFromAppraisalDialog';

export default function BudgetsList() {
  const { projectId } = useParams();
  const { me } = useAuth();
  const isDesktop = useIsDesktop();

  const canView   = !!me?.permissions?.includes('budgets.view');
  const canCreate = canCreateFromAppraisal(me) && isDesktop;
  const canAdmin  = canRefreshAttention(me) && isDesktop;

  // ALL hooks must be called before any conditional return (Rules of Hooks).
  const { data, isLoading, isError, error } = useProjectBudgets(projectId, {
    enabled: canView,
  });
  const refreshMut = useRefreshAttention();

  const budgets = data?.items ?? [];

  if (!canView) {
    return (
      <div
        data-testid="budgets-list-no-perm"
        className="m-6 rounded-lg border border-slate-200 bg-slate-50 p-6 text-slate-600"
      >
        You don't have access to budgets. Contact a director if you need this.
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <nav className="text-sm text-slate-600" data-testid="budgets-list-breadcrumb">
        <Link to="/projects" className="hover:underline">Projects</Link>
        <span className="mx-1.5 text-slate-400">/</span>
        <Link to={`/projects/${projectId}`} className="hover:underline">
          Project
        </Link>
        <span className="mx-1.5 text-slate-400">/</span>
        <span className="text-slate-900">Budgets</span>
      </nav>

      <header className="flex items-center justify-between gap-3">
        <h1
          data-testid="budgets-list-title"
          className="text-2xl font-semibold text-slate-900"
        >
          Budgets
        </h1>
        <div className="hidden items-center gap-2 md:flex">
          {canAdmin && (
            <Button
              variant="outline"
              disabled={refreshMut.isPending}
              onClick={() => refreshMut.mutate()}
              data-testid="budgets-refresh-attention"
            >
              {refreshMut.isPending ? 'Scanning…' : 'Refresh attention'}
            </Button>
          )}
          {canCreate && (
            <CreateFromAppraisalDialog
              projectId={projectId}
              budgets={budgets}
              trigger={
                <Button
                  className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
                  data-testid="budgets-create-button"
                >
                  Create from Approved Appraisal
                </Button>
              }
            />
          )}
        </div>
      </header>

      {/* Mobile read-only banner */}
      <div
        data-testid="budgets-list-mobile-banner"
        className="md:hidden rounded-md bg-slate-100 px-4 py-2 text-xs text-slate-600"
      >
        Read-only on mobile. Use desktop to edit.
      </div>

      {isLoading ? (
        <div
          data-testid="budgets-list-loading"
          className="rounded-lg border border-slate-200 p-12 text-center text-slate-500"
        >
          Loading budgets…
        </div>
      ) : isError ? (
        <div
          data-testid="budgets-list-error"
          className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700"
        >
          Failed to load budgets: {error?.message ?? 'Unknown error.'}
        </div>
      ) : (
        <BudgetsTable budgets={budgets} projectId={projectId} />
      )}
    </div>
  );
}
