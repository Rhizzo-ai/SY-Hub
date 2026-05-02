/**
 * AppraisalPage — /appraisals/:id
 *
 * Thin shell. Handles:
 *   • load/reload of the appraisal document
 *   • local `stale` (dirty) flag for the stale-until-save UX
 *   • state-machine CTAs (Submit / Approve / Reject / Withdraw / Reopen)
 *   • top-level banners (submitted / rejected / superseded)
 *   • tab routing
 *
 * Tab bodies live in /components/appraisal/{Header,Units,Costs,Finance,Summary}Tab.jsx.
 * Shared atoms (StalePill, Kpi, Field, enum constants) live in atoms.jsx.
 *
 * TWO-LAYER CALC MODEL (recap — implemented in the per-tab files):
 *   ┌─ LIVE (decimal.js, instant) ───────────────────────────────────────┐
 *   │ Unit rows only: gia_sqm, gdv_per_sqft, gdv_total_for_type,         │
 *   │                 build_cost_per_unit, build_cost_total_for_type     │
 *   └─────────────────────────────────────────────────────────────────────┘
 *   ┌─ STALE-UNTIL-SAVE (server owns) ───────────────────────────────────┐
 *   │ Everything else — header KPIs, Percentage_Of_* cost effectives,    │
 *   │ SDLT_Engine/Finance_Engine/RLV_Engine auto lines, RLV outputs      │
 *   └─────────────────────────────────────────────────────────────────────┘
 */
import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { STATE_BADGE, StalePill } from "@/components/appraisal/atoms";

import HeaderTab from "@/components/appraisal/HeaderTab";
import UnitsTab from "@/components/appraisal/UnitsTab";
import CostsTab from "@/components/appraisal/CostsTab";
import FinanceTab from "@/components/appraisal/FinanceTab";
import SummaryTab from "@/components/appraisal/SummaryTab";


export default function AppraisalPage() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { me } = useAuth();
    const perms = me?.permissions || [];
    const isSuper = me?.is_super_admin;

    const canEdit = isSuper || perms.includes("appraisals.edit");
    const canSubmit = isSuper || perms.includes("appraisals.submit");
    const canApprove = isSuper || perms.includes("appraisals.approve");
    const canFin = isSuper || perms.includes("appraisals.view_financials");

    const [a, setA] = useState(null);
    const [err, setErr] = useState(null);
    const [busy, setBusy] = useState(false);
    const [stale, setStale] = useState(false);  // local "dirty" marker

    const load = useCallback(async () => {
        try {
            const r = await api.get(`/v1/appraisals/${id}`);
            setA(r.data);
            setStale(r.data.is_stale);
        } catch (e) {
            setErr(e.friendlyMessage || "Failed to load appraisal");
        }
    }, [id]);

    useEffect(() => { load(); }, [load]);

    if (err) {
        return (
            <div className="border border-rose-200 bg-rose-50 text-rose-800 p-4 rounded"
                 data-testid="appraisal-error">{err}</div>
        );
    }
    if (!a) {
        return (
            <div className="flex items-center gap-2 text-slate-500"
                 data-testid="appraisal-loading">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading appraisal…
            </div>
        );
    }

    const editable = a.state === "Draft" && canEdit;

    const handleStateAction = async (action, body = {}) => {
        setBusy(true);
        try {
            const r = await api.post(`/v1/appraisals/${id}/${action}`, body);
            if (action === "reopen" && r.data.version && r.data.id !== id) {
                // Approved→new-version clone — navigate to new row.
                navigate(`/appraisals/${r.data.id}`);
                return;
            }
            await load();
            toast.success(`Appraisal ${
                action === "approve" ? "approved" :
                action === "reject" ? "rejected" :
                action === "submit" ? "submitted" :
                action === "reopen" ? "reopened" :
                action === "withdraw" ? "withdrawn" : "updated"}`);
        } catch (e) {
            toast.error(e.friendlyMessage || "Action failed");
        } finally { setBusy(false); }
    };

    return (
        <div className="space-y-5" data-testid="appraisal-page">
            {/* ---------- Header bar ---------- */}
            <div className="flex items-start justify-between">
                <div>
                    <Link to={`/projects/${a.project_id}/appraisals`}
                          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"
                          data-testid="back-to-appraisals-link">
                        <ArrowLeft className="w-4 h-4" /> Back to appraisals
                    </Link>
                    <div className="flex items-center gap-3 mt-2">
                        <h1 className="font-heading text-3xl font-bold text-slate-900"
                            data-testid="appraisal-name">{a.name}</h1>
                        <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded ${STATE_BADGE[a.state]}`}
                              data-testid="appraisal-state-badge">{a.state}</span>
                        <span className="text-xs text-slate-500 font-mono">v{a.version}</span>
                        <StalePill stale={stale} />
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {a.state === "Draft" && canSubmit && (
                        <Button onClick={() => handleStateAction("submit")}
                                disabled={busy} data-testid="submit-appraisal-btn">
                            Submit for approval
                        </Button>
                    )}
                    {a.state === "Submitted" && canApprove && (
                        <>
                            <Button variant="outline"
                                    onClick={() => {
                                        const reason = window.prompt(
                                            "Rejection reason (5+ chars):"
                                        );
                                        if (reason && reason.trim().length >= 5) {
                                            handleStateAction("reject", { reason });
                                        }
                                    }}
                                    disabled={busy} data-testid="reject-appraisal-btn">
                                Reject
                            </Button>
                            <Button onClick={() => handleStateAction("approve")}
                                    disabled={busy} data-testid="approve-appraisal-btn">
                                Approve
                            </Button>
                        </>
                    )}
                    {a.state === "Submitted" && a.submitted_by_user_id === me?.id && (
                        <Button variant="outline"
                                onClick={() => handleStateAction("withdraw")}
                                disabled={busy} data-testid="withdraw-appraisal-btn">
                            Withdraw
                        </Button>
                    )}
                    {(a.state === "Rejected" || a.state === "Approved") && canEdit && (
                        <Button variant="outline"
                                onClick={() => handleStateAction("reopen")}
                                disabled={busy} data-testid="reopen-appraisal-btn">
                            {a.state === "Approved" ? "Reopen (new version)" : "Reopen"}
                        </Button>
                    )}
                </div>
            </div>

            {/* ---------- State-based banners ---------- */}
            {a.state === "Superseded" && (
                <div className="border border-slate-300 bg-slate-50 text-slate-700 p-3 rounded text-sm"
                     data-testid="superseded-banner">
                    This version has been superseded. See the most-recent Draft
                    on the project's appraisal list.
                </div>
            )}
            {a.state === "Rejected" && a.rejection_reason && (
                <div className="border border-rose-200 bg-rose-50 text-rose-800 p-3 rounded text-sm"
                     data-testid="rejection-reason-banner">
                    <strong>Rejected:</strong> {a.rejection_reason}
                </div>
            )}
            {a.state === "Submitted" && (
                <div className="border border-amber-200 bg-amber-50 text-amber-800 p-3 rounded text-sm"
                     data-testid="submitted-banner">
                    This appraisal is awaiting approval — fields are read-only.
                </div>
            )}

            <Tabs defaultValue="header" data-testid="appraisal-tabs">
                <TabsList>
                    <TabsTrigger value="header" data-testid="tab-header">Header</TabsTrigger>
                    <TabsTrigger value="units" data-testid="tab-units">Units</TabsTrigger>
                    {canFin && <TabsTrigger value="costs" data-testid="tab-costs">Costs</TabsTrigger>}
                    {canFin && <TabsTrigger value="finance" data-testid="tab-finance">Finance</TabsTrigger>}
                    {canFin && <TabsTrigger value="summary" data-testid="tab-summary">Summary</TabsTrigger>}
                </TabsList>

                <TabsContent value="header" className="mt-4">
                    <HeaderTab a={a} editable={editable} canFin={canFin}
                               onSaved={(next) => { setA(next); setStale(next.is_stale); }}
                               onDirty={() => setStale(true)} />
                </TabsContent>
                <TabsContent value="units" className="mt-4">
                    <UnitsTab a={a} editable={editable}
                              onReload={load} onDirty={() => setStale(true)} />
                </TabsContent>
                {canFin && (
                    <TabsContent value="costs" className="mt-4">
                        <CostsTab a={a} editable={editable}
                                  onReload={load} onDirty={() => setStale(true)} />
                    </TabsContent>
                )}
                {canFin && (
                    <TabsContent value="finance" className="mt-4">
                        <FinanceTab a={a} editable={editable}
                                    onReload={load} onDirty={() => setStale(true)} />
                    </TabsContent>
                )}
                {canFin && (
                    <TabsContent value="summary" className="mt-4">
                        <SummaryTab a={a} editable={editable} stale={stale}
                                    onReload={load} />
                    </TabsContent>
                )}
            </Tabs>
        </div>
    );
}
