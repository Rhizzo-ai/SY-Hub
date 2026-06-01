/**
 * <BudgetChangeLogPanel/> — Surface E (read-only change log).
 *
 * GET /api/v1/budgets/{budget_id}/change-log returns ALL BCRs for the
 * budget (newest first, capped at 200). Renders as a flat read-only
 * timeline-style list with status pills + reference + net impact.
 *
 * Differs from Surface A (the queue) by being intentionally non-
 * actionable — it's the audit-trail view, not the workflow surface.
 */
import { Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useBudgetChangeLog } from '@/hooks/budgetChanges';
import { canViewBCR } from '@/lib/budgetChangeCapability';
import { fmtGBP } from '@/lib/poFormat';
import BCRStatusPill from '@/components/budgetChanges/BCRStatusPill';

function shortDateTime(s) {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return s;
  }
}

export default function BudgetChangeLogPanel({ budgetId }) {
  const { me } = useAuth();
  const enabled = canViewBCR(me) && !!budgetId;
  const { data, isLoading, isError, error, refetch } = useBudgetChangeLog(
    budgetId, { enabled },
  );

  if (!canViewBCR(me)) {
    return (
      <div
        data-testid="bcr-change-log-no-perm"
        className="rounded-lg border border-slate-200 bg-slate-50 p-6 text-sm text-slate-600"
      >
        You don't have access to the change log.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div
        data-testid="bcr-change-log-loading"
        className="rounded-lg border border-slate-200 p-8 text-center text-sm text-slate-500"
      >
        Loading change log…
      </div>
    );
  }
  if (isError) {
    return (
      <div
        data-testid="bcr-change-log-error"
        className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700"
      >
        <div className="font-medium">Failed to load change log.</div>
        <div className="mt-1 text-rose-600">
          {error?.friendlyMessage ?? error?.message ?? 'Unknown error'}
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="mt-2 rounded border border-rose-300 px-2 py-1 text-xs"
          data-testid="bcr-change-log-retry"
        >
          Retry
        </button>
      </div>
    );
  }
  const rows = data?.items ?? [];
  if (rows.length === 0) {
    return (
      <div
        data-testid="bcr-change-log-empty"
        className="rounded-lg border border-dashed border-slate-200 p-10 text-center text-sm text-slate-500"
      >
        No budget changes on record for this budget yet.
      </div>
    );
  }

  return (
    <ol
      className="space-y-3"
      data-testid="bcr-change-log"
    >
      {rows.map((bcr) => (
        <li
          key={bcr.id}
          className="flex items-start gap-4 rounded-lg border border-slate-200 p-3"
          data-testid={`bcr-change-log-row-${bcr.reference}`}
        >
          <BCRStatusPill status={bcr.status} />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <Link
                to={`/budget-changes/${bcr.id}`}
                className="font-mono text-sm font-semibold text-sy-teal-700 hover:underline"
              >
                {bcr.reference}
              </Link>
              <span className="text-sm text-slate-700">{bcr.title}</span>
              <span className="ml-auto text-xs font-mono text-slate-500 tabular-nums">
                {fmtGBP(bcr.net_impact) ?? '£0.00'}
              </span>
            </div>
            <div className="mt-1 text-xs text-slate-500">
              <span>{bcr.change_type}</span>
              <span className="mx-1.5">·</span>
              <span>{bcr.lines?.length ?? 0} line{bcr.lines?.length === 1 ? '' : 's'}</span>
              {bcr.applied_at ? (
                <>
                  <span className="mx-1.5">·</span>
                  <span>Applied {shortDateTime(bcr.applied_at)}</span>
                </>
              ) : bcr.rejected_at ? (
                <>
                  <span className="mx-1.5">·</span>
                  <span>Rejected {shortDateTime(bcr.rejected_at)}</span>
                </>
              ) : bcr.submitted_at ? (
                <>
                  <span className="mx-1.5">·</span>
                  <span>Submitted {shortDateTime(bcr.submitted_at)}</span>
                </>
              ) : (
                <>
                  <span className="mx-1.5">·</span>
                  <span>Created {shortDateTime(bcr.created_at)}</span>
                </>
              )}
            </div>
            {bcr.rejection_reason ? (
              <div className="mt-1 text-xs italic text-rose-700">
                Rejected: {bcr.rejection_reason}
              </div>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  );
}
