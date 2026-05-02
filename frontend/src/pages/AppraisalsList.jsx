/**
 * AppraisalsList — /projects/:id/appraisals
 *
 * Lists every appraisal version for a project. Header includes a Back
 * link to the project, permission-gated New button, and a version table
 * with state badges + last-updated timestamp.
 */
import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Plus, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { fmtGBP, fmtPct } from "@/lib/appraisalMath";
import { formatDateTime } from "@/lib/format";


const STATE_BADGE = {
    Draft: "bg-slate-100 text-slate-700 border-slate-300",
    Submitted: "bg-amber-50 text-amber-800 border-amber-200",
    Approved: "bg-emerald-50 text-emerald-800 border-emerald-200",
    Rejected: "bg-rose-50 text-rose-700 border-rose-200",
    Superseded: "bg-slate-50 text-slate-500 border-slate-200",
};


export default function AppraisalsList() {
    const { id: projectId } = useParams();
    const { me } = useAuth();
    const perms = me?.permissions || [];
    const isSuper = me?.is_super_admin;
    const canCreate = isSuper || perms.includes("appraisals.create");
    const canSeeFin = isSuper || perms.includes("appraisals.view_financials");

    const [items, setItems] = useState(null);
    const [project, setProject] = useState(null);
    const [err, setErr] = useState(null);
    const [creating, setCreating] = useState(false);

    useEffect(() => {
        (async () => {
            try {
                const [p, a] = await Promise.all([
                    api.get(`/projects/${projectId}`),
                    api.get(`/v1/projects/${projectId}/appraisals`),
                ]);
                setProject(p.data);
                setItems(a.data.items || []);
            } catch (e) {
                setErr(e.friendlyMessage || "Failed to load appraisals");
            }
        })();
    }, [projectId]);

    const createDraft = async () => {
        setCreating(true);
        try {
            const name = `Appraisal v${(items?.length || 0) + 1}`;
            const r = await api.post(`/v1/projects/${projectId}/appraisals`, {
                name, land_purchase_price: "0",
                sdlt_category: "Residential_Standard",
                project_duration_months: 18,
            });
            // Prepend to list; link to detail.
            setItems((prev) => [r.data, ...(prev || [])]);
        } catch (e) {
            setErr(e.friendlyMessage || "Failed to create appraisal");
        } finally { setCreating(false); }
    };

    if (items === null) {
        return (
            <div className="flex items-center gap-2 text-slate-500"
                 data-testid="appraisals-list-loading">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading appraisals…
            </div>
        );
    }

    return (
        <div className="space-y-6" data-testid="appraisals-list-page">
            <div className="flex items-center justify-between">
                <div>
                    <Link to={`/projects/${projectId}`}
                          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"
                          data-testid="back-to-project-link">
                        <ArrowLeft className="w-4 h-4" /> Back to project
                    </Link>
                    <h1 className="font-heading text-3xl font-bold text-slate-900 mt-2">
                        Appraisals
                    </h1>
                    <p className="text-sm text-slate-500 mt-1">
                        {project?.project_code} — {project?.name}
                    </p>
                </div>
                {canCreate && (
                    <Button onClick={createDraft} disabled={creating}
                            data-testid="create-appraisal-btn">
                        {creating
                            ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Creating…</>
                            : <><Plus className="w-4 h-4 mr-2" /> New appraisal</>}
                    </Button>
                )}
            </div>

            {err && (
                <div className="border border-rose-200 bg-rose-50 text-rose-800 p-3 rounded text-sm"
                     data-testid="appraisals-list-error">
                    {err}
                </div>
            )}

            {items.length === 0 ? (
                <div className="border border-dashed border-slate-300 p-10 rounded text-center text-slate-500"
                     data-testid="appraisals-empty-state">
                    No appraisals yet for this project.{" "}
                    {canCreate && "Click 'New appraisal' to create version 1."}
                </div>
            ) : (
                <div className="border border-slate-200 rounded overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-left">
                            <tr className="text-xs uppercase tracking-wide text-slate-500">
                                <th className="px-4 py-3">Version</th>
                                <th className="px-4 py-3">Name</th>
                                <th className="px-4 py-3">State</th>
                                {canSeeFin && <th className="px-4 py-3 text-right">Total GDV</th>}
                                {canSeeFin && <th className="px-4 py-3 text-right">Total cost</th>}
                                {canSeeFin && <th className="px-4 py-3 text-right">Profit on cost</th>}
                                <th className="px-4 py-3">Updated</th>
                                <th className="px-4 py-3" />
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((a) => (
                                <tr key={a.id} className="border-t border-slate-100 hover:bg-slate-50"
                                    data-testid={`appraisal-row-${a.version}`}>
                                    <td className="px-4 py-3 font-mono text-xs">v{a.version}</td>
                                    <td className="px-4 py-3">{a.name}</td>
                                    <td className="px-4 py-3">
                                        <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded ${STATE_BADGE[a.state] || ""}`}
                                              data-testid={`appraisal-state-${a.version}`}>
                                            {a.state}
                                        </span>
                                    </td>
                                    {canSeeFin && <td className="px-4 py-3 text-right font-mono">{fmtGBP(a.total_gdv)}</td>}
                                    {canSeeFin && <td className="px-4 py-3 text-right font-mono">{fmtGBP(a.total_cost)}</td>}
                                    {canSeeFin && <td className="px-4 py-3 text-right font-mono">{fmtPct(a.profit_on_cost_pct)}</td>}
                                    <td className="px-4 py-3 text-xs text-slate-500">
                                        {formatDateTime(a.updated_at)}
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        <Link to={`/appraisals/${a.id}`}
                                              className="text-sm text-blue-600 hover:underline"
                                              data-testid={`open-appraisal-${a.version}`}>
                                            Open →
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
