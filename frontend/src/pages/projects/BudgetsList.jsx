/**
 * BudgetsList — Prompt 2.4B-i §R2.4 shell.
 *
 * Final implementation lands in §R4. This shell exists so the route
 * resolves cleanly and the build pack's smoke check passes.
 */
import { useParams, Link } from "react-router-dom";

export default function BudgetsList() {
    const { projectId } = useParams();
    return (
        <div className="space-y-4">
            <nav className="text-sm text-slate-600">
                <Link to="/projects" className="hover:underline">Projects</Link>
                <span className="mx-1.5 text-slate-400">/</span>
                <Link to={`/projects/${projectId}`} className="hover:underline">
                    Project
                </Link>
                <span className="mx-1.5 text-slate-400">/</span>
                <span className="text-slate-900">Budgets</span>
            </nav>
            <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900">
                Budgets
            </h1>
            <p className="text-sm text-slate-500" data-testid="budgets-list-shell">
                Budgets list shell — projectId={projectId}. Final UI lands in §R4.
            </p>
        </div>
    );
}
