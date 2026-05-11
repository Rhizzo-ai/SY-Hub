/**
 * BudgetLineage — Prompt 2.4B-i §R5 follow-up (E10 errata).
 *
 * Renders a tiny prev/next breadcrumb when the budget has siblings in
 * the same project. The backend does NOT expose lineage pointers
 * (no `superseded_by_id`, no `previous_version_id`) — see errata E10.
 * We compute lineage entirely from the cached project-budgets list.
 *
 * Behaviour:
 *   - 0 or 1 budget in project → render nothing.
 *   - prev = the budget with the next-lower version_number in the same
 *     project (regardless of status — Superseded budgets still chain).
 *   - next = the budget with the next-higher version_number.
 *   - Links: "← Previous version (vN)" / "Next version (vN+1) →"
 *
 * Slate-500, inline-flex, gap-3 so it sits cleanly below the version
 * badge. testids exposed for R8.
 *
 * The `useProjectBudgets(projectId)` query is shared cache — calling
 * it from the header does not duplicate the list-page fetch. If the
 * user lands directly on the detail URL (cold cache), the list fetches
 * once and resolves quickly; the lineage row simply unmounts→remounts
 * with the data.
 */
import { Link } from 'react-router-dom';
import { useProjectBudgets } from '@/hooks/budgets';

export function BudgetLineage({ budget, projectId }) {
  // Always-on hook (Rules of Hooks). Suspended if data not yet loaded.
  const { data } = useProjectBudgets(projectId, { enabled: !!projectId });
  const all = data?.items ?? [];
  if (!budget || all.length < 2) return null;

  // Sort ascending by version_number. Linear-scan find prev/next.
  const sorted = [...all].sort(
    (a, b) => (a.version_number ?? 0) - (b.version_number ?? 0),
  );
  const idx = sorted.findIndex((b) => b.id === budget.id);
  if (idx < 0) return null;
  const prev = idx > 0 ? sorted[idx - 1] : null;
  const next = idx < sorted.length - 1 ? sorted[idx + 1] : null;
  if (!prev && !next) return null;

  return (
    <div
      data-testid="budget-lineage"
      className="flex items-center gap-3 text-xs text-slate-500"
    >
      {prev && (
        <Link
          to={`/projects/${projectId}/budgets/${prev.id}`}
          data-testid="budget-lineage-prev"
          className="hover:text-slate-900 hover:underline"
        >
          ← Previous version (v{prev.version_number})
        </Link>
      )}
      {prev && next && <span aria-hidden>·</span>}
      {next && (
        <Link
          to={`/projects/${projectId}/budgets/${next.id}`}
          data-testid="budget-lineage-next"
          className="hover:text-slate-900 hover:underline"
        >
          Next version (v{next.version_number}) →
        </Link>
      )}
    </div>
  );
}
