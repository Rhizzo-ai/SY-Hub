import React, { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { CalendarDays, Plus, Trash2, Loader2, Lock } from "lucide-react";

const CATEGORY_LABELS = {
    Residential_Standard: "Residential — Standard",
    Residential_Surcharge: "Residential — Surcharge (+5%)",
    Non_Residential: "Non-Residential",
    Corporate_Flat_Rate: "Corporate Flat Rate",
};

function fmtGBP(x) {
    if (x === null || x === undefined || x === "") return "no cap";
    return "£" + new Intl.NumberFormat("en-GB").format(Number(x));
}

function StructureEditor({ initial, onCancel, onSaved }) {
    const [effectiveFrom, setEffectiveFrom] = useState(
        new Date().toISOString().slice(0, 10)
    );
    const [byCategory, setByCategory] = useState(() => {
        const out = {};
        Object.entries(initial || {}).forEach(([cat, rows]) => {
            out[cat] = rows.map((r) => ({
                band_lower: r.band_lower,
                band_upper: r.band_upper,
                rate_pct: r.rate_pct,
                notes: r.notes || "",
            }));
        });
        return out;
    });
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState(null);

    const addRow = (cat) => {
        setByCategory((p) => ({
            ...p,
            [cat]: [...(p[cat] || []), { band_lower: "0", band_upper: null, rate_pct: "0", notes: "" }],
        }));
    };
    const removeRow = (cat, idx) => {
        setByCategory((p) => ({
            ...p,
            [cat]: p[cat].filter((_, i) => i !== idx),
        }));
    };
    const updateCell = (cat, idx, field, value) => {
        setByCategory((p) => {
            const copy = [...p[cat]];
            copy[idx] = { ...copy[idx], [field]: value };
            return { ...p, [cat]: copy };
        });
    };

    const handleSave = async () => {
        setBusy(true); setErr(null);
        try {
            const payload = {};
            Object.entries(byCategory).forEach(([cat, rows]) => {
                if (!rows || rows.length === 0) return;
                payload[cat] = rows.map((r) => ({
                    band_lower: String(r.band_lower),
                    band_upper: r.band_upper === "" || r.band_upper === null ? null : String(r.band_upper),
                    rate_pct: String(r.rate_pct),
                    notes: r.notes || null,
                }));
            });
            await api.post("/v1/reference-data/sdlt-rates/new-structure", {
                effective_from: effectiveFrom,
                bands_by_category: payload,
            });
            onSaved && onSaved();
        } catch (e) {
            setErr(e.response?.data?.detail || e.message || "Save failed");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="bg-white border border-amber-300 rounded-lg p-4 mb-6" data-testid="sdlt-editor">
            <div className="flex items-center gap-3 mb-4">
                <label className="text-sm text-slate-600">Effective from</label>
                <input
                    type="date"
                    value={effectiveFrom}
                    onChange={(e) => setEffectiveFrom(e.target.value)}
                    className="border border-slate-300 rounded px-2 py-1 text-sm"
                    data-testid="sdlt-editor-effective-from"
                />
                <span className="text-xs text-slate-500 ml-auto">
                    Previous version's effective_to will be auto-set to day before.
                </span>
            </div>
            {Object.keys(initial || {}).map((cat) => (
                <div key={cat} className="mb-4">
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="font-heading text-sm font-semibold text-slate-900">
                            {CATEGORY_LABELS[cat] || cat}
                        </h3>
                        <button
                            onClick={() => addRow(cat)}
                            className="text-xs flex items-center gap-1 px-2 py-1 rounded border border-slate-200 hover:border-slate-400"
                            data-testid={`sdlt-editor-add-${cat}`}
                        >
                            <Plus size={12} /> Add band
                        </button>
                    </div>
                    <table className="w-full text-sm border border-slate-200 rounded overflow-hidden">
                        <thead className="bg-slate-50 text-xs uppercase tracking-widest text-slate-500">
                            <tr>
                                <th className="px-3 py-2 text-left w-40">Band lower (£)</th>
                                <th className="px-3 py-2 text-left w-40">Band upper (£, blank = no cap)</th>
                                <th className="px-3 py-2 text-left w-24">Rate %</th>
                                <th className="px-3 py-2 text-left">Notes</th>
                                <th className="px-3 py-2 w-10"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {(byCategory[cat] || []).map((row, idx) => (
                                <tr key={idx} className="border-t border-slate-100">
                                    <td className="px-2 py-2">
                                        <input className="border border-slate-300 rounded px-2 py-1 w-full" value={row.band_lower || ""}
                                            onChange={(e) => updateCell(cat, idx, "band_lower", e.target.value)} />
                                    </td>
                                    <td className="px-2 py-2">
                                        <input className="border border-slate-300 rounded px-2 py-1 w-full" value={row.band_upper ?? ""}
                                            onChange={(e) => updateCell(cat, idx, "band_upper", e.target.value || null)} />
                                    </td>
                                    <td className="px-2 py-2">
                                        <input className="border border-slate-300 rounded px-2 py-1 w-full" value={row.rate_pct || ""}
                                            onChange={(e) => updateCell(cat, idx, "rate_pct", e.target.value)} />
                                    </td>
                                    <td className="px-2 py-2">
                                        <input className="border border-slate-300 rounded px-2 py-1 w-full text-xs" value={row.notes || ""}
                                            onChange={(e) => updateCell(cat, idx, "notes", e.target.value)} />
                                    </td>
                                    <td className="px-2 py-2 text-right">
                                        <button onClick={() => removeRow(cat, idx)}
                                            className="text-slate-400 hover:text-rose-600"
                                            data-testid={`sdlt-editor-remove-${cat}-${idx}`}>
                                            <Trash2 size={14} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ))}

            {err && <div className="text-xs text-rose-700 mb-3" data-testid="sdlt-editor-error">{err}</div>}

            <div className="flex items-center gap-3">
                <button
                    onClick={handleSave}
                    disabled={busy}
                    className="text-sm px-3 py-2 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-40 flex items-center gap-2"
                    data-testid="sdlt-editor-save"
                >
                    {busy ? <Loader2 size={14} className="animate-spin" /> : null}
                    Publish new structure
                </button>
                <button onClick={onCancel} className="text-sm text-slate-600 hover:text-slate-900"
                    data-testid="sdlt-editor-cancel">Cancel</button>
            </div>
        </div>
    );
}

export default function SdltRatesPage() {
    const { me } = useAuth();
    const canAdmin = (me?.permissions || []).includes("system_config.admin") || me?.is_super_admin;
    const [asOf, setAsOf] = useState("");  // blank = today
    const [data, setData] = useState(null);
    const [editing, setEditing] = useState(false);
    const [error, setError] = useState(null);

    const load = async () => {
        try {
            const params = asOf ? { as_of: asOf } : {};
            const r = await api.get("/v1/reference-data/sdlt-rates", { params });
            setData(r.data);
        } catch (e) {
            setError(e.response?.data?.detail || e.message);
        }
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [asOf]);

    return (
        <AppShell>
            <div data-testid="sdlt-rates-page" className="space-y-6">
                <div className="flex items-start justify-between">
                    <div>
                        <h1 className="font-heading text-3xl font-semibold text-slate-900" data-testid="sdlt-rates-title">
                            SDLT rates
                        </h1>
                        <p className="text-sm text-slate-600 mt-1">
                            Statutory UK rates used by the appraisal engine. Append-only versioning.
                        </p>
                    </div>
                    {!canAdmin && (
                        <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-widest font-semibold text-slate-600 bg-slate-100 border border-slate-200 rounded-full px-3 py-1" data-testid="sdlt-readonly-pill">
                            <Lock size={12} /> Read-only
                        </span>
                    )}
                </div>

                <div className="flex items-end gap-3 bg-white border border-slate-200 rounded-lg p-4">
                    <div>
                        <label className="block text-xs uppercase tracking-widest text-slate-500 mb-1">
                            <CalendarDays size={12} className="inline mr-1" /> As of
                        </label>
                        <input type="date" value={asOf}
                            onChange={(e) => setAsOf(e.target.value)}
                            className="border border-slate-300 rounded px-2 py-1 text-sm"
                            data-testid="sdlt-as-of" />
                    </div>
                    <span className="text-xs text-slate-500 ml-2">
                        Leave blank for today. Historical queries pick the version active on the date.
                    </span>
                    <div className="ml-auto">
                        {canAdmin && !editing && (
                            <button
                                onClick={() => setEditing(true)}
                                className="text-sm px-3 py-2 rounded border border-slate-300 hover:border-slate-500 flex items-center gap-1"
                                data-testid="sdlt-new-structure">
                                <Plus size={14} /> New rate structure
                            </button>
                        )}
                    </div>
                </div>

                {editing && (
                    <StructureEditor
                        initial={data?.by_category || {}}
                        onCancel={() => setEditing(false)}
                        onSaved={async () => { setEditing(false); await load(); }}
                    />
                )}

                {error && <div className="rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" data-testid="sdlt-error">{error}</div>}

                {data && Object.entries(data.by_category || {}).map(([cat, rows]) => (
                    <div key={cat} className="bg-white border border-slate-200 rounded-lg overflow-hidden" data-testid={`sdlt-category-${cat}`}>
                        <div className="px-4 py-3 bg-slate-50 border-b border-slate-100">
                            <h3 className="font-heading text-sm font-semibold text-slate-900">
                                {CATEGORY_LABELS[cat] || cat}
                            </h3>
                            <p className="text-xs text-slate-500 mt-0.5">
                                {rows.length} band{rows.length === 1 ? "" : "s"} · effective from {rows[0]?.effective_from}
                            </p>
                        </div>
                        <table className="w-full text-sm">
                            <thead className="text-xs uppercase tracking-widest text-slate-500 bg-slate-50/50">
                                <tr>
                                    <th className="px-4 py-2 text-left w-44">Band</th>
                                    <th className="px-4 py-2 text-left w-24">Rate</th>
                                    <th className="px-4 py-2 text-left">Notes</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r, idx) => (
                                    <tr key={r.id} className="border-t border-slate-100" data-testid={`sdlt-band-${cat}-${idx}`}>
                                        <td className="px-4 py-2 font-mono text-xs">
                                            {fmtGBP(r.band_lower)} — {fmtGBP(r.band_upper)}
                                        </td>
                                        <td className="px-4 py-2 font-medium">{r.rate_pct}%</td>
                                        <td className="px-4 py-2 text-xs text-slate-500">{r.notes || "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ))}
            </div>
        </AppShell>
    );
}
