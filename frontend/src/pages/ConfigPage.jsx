import React, { useEffect, useState, useMemo } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Lock, RefreshCw, ChevronDown, ChevronRight, Loader2, Save } from "lucide-react";

const CATEGORY_LABELS = {
    Finance: "Finance", Appraisal: "Appraisal", Budget: "Budget",
    CashFlow: "Cash Flow", Programme: "Programme", Document: "Document",
    Security: "Security", Integration: "Integration", Notification: "Notification",
    Reporting: "Reporting", Audit: "Audit", System: "System",
};

function formatRelative(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`;
    return d.toLocaleDateString();
}

function ConfigRow({ row, canEdit, onSave, onRestore }) {
    const [editing, setEditing] = useState(false);
    const [draft, setDraft] = useState(row.raw_value);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState(null);

    useEffect(() => { setDraft(row.raw_value); }, [row.raw_value]);

    const placeholder = useMemo(() => {
        if (row.value_type === "Boolean") return "true / false";
        if (row.value_type === "JSON") return "[…] or {…}";
        if (row.value_type === "Date") return "YYYY-MM-DD";
        return "";
    }, [row.value_type]);

    const dirty = editing && draft !== row.raw_value;

    const handleSave = async () => {
        setBusy(true); setErr(null);
        try {
            // Coerce typed input.
            let value = draft;
            if (row.value_type === "Integer") value = parseInt(draft, 10);
            else if (row.value_type === "Decimal") value = draft;  // server validates
            else if (row.value_type === "Boolean") value = draft === "true" || draft === true;
            else if (row.value_type === "JSON") value = draft;
            await onSave(row.config_key, value);
            setEditing(false);
        } catch (e) {
            setErr(e.response?.data?.detail || e.message || "Save failed");
        } finally {
            setBusy(false);
        }
    };

    return (
        <tr className="border-t border-slate-100 hover:bg-slate-50" data-testid={`config-row-${row.config_key}`}>
            <td className="px-4 py-3 align-top">
                <div className="flex items-center gap-2">
                    {row.is_system_locked && (
                        <Lock size={12} className="text-slate-400" data-testid="lock-icon" />
                    )}
                    <code className="text-xs font-mono text-slate-900">{row.config_key}</code>
                </div>
                <p className="text-xs text-slate-500 mt-1 max-w-md">{row.description}</p>
            </td>
            <td className="px-4 py-3 align-top w-72">
                {editing && canEdit && !row.is_system_locked ? (
                    <div className="flex flex-col gap-1">
                        {row.value_type === "Boolean" ? (
                            <select
                                value={String(draft)}
                                onChange={(e) => setDraft(e.target.value)}
                                className="border border-slate-300 rounded px-2 py-1 text-sm w-full"
                                data-testid={`config-input-${row.config_key}`}
                            >
                                <option value="true">true</option>
                                <option value="false">false</option>
                            </select>
                        ) : row.value_type === "JSON" ? (
                            <textarea
                                rows={3}
                                value={draft}
                                onChange={(e) => setDraft(e.target.value)}
                                className="font-mono text-xs border border-slate-300 rounded px-2 py-1 w-full"
                                placeholder={placeholder}
                                data-testid={`config-input-${row.config_key}`}
                            />
                        ) : (
                            <input
                                type={row.value_type === "Integer" || row.value_type === "Decimal" ? "text" : "text"}
                                value={draft}
                                onChange={(e) => setDraft(e.target.value)}
                                className="border border-slate-300 rounded px-2 py-1 text-sm w-full"
                                placeholder={placeholder}
                                data-testid={`config-input-${row.config_key}`}
                            />
                        )}
                        <div className="flex items-center gap-2">
                            <button
                                onClick={handleSave}
                                disabled={!dirty || busy}
                                className="text-xs px-2 py-1 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
                                data-testid={`config-save-${row.config_key}`}
                            >
                                {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                                Save
                            </button>
                            <button
                                onClick={() => { setEditing(false); setDraft(row.raw_value); setErr(null); }}
                                className="text-xs text-slate-500 hover:text-slate-700"
                                data-testid={`config-cancel-${row.config_key}`}
                            >Cancel</button>
                        </div>
                        {err && <div className="text-xs text-rose-700">{err}</div>}
                    </div>
                ) : (
                    <button
                        onClick={() => canEdit && !row.is_system_locked && setEditing(true)}
                        disabled={!canEdit || row.is_system_locked}
                        className={`text-sm font-mono px-2 py-1 rounded border w-full text-left ${canEdit && !row.is_system_locked ? "border-slate-200 hover:border-slate-400 bg-white" : "border-slate-100 bg-slate-50 text-slate-500 cursor-not-allowed"}`}
                        data-testid={`config-display-${row.config_key}`}
                    >
                        {row.raw_value}
                    </button>
                )}
            </td>
            <td className="px-4 py-3 align-top text-xs text-slate-500">
                <div>{row.value_type}</div>
                {!row.is_at_default && (
                    <div className="mt-1 text-amber-700 font-medium">modified</div>
                )}
            </td>
            <td className="px-4 py-3 align-top text-xs text-slate-500">
                <div>{formatRelative(row.last_changed_at)}</div>
            </td>
            <td className="px-4 py-3 align-top w-32">
                {canEdit && !row.is_system_locked && !row.is_at_default && (
                    <button
                        onClick={() => onRestore(row.config_key)}
                        className="text-xs px-2 py-1 rounded border border-slate-200 hover:border-slate-400 text-slate-700 flex items-center gap-1"
                        data-testid={`config-restore-${row.config_key}`}
                    >
                        <RefreshCw size={12} /> Restore
                    </button>
                )}
            </td>
        </tr>
    );
}

export default function ConfigPage() {
    const { me } = useAuth();
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [open, setOpen] = useState({});  // category → bool
    const isSuperAdmin = me?.is_super_admin || (me?.permissions || []).includes("system_config.admin");

    const load = async () => {
        try {
            const r = await api.get("/v1/system-config");
            setData(r.data);
            // Default open all categories.
            setOpen((prev) => {
                const out = { ...prev };
                Object.keys(r.data.by_category).forEach((c) => {
                    if (out[c] === undefined) out[c] = true;
                });
                return out;
            });
        } catch (e) {
            setError(e.response?.data?.detail || e.message || "Load failed");
        }
    };

    useEffect(() => { load(); }, []);

    const handleSave = async (key, value) => {
        await api.put(`/v1/system-config/${key}`, { value });
        await load();
    };
    const handleRestore = async (key) => {
        await api.post(`/v1/system-config/${key}/restore`);
        await load();
    };

    return (
        <AppShell>
            <div data-testid="config-page" className="space-y-6">
                <div className="flex items-start justify-between">
                    <div>
                        <h1 className="font-heading text-3xl font-semibold text-slate-900" data-testid="config-page-title">
                            System Configuration
                        </h1>
                        <p className="text-sm text-slate-600 mt-1 max-w-3xl">
                            Runtime-tunable settings. Super-admin can edit; other roles can view.
                            Locked rows cannot be changed via the UI or API.
                        </p>
                    </div>
                    {!isSuperAdmin && (
                        <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-widest font-semibold text-slate-600 bg-slate-100 border border-slate-200 rounded-full px-3 py-1" data-testid="config-readonly-pill">
                            <Lock size={12} /> Read-only
                        </span>
                    )}
                </div>

                {error && (
                    <div className="rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" data-testid="config-error">
                        {error}
                    </div>
                )}

                {data && Object.entries(data.by_category)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([category, rows]) => (
                        <div key={category} className="bg-white border border-slate-200 rounded-lg overflow-hidden" data-testid={`config-category-${category}`}>
                            <button
                                onClick={() => setOpen((p) => ({ ...p, [category]: !p[category] }))}
                                className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 text-left"
                                data-testid={`config-category-toggle-${category}`}
                            >
                                <div className="flex items-center gap-2">
                                    {open[category] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                    <span className="font-heading text-sm font-semibold text-slate-900">
                                        {CATEGORY_LABELS[category] || category}
                                    </span>
                                    <span className="text-xs text-slate-500">({rows.length} keys)</span>
                                </div>
                            </button>
                            {open[category] && (
                                <table className="w-full text-sm">
                                    <thead className="bg-slate-50 text-xs uppercase tracking-widest text-slate-500">
                                        <tr>
                                            <th className="px-4 py-2 text-left">Key</th>
                                            <th className="px-4 py-2 text-left">Value</th>
                                            <th className="px-4 py-2 text-left">Type</th>
                                            <th className="px-4 py-2 text-left">Last changed</th>
                                            <th className="px-4 py-2 text-left"></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rows.map((r) => (
                                            <ConfigRow
                                                key={r.config_key}
                                                row={r}
                                                canEdit={isSuperAdmin}
                                                onSave={handleSave}
                                                onRestore={handleRestore}
                                            />
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    ))}
            </div>
        </AppShell>
    );
}
