/**
 * HeaderTab — top-level appraisal fields (name, dates, land price, SDLT,
 * hurdles, contingency, duration, notes). Values outside unit-row LIVE
 * scope are stale-until-save on the Summary tab; Header inputs themselves
 * just edit the appraisal row.
 */
import React, { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { Field, SDLT_CATEGORIES } from "@/components/appraisal/atoms";


export default function HeaderTab({ a, editable, canFin, onSaved, onDirty }) {
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
