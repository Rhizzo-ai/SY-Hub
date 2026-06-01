/**
 * <BudgetChangeQueue/> — Surface A (per-budget queue).
 *
 * The canonical "Changes" surface for a single budget. Lists BCRs
 * filterable by status. Drives the BudgetDetail "Changes" tab today;
 * the standalone cross-project queue is deferred (backend gap B51 —
 * no /budget-changes/pending or /projects/{id}/budget-changes today).
 *
 * Status filter chips: All / Draft / Submitted / Approved / Applied /
 * Rejected / Withdrawn. Defaults to "Open" (Submitted + Approved) to
 * surface actionable rows first.
 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import { useBudgetBCRs } from '@/hooks/budgetChanges';
import { canCreateBCR, canViewBCR } from '@/lib/budgetChangeCapability';
import { fmtGBP } from '@/lib/poFormat';

import BCRStatusPill from '@/components/budgetChanges/BCRStatusPill';
import CreateBudgetChangeDialog
  from '@/components/budgetChanges/CreateBudgetChangeDialog';

const FILTER_OPTIONS = [
  // value=null means "no status filter applied at server".
  { key: 'open',       label: 'Open',       statuses: ['Submitted', 'Approved'] },
  { key: 'all',        label: 'All',        statuses: null },
  { key: 'draft',      label: 'Draft',      statuses: ['Draft'] },
  { key: 'submitted',  label: 'Submitted',  statuses: ['Submitted'] },
  { key: 'approved',   label: 'Approved',   statuses: ['Approved'] },
  { key: 'applied',    label: 'Applied',    statuses: ['Applied'] },
  { key: 'rejected',   label: 'Rejected',   statuses: ['Rejected'] },
  { key: 'withdrawn',  label: 'Withdrawn',  statuses: ['Withdrawn'] },
];

function shortDate(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleDateString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  } catch {
    return s;
  }
}

export default function BudgetChangeQueue({ budgetId, projectId }) {
  const { me } = useAuth();
  const [filterKey, setFilterKey] = useState('open');
  const [createOpen, setCreateOpen] = useState(false);

  const filter = FILTER_OPTIONS.find((f) => f.key === filterKey)
                 ?? FILTER_OPTIONS[0];

  // Single-status backend filter — for the "Open" composite we fetch
  // unfiltered and filter client-side. Volume is bounded by the
  // backend list cap (200) so this is fine for the per-budget scope.
  const serverStatus = filter.statuses?.length === 1
    ? filter.statuses[0] : undefined;

  const { data, isLoading, isError, error, refetch } = useBudgetBCRs(
    budgetId,
    {
      params: serverStatus ? { status: serverStatus } : {},
      enabled: canViewBCR(me) && !!budgetId,
    },
  );

  const rows = useMemo(() => {
    const items = data?.items ?? [];
    if (!filter.statuses || serverStatus) return items;
    // Client-side filter for composite (Open).
    const allowed = new Set(filter.statuses);
    return items.filter((bcr) => allowed.has(bcr.status));
  }, [data, filter, serverStatus]);

  if (!canViewBCR(me)) {
    return (
      <div
        data-testid="bcr-queue-no-perm"
        className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600"
      >
        You don't have access to budget changes (requires
        <code> budget_changes.view</code>).
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="bcr-queue">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2" data-testid="bcr-queue-filters">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setFilterKey(opt.key)}
              className={`rounded-full border px-3 py-1 text-xs transition ${
                opt.key === filterKey
                  ? 'border-slate-800 bg-slate-900 text-white'
                  : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
              }`}
              data-testid={`bcr-queue-filter-${opt.key}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {canCreateBCR(me) ? (
          <Button
            type="button"
            onClick={() => setCreateOpen(true)}
            data-testid="bcr-queue-new-btn"
          >
            <Plus className="mr-1 h-4 w-4" />
            New change
          </Button>
        ) : null}
      </div>

      {/* Body */}
      {isLoading ? (
        <div
          data-testid="bcr-queue-loading"
          className="rounded-lg border border-slate-200 p-8 text-center text-sm text-slate-500"
        >
          Loading budget changes…
        </div>
      ) : isError ? (
        <div
          data-testid="bcr-queue-error"
          className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700"
        >
          <div className="font-medium">Failed to load budget changes.</div>
          <div className="mt-1 text-rose-600">
            {error?.friendlyMessage ?? error?.message ?? 'Unknown error'}
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-2 rounded border border-rose-300 px-2 py-1 text-xs"
            data-testid="bcr-queue-retry"
          >
            Retry
          </button>
        </div>
      ) : rows.length === 0 ? (
        <div
          data-testid="bcr-queue-empty"
          className="rounded-lg border border-dashed border-slate-200 p-10 text-center text-sm text-slate-500"
        >
          No budget changes in this view.
          {filter.key !== 'all' ? (
            <button
              type="button"
              onClick={() => setFilterKey('all')}
              className="ml-1 underline hover:text-slate-800"
              data-testid="bcr-queue-clear-filter"
            >
              Show all
            </button>
          ) : null}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2 text-left">Reference</th>
                <th className="px-3 py-2 text-left">Title</th>
                <th className="px-3 py-2 text-left">Type</th>
                <th className="px-3 py-2 text-right">Net impact</th>
                <th className="px-3 py-2 text-center">Lines</th>
                <th className="px-3 py-2 text-center">Status</th>
                <th className="px-3 py-2 text-left">Submitted</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((bcr) => (
                <tr
                  key={bcr.id}
                  className="hover:bg-slate-50"
                  data-testid={`bcr-queue-row-${bcr.reference}`}
                >
                  <td className="px-3 py-2 font-mono text-xs">
                    <Link
                      to={`/budget-changes/${bcr.id}`}
                      state={{ projectId, budgetId }}
                      className="font-semibold text-sy-teal-700 hover:underline"
                      data-testid={`bcr-queue-link-${bcr.reference}`}
                    >
                      {bcr.reference}
                    </Link>
                  </td>
                  <td className="px-3 py-2 max-w-md truncate" title={bcr.title}>
                    {bcr.title}
                  </td>
                  <td className="px-3 py-2 text-slate-600">{bcr.change_type}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">
                    {fmtGBP(bcr.net_impact) ?? '£0.00'}
                  </td>
                  <td className="px-3 py-2 text-center text-slate-600">
                    {bcr.lines?.length ?? 0}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <BCRStatusPill status={bcr.status} />
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-500">
                    {shortDate(bcr.submitted_at ?? bcr.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CreateBudgetChangeDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        budgetId={budgetId}
      />
    </div>
  );
}
