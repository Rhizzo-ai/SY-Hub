/**
 * BudgetDetail — Prompt 2.4B-i §R2.4 shell.
 *
 * Final implementation lands in §R5/§R6/§R7. This shell exists so the
 * route resolves cleanly and the build pack's smoke check passes.
 */
import { useParams, Link } from "react-router-dom";

export default function BudgetDetail() {
    const { projectId, budgetId } = useParams();
    return (
        <div className="space-y-4">
            <nav className="text-sm text-slate-600">
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
                <span className="text-slate-900 truncate">{budgetId}</span>
            </nav>
            <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900">
                Budget
            </h1>
            <p className="text-sm text-slate-500" data-testid="budget-detail-shell">
                Budget detail shell — projectId={projectId}, budgetId={budgetId}.
                Final UI lands in §R5/§R6/§R7.
            </p>
        </div>
    );
}
