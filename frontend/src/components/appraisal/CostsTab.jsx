/**
 * CostsTab — cost-line editor grouped by category.
 *
 * Manual lines: amount is editable input.
 * Auto lines (Percentage_Of_* / SDLT_Engine / Finance_Engine / RLV_Engine):
 *   amount is a DISPLAY value with a stale pill — server owns the value.
 *
 * NOTE (testing-agent reviewer call-out, retained intentionally):
 *   Category totals include raw r.amount even for stale auto rows.
 *   This is correct per spec — stale-until-save means the displayed value
 *   is the LAST-SAVED server value until the user saves again. Don't
 *   "fix" by zeroing auto rows or recomputing them client-side.
 */
import React, { useEffect, useMemo, useState } from "react";
import { Plus, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { D, fmtGBP } from "@/lib/appraisalMath";
import {
    StalePill, SectionHeader,
    AUTO_SOURCES, COST_CATEGORIES,
} from "@/components/appraisal/atoms";


export default function CostsTab({ a, editable, onReload, onDirty }) {
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
