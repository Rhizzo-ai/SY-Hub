/**
 * UnitsTab — the unit-mix editor.
 *
 * LIVE decimal.js transforms per row (instant, no round-trip):
 *   • gdv_per_sqft       = price_per_unit / (gia_sqm × 10.7639)
 *   • gdv_total_for_type = price_per_unit × quantity
 *   • build_total_for_type = build_cost_per_unit × quantity
 *
 * Session-aggregate LIVE totals shown as KPIs next to the server totals;
 * the server KPI gets a stale pill when live ≠ last-saved.
 */
import React, { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import {
    D, fmtGBP, liveTotalGdv, liveTotalBuild,
    pricePerSqft, totalGdvForType, totalBuildForType,
} from "@/lib/appraisalMath";
import {
    Kpi, SectionHeader, TENURES, UNIT_TYPES,
} from "@/components/appraisal/atoms";


export default function UnitsTab({ a, editable, onReload, onDirty }) {
    const [rows, setRows] = useState(() =>
        (a.units || []).map((u) => ({ ...u }))
    );

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
