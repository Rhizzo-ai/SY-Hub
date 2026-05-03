/**
 * SummaryTab — header KPIs (stale until save) + RLV three-state panel.
 *
 * RLV panel states:
 *   1. empty          — rlv_computed_at IS NULL
 *   2. calculated     — converged: true; shows timestamp + Recalculate
 *   3. non_convergence — converged: false; shows banner with solver message
 *
 * RlvForm is the shared Basis + Target% + Run control, reused by all
 * three states.
 */
import React, { useState } from "react";
import {
    AlertTriangle, Calculator, Calendar, CheckCircle2, Loader2, RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { fmtGBP, fmtPct } from "@/lib/appraisalMath";
import { formatDateTime } from "@/lib/format";
import { Field, Kpi, SectionHeader } from "@/components/appraisal/atoms";


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


export default function SummaryTab({ a, editable, stale, onReload }) {
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

    const recompute = async () => {
        setRlvBusy(true);
        try {
            await api.post(`/v1/appraisals/${a.id}/recompute`);
            toast.success("Recomputed.");
            onReload();
        } catch (e) {
            toast.error(e.friendlyMessage || "Failed");
        } finally { setRlvBusy(false); }
    };

    // Three RLV states.
    const rlvState = (() => {
        if (!a.rlv_computed_at) return "empty";
        if (a.rlv_converged) return "calculated";
        return "non_convergence";
    })();

    return (
        <div className="space-y-6" data-testid="summary-tab">
            <SectionHeader title="Summary" right={
                editable && (
                    <Button variant="outline" onClick={recompute}
                            disabled={rlvBusy} data-testid="recompute-btn">
                        <RefreshCw className="w-4 h-4 mr-1" /> Recompute
                    </Button>
                )
            } />

            <div className="grid grid-cols-4 gap-4">
                <Kpi label="Total GDV" value={fmtGBP(a.gdv_total)}
                     stale={stale} testId="kpi-total-gdv" />
                <Kpi label="Total cost" value={fmtGBP(a.total_cost)}
                     stale={stale} testId="kpi-total-cost" />
                <Kpi label="Profit" value={fmtGBP(a.profit_total)}
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
                    <div>
                        <p className="text-sm text-slate-600 mb-3">
                            Not yet calculated. Pick a target margin and run the solver to
                            compute the land price that would meet it, holding everything else constant.
                        </p>
                        {editable && <RlvForm form={rlvForm} setForm={setRlvForm}
                                              onRun={runRlv} busy={rlvBusy} />}
                    </div>
                )}

                {rlvState === "calculated" && (
                    <div>
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
                    <div>
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
