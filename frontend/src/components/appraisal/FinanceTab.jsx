/**
 * FinanceTab — debt / equity facility editor.
 *
 * Interest total and fee total are STALE until save (server runs the
 * finance engine on recompute). All numeric-output columns carry a
 * stale pill.
 */
import React, { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { fmtGBP } from "@/lib/appraisalMath";
import {
    StalePill, SectionHeader, FINANCE_TYPES, INTEREST_MODES,
} from "@/components/appraisal/atoms";


export default function FinanceTab({ a, editable, onReload, onDirty }) {
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
