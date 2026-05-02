/**
 * AppraisalPage — /appraisals/:id
 *
 * Five tabs: Header, Units, Costs, Finance, Summary.
 *
 * TWO-LAYER CALC MODEL (per Prompt 2.2 v4 spec):
 *   ┌─ LIVE (decimal.js, instant) ──────────────────────────────────────────┐
 *   │ Unit rows: gia_sqm, gdv_per_sqft, gdv_total_for_type,                 │
 *   │            build_cost_per_unit, build_cost_total_for_type             │
 *   └────────────────────────────────────────────────────────────────────────┘
 *   ┌─ STALE-UNTIL-SAVE (server owns, recompute pipeline) ──────────────────┐
 *   │ Header KPIs, Cost-line effective_value (Percentage_Of_* resolution),  │
 *   │ SDLT_Engine / Finance_Engine auto lines, RLV outputs                  │
 *   └────────────────────────────────────────────────────────────────────────┘
 *
 * RLV panel has THREE states:
 *   1. empty          — rlv_computed_at IS NULL
 *   2. calculated     — computed at <timestamp> + Recalculate button
 *   3. non-convergence — banner surfacing the solver's message
 *
 * State-machine-aware UI:
 *   - Draft:      editable; Submit CTA visible
 *   - Submitted:  read-only; Approve/Reject CTAs visible to approvers
 *   - Approved:   read-only; Reopen (new version) CTA
 *   - Rejected:   read-only; Reopen (back to Draft) CTA, rejection reason shown
 *   - Superseded: read-only; banner "this version has been superseded"
 */
import React, { useEffect, useMemo, useState, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
    ArrowLeft, Loader2, Plus, Trash2, RefreshCw, Lock,
    AlertTriangle, CheckCircle2, Calculator, Calendar, Zap,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
    D, fmtGBP, fmtPct, liveTotalGdv, liveTotalBuild,
    pricePerSqft, sqmToSqft, totalGdvForType, totalBuildForType,
} from "@/lib/appraisalMath";
import { formatDateTime } from "@/lib/format";


const STATE_BADGE = {
    Draft: "bg-slate-100 text-slate-700 border-slate-300",
    Submitted: "bg-amber-50 text-amber-800 border-amber-200",
    Approved: "bg-emerald-50 text-emerald-800 border-emerald-200",
    Rejected: "bg-rose-50 text-rose-700 border-rose-200",
    Superseded: "bg-slate-50 text-slate-500 border-slate-200",
};

const SDLT_CATEGORIES = [
    "Residential_Standard", "Residential_Surcharge",
    "Non_Residential", "Corporate_Flat_Rate",
];
const UNIT_TYPES = [
    "Detached", "Semi_Detached", "Terraced", "Flat", "Bungalow",
    "Commercial", "Other",
];
const TENURES = [
    "Open_Market", "Affordable_Rent", "Shared_Ownership",
    "Social_Rent", "Build_To_Rent", "Private_Rent",
];
const COST_CATEGORIES = [
    "Acquisition", "Construction", "Professional_Fees", "Statutory",
    "Finance", "Contingency", "Sales", "Other",
];
const AUTO_SOURCES = [
    "Manual", "Percentage_Of_GDV", "Percentage_Of_Build_Cost",
    "Percentage_Of_Land", "SDLT_Engine", "Finance_Engine", "RLV_Engine",
];
const FINANCE_TYPES = ["Debt", "Equity", "Mezzanine", "Grant"];
const INTEREST_MODES = [
    "Simple_Monthly", "Compound_Monthly", "Rolled_Up", "Serviced",
];


// ---------------------------------------------------------------------
// Small atoms
// ---------------------------------------------------------------------

function StalePill({ stale }) {
    if (!stale) return null;
    return (
        <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 bg-amber-100 text-amber-800 border border-amber-200 rounded"
              data-testid="stale-pill">
            <AlertTriangle className="w-3 h-3" /> Stale
        </span>
    );
}

function Kpi({ label, value, stale, testId }) {
    return (
        <div className="border border-slate-200 rounded p-4 bg-white"
             data-testid={testId}>
            <div className="text-xs text-slate-500 uppercase tracking-wide flex items-center gap-2">
                {label}
                <StalePill stale={stale} />
            </div>
            <div className="mt-1 text-2xl font-mono font-semibold text-slate-900">
                {value}
            </div>
        </div>
    );
}

function SectionHeader({ title, right }) {
    return (
        <div className="flex items-center justify-between mb-3">
            <h2 className="font-heading text-lg font-bold text-slate-900">{title}</h2>
            <div>{right}</div>
        </div>
    );
}


// ---------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------

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
                // Approved→new version clone — navigate to new row.
                navigate(`/appraisals/${r.data.id}`);
                return;
            }
            await load();
            toast.success(`Appraisal ${action === "approve" ? "approved" :
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


// ---------------------------------------------------------------------
// Header tab
// ---------------------------------------------------------------------

function HeaderTab({ a, editable, canFin, onSaved, onDirty }) {
    const [form, setForm] = useState({
        name: a.name,
        reference_date: a.reference_date,
        land_purchase_price: a.land_purchase_price ?? "",
        sdlt_category: a.sdlt_category,
        developer_relief: a.developer_relief,
        contingency_pct: a.contingency_pct ?? "",
        target_profit_on_cost_pct: a.target_profit_on_cost_pct ?? "",
        target_profit_on_gdv_pct: a.target_profit_on_gdv_pct ?? "",
        project_duration_months: a.project_duration_months,
        notes: a.notes ?? "",
    });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => { setForm((p) => ({ ...p, [k]: v })); onDirty(); };

    const save = async () => {
        setSaving(true);
        try {
            const r = await api.put(`/v1/appraisals/${a.id}`, form);
            onSaved(r.data);
            toast.success("Header saved and recomputed.");
        } catch (e) {
            toast.error(e.friendlyMessage || "Save failed");
        } finally { setSaving(false); }
    };

    return (
        <div className="space-y-5 max-w-3xl" data-testid="header-tab">
            <Field label="Name" disabled={!editable}>
                <Input value={form.name} onChange={(e) => set("name", e.target.value)}
                       disabled={!editable} data-testid="header-name-input" />
            </Field>
            <Field label="Reference date" disabled={!editable}>
                <Input type="date" value={form.reference_date}
                       onChange={(e) => set("reference_date", e.target.value)}
                       disabled={!editable} data-testid="header-ref-date-input" />
            </Field>
            {canFin && (
                <Field label="Land purchase price (£)" disabled={!editable}>
                    <Input value={form.land_purchase_price}
                           onChange={(e) => set("land_purchase_price", e.target.value)}
                           disabled={!editable} data-testid="header-land-price-input" />
                </Field>
            )}
            <Field label="SDLT category" disabled={!editable}>
                <select className="w-full border border-slate-300 rounded px-3 py-2 bg-white text-sm"
                        value={form.sdlt_category}
                        onChange={(e) => set("sdlt_category", e.target.value)}
                        disabled={!editable} data-testid="header-sdlt-cat-select">
                    {SDLT_CATEGORIES.map((c) => (
                        <option key={c} value={c}>{c.replace(/_/g, " ")}</option>
                    ))}
                </select>
            </Field>
            <Field label="Developer relief" disabled={!editable}>
                <label className="inline-flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.developer_relief}
                           onChange={(e) => set("developer_relief", e.target.checked)}
                           disabled={!editable} data-testid="header-dev-relief-chk" />
                    Apply developer-relief rule
                </label>
            </Field>
            {canFin && (
                <div className="grid grid-cols-3 gap-4">
                    <Field label="Contingency %" disabled={!editable}>
                        <Input value={form.contingency_pct}
                               onChange={(e) => set("contingency_pct", e.target.value)}
                               disabled={!editable}
                               data-testid="header-contingency-input" />
                    </Field>
                    <Field label="Target profit on cost %" disabled={!editable}>
                        <Input value={form.target_profit_on_cost_pct}
                               onChange={(e) => set("target_profit_on_cost_pct", e.target.value)}
                               disabled={!editable}
                               data-testid="header-hurdle-cost-input" />
                    </Field>
                    <Field label="Target profit on GDV %" disabled={!editable}>
                        <Input value={form.target_profit_on_gdv_pct}
                               onChange={(e) => set("target_profit_on_gdv_pct", e.target.value)}
                               disabled={!editable}
                               data-testid="header-hurdle-gdv-input" />
                    </Field>
                </div>
            )}
            <Field label="Project duration (months)" disabled={!editable}>
                <Input type="number" min="0" value={form.project_duration_months}
                       onChange={(e) => set("project_duration_months", parseInt(e.target.value || "0", 10))}
                       disabled={!editable} data-testid="header-duration-input" />
            </Field>
            <Field label="Notes" disabled={!editable}>
                <textarea className="w-full border border-slate-300 rounded px-3 py-2 bg-white text-sm"
                          rows={3} value={form.notes}
                          onChange={(e) => set("notes", e.target.value)}
                          disabled={!editable} data-testid="header-notes-input" />
            </Field>

            {editable && (
                <Button onClick={save} disabled={saving} data-testid="header-save-btn">
                    {saving ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Saving…</>
                            : "Save and recompute"}
                </Button>
            )}
        </div>
    );
}

function Field({ label, disabled, children }) {
    return (
        <label className={`block text-sm ${disabled ? "opacity-70" : ""}`}>
            <span className="text-slate-600 text-xs uppercase tracking-wide flex items-center gap-1">
                {label} {disabled && <Lock className="w-3 h-3" />}
            </span>
            <div className="mt-1">{children}</div>
        </label>
    );
}


// ---------------------------------------------------------------------
// Units tab — LIVE decimal.js derivations per row
// ---------------------------------------------------------------------

function UnitsTab({ a, editable, onReload, onDirty }) {
    const [rows, setRows] = useState(() =>
        (a.units || []).map((u) => ({ ...u }))
    );

    // Refresh rows when server data changes.
    useEffect(() => {
        setRows((a.units || []).map((u) => ({ ...u })));
    }, [a.units]);

    const setRow = (idx, patch) => {
        setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
        onDirty();
    };

    const saveRow = async (idx) => {
        const r = rows[idx];
        try {
            if (r.id) {
                await api.put(`/v1/appraisals/${a.id}/units/${r.id}`, r);
            } else {
                await api.post(`/v1/appraisals/${a.id}/units`, r);
            }
            toast.success("Unit saved.");
            onReload();
        } catch (e) {
            toast.error(e.friendlyMessage || "Save failed");
        }
    };

    const deleteRow = async (idx) => {
        const r = rows[idx];
        if (!r.id) {
            setRows((prev) => prev.filter((_, i) => i !== idx));
            return;
        }
        try {
            await api.delete(`/v1/appraisals/${a.id}/units/${r.id}`);
            toast.success("Unit removed.");
            onReload();
        } catch (e) {
            toast.error(e.friendlyMessage || "Delete failed");
        }
    };

    const addRow = () => {
        setRows((prev) => [...prev, {
            unit_label: "", unit_type: "Detached", tenure: "Open_Market",
            quantity: 1, gia_sqm: "", price_per_unit: "0",
            build_cost_per_unit: "0", display_order: prev.length * 10 + 10,
        }]);
        onDirty();
    };

    const liveGdv = liveTotalGdv(rows);
    const liveBuild = liveTotalBuild(rows);

    return (
        <div className="space-y-4" data-testid="units-tab">
            <SectionHeader title="Unit mix"
                right={editable && (
                    <Button variant="outline" onClick={addRow} data-testid="add-unit-btn">
                        <Plus className="w-4 h-4 mr-1" /> Add row
                    </Button>
                )} />

            <div className="grid grid-cols-3 gap-4">
                <Kpi label="Live GDV (this session)"
                     value={fmtGBP(liveGdv)}
                     testId="live-gdv-kpi" />
                <Kpi label="Live Build (this session)"
                     value={fmtGBP(liveBuild)}
                     testId="live-build-kpi" />
                <Kpi label="Server GDV (last save)"
                     value={fmtGBP(a.total_gdv)}
                     stale={!liveGdv.eq(D(a.total_gdv || 0))}
                     testId="server-gdv-kpi" />
            </div>

            {rows.length === 0 ? (
                <div className="border border-dashed border-slate-300 p-6 text-center text-slate-500 rounded"
                     data-testid="units-empty">
                    No units yet. Add a row to start building the unit mix.
                </div>
            ) : (
                <div className="border border-slate-200 rounded overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                            <tr>
                                <th className="px-3 py-2 text-left">Label</th>
                                <th className="px-3 py-2 text-left">Type</th>
                                <th className="px-3 py-2 text-left">Tenure</th>
                                <th className="px-3 py-2 text-right">Qty</th>
                                <th className="px-3 py-2 text-right">GIA (sqm)</th>
                                <th className="px-3 py-2 text-right">Price / unit</th>
                                <th className="px-3 py-2 text-right">GDV / sqft (live)</th>
                                <th className="px-3 py-2 text-right">Type GDV (live)</th>
                                <th className="px-3 py-2 text-right">Build / unit</th>
                                <th className="px-3 py-2 text-right">Type build (live)</th>
                                {editable && <th className="px-3 py-2" />}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r, idx) => {
                                const ppsqft = pricePerSqft(r.price_per_unit, r.gia_sqm);
                                const gdvT = totalGdvForType(r.price_per_unit, r.quantity);
                                const buildT = totalBuildForType(r.build_cost_per_unit, r.quantity);
                                return (
                                    <tr key={r.id || `new-${idx}`} className="border-t border-slate-100"
                                        data-testid={`unit-row-${idx}`}>
                                        <td className="px-3 py-2">
                                            <Input value={r.unit_label}
                                                   onChange={(e) => setRow(idx, { unit_label: e.target.value })}
                                                   disabled={!editable}
                                                   data-testid={`unit-label-${idx}`} />
                                        </td>
                                        <td className="px-3 py-2">
                                            <select className="border border-slate-300 rounded px-2 py-1 bg-white text-sm"
                                                    value={r.unit_type}
                                                    onChange={(e) => setRow(idx, { unit_type: e.target.value })}
                                                    disabled={!editable}
                                                    data-testid={`unit-type-${idx}`}>
                                                {UNIT_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
                                            </select>
                                        </td>
                                        <td className="px-3 py-2">
                                            <select className="border border-slate-300 rounded px-2 py-1 bg-white text-sm"
                                                    value={r.tenure}
                                                    onChange={(e) => setRow(idx, { tenure: e.target.value })}
                                                    disabled={!editable}
                                                    data-testid={`unit-tenure-${idx}`}>
                                                {TENURES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
                                            </select>
                                        </td>
                                        <td className="px-3 py-2 text-right">
                                            <Input type="number" className="text-right w-20"
                                                   value={r.quantity}
                                                   onChange={(e) => setRow(idx, { quantity: parseInt(e.target.value || "0", 10) })}
                                                   disabled={!editable}
                                                   data-testid={`unit-qty-${idx}`} />
                                        </td>
                                        <td className="px-3 py-2 text-right">
                                            <Input className="text-right w-24"
                                                   value={r.gia_sqm ?? ""}
                                                   onChange={(e) => setRow(idx, { gia_sqm: e.target.value })}
                                                   disabled={!editable}
                                                   data-testid={`unit-gia-${idx}`} />
                                        </td>
                                        <td className="px-3 py-2 text-right">
                                            <Input className="text-right w-28"
                                                   value={r.price_per_unit}
                                                   onChange={(e) => setRow(idx, { price_per_unit: e.target.value })}
                                                   disabled={!editable}
                                                   data-testid={`unit-price-${idx}`} />
                                        </td>
                                        <td className="px-3 py-2 text-right font-mono text-xs text-emerald-700"
                                            data-testid={`unit-gdv-per-sqft-${idx}`}>
                                            {ppsqft ? fmtGBP(ppsqft) : "—"}
                                        </td>
                                        <td className="px-3 py-2 text-right font-mono text-emerald-700"
                                            data-testid={`unit-type-gdv-${idx}`}>
                                            {fmtGBP(gdvT)}
                                        </td>
                                        <td className="px-3 py-2 text-right">
                                            <Input className="text-right w-28"
                                                   value={r.build_cost_per_unit}
                                                   onChange={(e) => setRow(idx, { build_cost_per_unit: e.target.value })}
                                                   disabled={!editable}
                                                   data-testid={`unit-build-${idx}`} />
                                        </td>
                                        <td className="px-3 py-2 text-right font-mono text-emerald-700"
                                            data-testid={`unit-type-build-${idx}`}>
                                            {fmtGBP(buildT)}
                                        </td>
                                        {editable && (
                                            <td className="px-3 py-2 text-right space-x-1">
                                                <Button size="sm" variant="outline"
                                                        onClick={() => saveRow(idx)}
                                                        data-testid={`unit-save-${idx}`}>
                                                    Save
                                                </Button>
                                                <Button size="sm" variant="ghost"
                                                        onClick={() => deleteRow(idx)}
                                                        data-testid={`unit-delete-${idx}`}>
                                                    <Trash2 className="w-4 h-4 text-rose-600" />
                                                </Button>
                                            </td>
                                        )}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}


// ---------------------------------------------------------------------
// Costs tab
// ---------------------------------------------------------------------

function CostsTab({ a, editable, onReload, onDirty }) {
    const [rows, setRows] = useState(() =>
        (a.cost_lines || []).map((l) => ({ ...l }))
    );

    useEffect(() => {
        setRows((a.cost_lines || []).map((l) => ({ ...l })));
    }, [a.cost_lines]);

    const setRow = (idx, patch) => {
        setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
        onDirty();
    };

    const saveRow = async (idx) => {
        const r = rows[idx];
        const payload = {
            display_order: r.display_order ?? 0,
            cost_code_id: r.cost_code_id || null,
            label: r.label, category: r.category,
            auto_source: r.auto_source,
            percentage: r.percentage ?? null,
            amount: r.amount ?? "0",
            is_locked: r.is_locked ?? false, notes: r.notes || null,
        };
        try {
            if (r.id) {
                await api.put(`/v1/appraisals/${a.id}/cost-lines/${r.id}`, payload);
            } else {
                await api.post(`/v1/appraisals/${a.id}/cost-lines`, payload);
            }
            toast.success("Cost line saved.");
            onReload();
        } catch (e) {
            toast.error(e.friendlyMessage || "Save failed");
        }
    };

    const deleteRow = async (idx) => {
        const r = rows[idx];
        if (!r.id) {
            setRows((prev) => prev.filter((_, i) => i !== idx));
            return;
        }
        try {
            await api.delete(`/v1/appraisals/${a.id}/cost-lines/${r.id}`);
            toast.success("Cost line removed.");
            onReload();
        } catch (e) {
            toast.error(e.friendlyMessage || "Delete failed");
        }
    };

    const addRow = () => {
        setRows((prev) => [...prev, {
            label: "", category: "Other", auto_source: "Manual",
            percentage: null, amount: "0", is_locked: false,
            display_order: prev.length * 10 + 10,
        }]);
        onDirty();
    };

    const grouped = useMemo(() => {
        const out = {};
        rows.forEach((r) => { (out[r.category] ??= []).push(r); });
        return out;
    }, [rows]);

    return (
        <div className="space-y-4" data-testid="costs-tab">
            <SectionHeader title="Cost lines"
                right={editable && (
                    <Button variant="outline" onClick={addRow} data-testid="add-cost-line-btn">
                        <Plus className="w-4 h-4 mr-1" /> Add line
                    </Button>
                )} />

            {rows.length === 0 ? (
                <div className="border border-dashed border-slate-300 p-6 text-center text-slate-500 rounded"
                     data-testid="costs-empty">
                    No cost lines yet.
                </div>
            ) : (
                <div className="space-y-4">
                    {COST_CATEGORIES.map((cat) => {
                        const lines = grouped[cat];
                        if (!lines || lines.length === 0) return null;
                        const catTotal = lines.reduce(
                            (s, r) => s.add(D(r.amount || 0)), D(0)
                        );
                        return (
                            <div key={cat} className="border border-slate-200 rounded"
                                 data-testid={`cost-cat-${cat}`}>
                                <div className="flex items-center justify-between px-3 py-2 bg-slate-50 border-b border-slate-200">
                                    <div className="font-heading font-semibold text-sm">{cat.replace(/_/g, " ")}</div>
                                    <div className="font-mono text-sm">{fmtGBP(catTotal)}</div>
                                </div>
                                <table className="w-full text-sm">
                                    <thead className="text-xs uppercase text-slate-500">
                                        <tr>
                                            <th className="px-3 py-1 text-left">Label</th>
                                            <th className="px-3 py-1 text-left">Source</th>
                                            <th className="px-3 py-1 text-right">%</th>
                                            <th className="px-3 py-1 text-right">Amount (effective)</th>
                                            {editable && <th className="px-3 py-1" />}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {lines.map((r) => {
                                            const idx = rows.indexOf(r);
                                            const isAuto = r.auto_source !== "Manual";
                                            return (
                                                <tr key={r.id || `new-${idx}`} className="border-t border-slate-100"
                                                    data-testid={`cost-line-${idx}`}>
                                                    <td className="px-3 py-2">
                                                        <Input value={r.label}
                                                               onChange={(e) => setRow(idx, { label: e.target.value })}
                                                               disabled={!editable}
                                                               data-testid={`cost-line-label-${idx}`} />
                                                    </td>
                                                    <td className="px-3 py-2">
                                                        <div className="flex items-center gap-2">
                                                            <select className="border border-slate-300 rounded px-2 py-1 bg-white text-sm"
                                                                    value={r.auto_source}
                                                                    onChange={(e) => setRow(idx, { auto_source: e.target.value })}
                                                                    disabled={!editable}
                                                                    data-testid={`cost-line-source-${idx}`}>
                                                                {AUTO_SOURCES.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
                                                            </select>
                                                            {isAuto && (
                                                                <span className="inline-flex items-center gap-1 text-[10px] uppercase px-1.5 py-0.5 bg-violet-50 text-violet-700 border border-violet-200 rounded"
                                                                      data-testid={`cost-line-auto-badge-${idx}`}>
                                                                    <Zap className="w-3 h-3" /> Auto
                                                                </span>
                                                            )}
                                                        </div>
                                                    </td>
                                                    <td className="px-3 py-2 text-right">
                                                        {isAuto && r.auto_source !== "SDLT_Engine"
                                                         && r.auto_source !== "Finance_Engine"
                                                         && r.auto_source !== "RLV_Engine" ? (
                                                            <Input className="text-right w-20"
                                                                   value={r.percentage ?? ""}
                                                                   onChange={(e) => setRow(idx, { percentage: e.target.value })}
                                                                   disabled={!editable}
                                                                   data-testid={`cost-line-pct-${idx}`} />
                                                        ) : "—"}
                                                    </td>
                                                    <td className="px-3 py-2 text-right font-mono">
                                                        <div className="flex items-center justify-end gap-2">
                                                            {r.auto_source === "Manual" ? (
                                                                <Input className="text-right w-28"
                                                                       value={r.amount}
                                                                       onChange={(e) => setRow(idx, { amount: e.target.value })}
                                                                       disabled={!editable}
                                                                       data-testid={`cost-line-amount-${idx}`} />
                                                            ) : (
                                                                <>
                                                                    <StalePill stale={true} />
                                                                    <span data-testid={`cost-line-amount-display-${idx}`}>{fmtGBP(r.amount)}</span>
                                                                </>
                                                            )}
                                                        </div>
                                                    </td>
                                                    {editable && (
                                                        <td className="px-3 py-2 text-right space-x-1">
                                                            <Button size="sm" variant="outline"
                                                                    onClick={() => saveRow(idx)}
                                                                    data-testid={`cost-line-save-${idx}`}>
                                                                Save
                                                            </Button>
                                                            <Button size="sm" variant="ghost"
                                                                    onClick={() => deleteRow(idx)}
                                                                    data-testid={`cost-line-delete-${idx}`}>
                                                                <Trash2 className="w-4 h-4 text-rose-600" />
                                                            </Button>
                                                        </td>
                                                    )}
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}


// ---------------------------------------------------------------------
// Finance tab
// ---------------------------------------------------------------------

function FinanceTab({ a, editable, onReload, onDirty }) {
    const [rows, setRows] = useState(() =>
        (a.finance_facilities || []).map((f) => ({ ...f }))
    );
    useEffect(() => {
        setRows((a.finance_facilities || []).map((f) => ({ ...f })));
    }, [a.finance_facilities]);

    const setRow = (idx, patch) => {
        setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
        onDirty();
    };

    const saveRow = async (idx) => {
        const r = rows[idx];
        try {
            if (r.id) {
                await api.put(`/v1/appraisals/${a.id}/finance/${r.id}`, r);
            } else {
                await api.post(`/v1/appraisals/${a.id}/finance`, r);
            }
            toast.success("Facility saved.");
            onReload();
        } catch (e) {
            toast.error(e.friendlyMessage || "Save failed");
        }
    };

    const deleteRow = async (idx) => {
        const r = rows[idx];
        if (!r.id) {
            setRows((prev) => prev.filter((_, i) => i !== idx));
            return;
        }
        try {
            await api.delete(`/v1/appraisals/${a.id}/finance/${r.id}`);
            toast.success("Facility removed.");
            onReload();
        } catch (e) {
            toast.error(e.friendlyMessage || "Delete failed");
        }
    };

    const addRow = () => {
        setRows((prev) => [...prev, {
            label: "", facility_type: "Debt",
            principal_amount: "0", interest_rate_pct: "0",
            arrangement_fee_pct: "0", exit_fee_pct: "0",
            interest_mode: "Simple_Monthly",
            drawn_from_month: 0, drawn_to_month: a.project_duration_months || 18,
            display_order: prev.length * 10 + 10,
        }]);
        onDirty();
    };

    return (
        <div className="space-y-4" data-testid="finance-tab">
            <SectionHeader title="Finance model"
                right={editable && (
                    <Button variant="outline" onClick={addRow} data-testid="add-facility-btn">
                        <Plus className="w-4 h-4 mr-1" /> Add facility
                    </Button>
                )} />

            {rows.length === 0 ? (
                <div className="border border-dashed border-slate-300 p-6 text-center text-slate-500 rounded"
                     data-testid="finance-empty">
                    No finance facilities yet.
                </div>
            ) : (
                <div className="border border-slate-200 rounded overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                            <tr>
                                <th className="px-3 py-2 text-left">Label</th>
                                <th className="px-3 py-2 text-left">Type</th>
                                <th className="px-3 py-2 text-right">Principal</th>
                                <th className="px-3 py-2 text-right">Rate %</th>
                                <th className="px-3 py-2 text-right">Arr. fee %</th>
                                <th className="px-3 py-2 text-right">Exit fee %</th>
                                <th className="px-3 py-2 text-left">Mode</th>
                                <th className="px-3 py-2 text-right">From</th>
                                <th className="px-3 py-2 text-right">To</th>
                                <th className="px-3 py-2 text-right">Total interest</th>
                                <th className="px-3 py-2 text-right">Total fees</th>
                                {editable && <th className="px-3 py-2" />}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r, idx) => (
                                <tr key={r.id || `new-${idx}`} className="border-t border-slate-100"
                                    data-testid={`facility-row-${idx}`}>
                                    <td className="px-3 py-2">
                                        <Input value={r.label}
                                               onChange={(e) => setRow(idx, { label: e.target.value })}
                                               disabled={!editable}
                                               data-testid={`facility-label-${idx}`} />
                                    </td>
                                    <td className="px-3 py-2">
                                        <select className="border border-slate-300 rounded px-2 py-1 bg-white text-sm"
                                                value={r.facility_type}
                                                onChange={(e) => setRow(idx, { facility_type: e.target.value })}
                                                disabled={!editable}
                                                data-testid={`facility-type-${idx}`}>
                                            {FINANCE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                                        </select>
                                    </td>
                                    <td className="px-3 py-2 text-right"><Input className="text-right w-28" value={r.principal_amount} onChange={(e) => setRow(idx, { principal_amount: e.target.value })} disabled={!editable} data-testid={`facility-principal-${idx}`} /></td>
                                    <td className="px-3 py-2 text-right"><Input className="text-right w-20" value={r.interest_rate_pct} onChange={(e) => setRow(idx, { interest_rate_pct: e.target.value })} disabled={!editable} data-testid={`facility-rate-${idx}`} /></td>
                                    <td className="px-3 py-2 text-right"><Input className="text-right w-20" value={r.arrangement_fee_pct} onChange={(e) => setRow(idx, { arrangement_fee_pct: e.target.value })} disabled={!editable} /></td>
                                    <td className="px-3 py-2 text-right"><Input className="text-right w-20" value={r.exit_fee_pct} onChange={(e) => setRow(idx, { exit_fee_pct: e.target.value })} disabled={!editable} /></td>
                                    <td className="px-3 py-2">
                                        <select className="border border-slate-300 rounded px-2 py-1 bg-white text-sm"
                                                value={r.interest_mode}
                                                onChange={(e) => setRow(idx, { interest_mode: e.target.value })}
                                                disabled={!editable}
                                                data-testid={`facility-mode-${idx}`}>
                                            {INTEREST_MODES.map((m) => <option key={m} value={m}>{m.replace(/_/g, " ")}</option>)}
                                        </select>
                                    </td>
                                    <td className="px-3 py-2 text-right"><Input type="number" className="text-right w-16" value={r.drawn_from_month} onChange={(e) => setRow(idx, { drawn_from_month: parseInt(e.target.value || "0", 10) })} disabled={!editable} /></td>
                                    <td className="px-3 py-2 text-right"><Input type="number" className="text-right w-16" value={r.drawn_to_month} onChange={(e) => setRow(idx, { drawn_to_month: parseInt(e.target.value || "0", 10) })} disabled={!editable} /></td>
                                    <td className="px-3 py-2 text-right font-mono">
                                        <span className="inline-flex items-center gap-1">
                                            <StalePill stale={true} />
                                            <span data-testid={`facility-interest-${idx}`}>{fmtGBP(r.total_interest)}</span>
                                        </span>
                                    </td>
                                    <td className="px-3 py-2 text-right font-mono">
                                        <span className="inline-flex items-center gap-1">
                                            <StalePill stale={true} />
                                            <span data-testid={`facility-fees-${idx}`}>{fmtGBP(r.total_fees)}</span>
                                        </span>
                                    </td>
                                    {editable && (
                                        <td className="px-3 py-2 text-right space-x-1">
                                            <Button size="sm" variant="outline"
                                                    onClick={() => saveRow(idx)}
                                                    data-testid={`facility-save-${idx}`}>Save</Button>
                                            <Button size="sm" variant="ghost"
                                                    onClick={() => deleteRow(idx)}
                                                    data-testid={`facility-delete-${idx}`}>
                                                <Trash2 className="w-4 h-4 text-rose-600" />
                                            </Button>
                                        </td>
                                    )}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}


// ---------------------------------------------------------------------
// Summary tab — KPIs + THREE-STATE RLV panel
// ---------------------------------------------------------------------

function SummaryTab({ a, editable, stale, onReload }) {
    const [rlvForm, setRlvForm] = useState({
        basis: a.rlv_target_basis || "on_cost",
        target_pct: a.rlv_target_value ?? "20",
    });
    const [rlvBusy, setRlvBusy] = useState(false);
    const [rlvMsg, setRlvMsg] = useState(null);  // last message from solver

    const runRlv = async () => {
        setRlvBusy(true);
        setRlvMsg(null);
        try {
            const r = await api.post(`/v1/appraisals/${a.id}/recalculate-rlv`, rlvForm);
            setRlvMsg(r.data);
            toast.success(r.data.converged
                ? `RLV computed in ${r.data.iterations} iterations.`
                : "RLV did not converge — see banner.");
            onReload();
        } catch (e) {
            toast.error(e.friendlyMessage || "RLV failed");
        } finally { setRlvBusy(false); }
    };

    // Determine RLV state.
    //  1. empty          → never computed
    //  2. calculated     → computed_at set, converged=true
    //  3. non-convergence → computed_at set, converged=false
    const rlvState = (() => {
        if (!a.rlv_computed_at) return "empty";
        if (a.rlv_converged) return "calculated";
        return "non_convergence";
    })();

    return (
        <div className="space-y-6" data-testid="summary-tab">
            <SectionHeader title="Summary" right={
                editable && (
                    <Button variant="outline" onClick={async () => {
                        setRlvBusy(true);
                        try {
                            await api.post(`/v1/appraisals/${a.id}/recompute`);
                            toast.success("Recomputed.");
                            onReload();
                        } catch (e) {
                            toast.error(e.friendlyMessage || "Failed");
                        } finally { setRlvBusy(false); }
                    }} disabled={rlvBusy} data-testid="recompute-btn">
                        <RefreshCw className="w-4 h-4 mr-1" /> Recompute
                    </Button>
                )
            } />

            <div className="grid grid-cols-4 gap-4">
                <Kpi label="Total GDV" value={fmtGBP(a.total_gdv)}
                     stale={stale} testId="kpi-total-gdv" />
                <Kpi label="Total cost" value={fmtGBP(a.total_cost)}
                     stale={stale} testId="kpi-total-cost" />
                <Kpi label="Profit" value={fmtGBP(a.total_profit)}
                     stale={stale} testId="kpi-profit" />
                <Kpi label="Profit on cost" value={fmtPct(a.profit_on_cost_pct)}
                     stale={stale} testId="kpi-profit-on-cost" />
            </div>

            <div className="grid grid-cols-4 gap-4">
                <Kpi label="Acquisition" value={fmtGBP(a.total_acquisition_cost)} stale={stale} testId="kpi-acq" />
                <Kpi label="Build" value={fmtGBP(a.total_build_cost)} stale={stale} testId="kpi-build" />
                <Kpi label="Finance" value={fmtGBP(a.total_finance_cost)} stale={stale} testId="kpi-fin" />
                <Kpi label="Profit on GDV" value={fmtPct(a.profit_on_gdv_pct)} stale={stale} testId="kpi-profit-on-gdv" />
            </div>

            {/* RLV panel — three distinct states. */}
            <div className="border border-slate-200 rounded p-4 bg-white"
                 data-testid={`rlv-panel-${rlvState}`}>
                <div className="flex items-center justify-between mb-3">
                    <h3 className="font-heading text-base font-bold text-slate-900 flex items-center gap-2">
                        <Calculator className="w-4 h-4" /> Residual Land Value (RLV)
                    </h3>
                </div>

                {rlvState === "empty" && (
                    <div data-testid="rlv-state-empty">
                        <p className="text-sm text-slate-600 mb-3">
                            Not yet calculated. Pick a target margin and run the solver to
                            compute the land price that would meet it, holding everything else constant.
                        </p>
                        {editable && <RlvForm form={rlvForm} setForm={setRlvForm}
                                              onRun={runRlv} busy={rlvBusy} />}
                    </div>
                )}

                {rlvState === "calculated" && (
                    <div data-testid="rlv-state-calculated">
                        <div className="flex items-center gap-3 mb-3">
                            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                            <span className="text-sm text-slate-700">
                                Converged in {a.rlv_iterations} iterations
                            </span>
                            <span className="text-xs text-slate-400 inline-flex items-center gap-1">
                                <Calendar className="w-3 h-3" />
                                {formatDateTime(a.rlv_computed_at)}
                            </span>
                        </div>
                        <div className="grid grid-cols-3 gap-4 mb-3">
                            <Kpi label="Computed land value"
                                 value={fmtGBP(a.rlv_computed_land_value)}
                                 testId="rlv-land-value-kpi" />
                            <Kpi label="Target basis"
                                 value={a.rlv_target_basis}
                                 testId="rlv-basis-kpi" />
                            <Kpi label="Target %"
                                 value={fmtPct(a.rlv_target_value)}
                                 testId="rlv-target-kpi" />
                        </div>
                        {editable && <RlvForm form={rlvForm} setForm={setRlvForm}
                                              onRun={runRlv} busy={rlvBusy}
                                              label="Recalculate" />}
                    </div>
                )}

                {rlvState === "non_convergence" && (
                    <div data-testid="rlv-state-non-convergence">
                        <div className="border border-rose-200 bg-rose-50 text-rose-800 p-3 rounded text-sm flex items-start gap-2 mb-3">
                            <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                            <div>
                                <div className="font-semibold">RLV did not converge</div>
                                <div className="text-xs mt-1">
                                    {rlvMsg?.message ||
                                     "The solver could not find a land value that meets the target margin within 50 iterations. Try a softer target or review unit pricing."}
                                </div>
                                <div className="text-xs mt-1">
                                    Last computed at {formatDateTime(a.rlv_computed_at)} — {a.rlv_iterations} iterations.
                                </div>
                            </div>
                        </div>
                        {editable && <RlvForm form={rlvForm} setForm={setRlvForm}
                                              onRun={runRlv} busy={rlvBusy}
                                              label="Try again" />}
                    </div>
                )}
            </div>
        </div>
    );
}


function RlvForm({ form, setForm, onRun, busy, label = "Calculate RLV" }) {
    const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));
    return (
        <div className="flex items-end gap-3">
            <Field label="Basis">
                <select className="border border-slate-300 rounded px-2 py-1 bg-white text-sm"
                        value={form.basis}
                        onChange={(e) => set("basis", e.target.value)}
                        data-testid="rlv-basis-select">
                    <option value="on_cost">On cost</option>
                    <option value="on_gdv">On GDV</option>
                </select>
            </Field>
            <Field label="Target %">
                <Input className="w-24" value={form.target_pct}
                       onChange={(e) => set("target_pct", e.target.value)}
                       data-testid="rlv-target-input" />
            </Field>
            <Button onClick={onRun} disabled={busy} data-testid="rlv-run-btn">
                {busy ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Running…</>
                     : label}
            </Button>
        </div>
    );
}
