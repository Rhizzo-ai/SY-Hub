import React, { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Lock, Save, Loader2, Link as LinkIcon } from "lucide-react";

function formatRelative(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return d.toLocaleDateString();
}

function SettingRow({ row, canEdit, onSave }) {
    const [editing, setEditing] = useState(false);
    const [value, setValue] = useState(row.setting_value);
    const [description, setDescription] = useState(row.description);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState(null);

    useEffect(() => { setValue(row.setting_value); setDescription(row.description); }, [row]);

    const handleSave = async () => {
        setBusy(true); setErr(null);
        try {
            await onSave(row.id, { value, description });
            setEditing(false);
        } catch (e) {
            setErr(e.response?.data?.detail || e.message || "Save failed");
        } finally { setBusy(false); }
    };

    return (
        <tr className="border-t border-slate-100 hover:bg-slate-50" data-testid={`setting-row-${row.setting_key}`}>
            <td className="px-4 py-3 align-top">
                <code className="text-xs font-mono text-slate-900">{row.setting_key}</code>
                <div className="text-xs text-slate-500 mt-1 max-w-md">
                    {editing && canEdit ? (
                        <input value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            className="border border-slate-300 rounded px-2 py-1 text-xs w-full"
                            data-testid={`setting-description-${row.setting_key}`} />
                    ) : row.description}
                </div>
            </td>
            <td className="px-4 py-3 align-top w-48">
                {editing && canEdit ? (
                    <div className="flex flex-col gap-1">
                        <input value={value}
                            onChange={(e) => setValue(e.target.value)}
                            className="border border-slate-300 rounded px-2 py-1 text-sm font-mono"
                            data-testid={`setting-value-${row.setting_key}`} />
                        <div className="flex items-center gap-2">
                            <button onClick={handleSave} disabled={busy}
                                className="text-xs px-2 py-1 rounded bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-40 flex items-center gap-1"
                                data-testid={`setting-save-${row.setting_key}`}>
                                {busy ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                                Save
                            </button>
                            <button onClick={() => { setEditing(false); setValue(row.setting_value); setDescription(row.description); setErr(null); }}
                                className="text-xs text-slate-500 hover:text-slate-700"
                                data-testid={`setting-cancel-${row.setting_key}`}>Cancel</button>
                        </div>
                        {err && <div className="text-xs text-rose-700">{err}</div>}
                    </div>
                ) : (
                    <button onClick={() => canEdit && setEditing(true)}
                        disabled={!canEdit}
                        className={`text-sm font-mono px-2 py-1 rounded border w-full text-left ${canEdit ? "border-slate-200 hover:border-slate-400 bg-white" : "border-slate-100 bg-slate-50 text-slate-500 cursor-not-allowed"}`}
                        data-testid={`setting-display-${row.setting_key}`}
                        data-readonly={!canEdit ? "true" : "false"}
                        data-setting-value={row.setting_value}>
                        {row.setting_value}
                    </button>
                )}
            </td>
            <td className="px-4 py-3 align-top text-xs text-slate-500">
                {row.setting_type}
            </td>
            <td className="px-4 py-3 align-top text-xs text-slate-500">
                {formatRelative(row.updated_at)}
            </td>
        </tr>
    );
}

export default function AppraisalDefaultsPage() {
    const { me } = useAuth();
    const canAdmin = (me?.permissions || []).includes("system_config.admin") || me?.is_super_admin;
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);

    const load = async () => {
        try {
            const r = await api.get("/v1/reference-data/appraisal-defaults");
            setData(r.data);
        } catch (e) {
            setError(e.response?.data?.detail || e.message);
        }
    };

    useEffect(() => { load(); }, []);

    const handleSave = async (id, { value, description }) => {
        await api.put(`/v1/reference-data/appraisal-defaults/${id}`, { value, description });
        await load();
    };

    return (
        <AppShell>
            <div data-testid="appraisal-defaults-page" className="space-y-6">
                <div className="flex items-start justify-between">
                    <div>
                        <h1 className="font-heading text-3xl font-semibold text-slate-900" data-testid="appraisal-defaults-title">
                            Appraisal default settings
                        </h1>
                        <p className="text-sm text-slate-600 mt-1 max-w-3xl">
                            Default percentages the appraisal engine uses when modelling new deals.
                            Tenant-scoped — shown values apply to the tenant you're signed in to.
                            Changes here apply only to new appraisals; existing appraisals keep their
                            original values.
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        {!canAdmin && (
                            <span className="inline-flex items-center gap-1 text-[11px] uppercase tracking-widest font-semibold text-slate-600 bg-slate-100 border border-slate-200 rounded-full px-3 py-1" data-testid="settings-readonly-pill">
                                <Lock size={12} /> Read-only
                            </span>
                        )}
                        <a href="/audit?resource_type=appraisal_default_settings"
                            className="text-xs text-slate-600 hover:text-slate-900 flex items-center gap-1"
                            data-testid="settings-audit-link">
                            <LinkIcon size={12} /> Change log
                        </a>
                    </div>
                </div>

                {error && <div className="rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700" data-testid="settings-error">{error}</div>}

                {data && Object.entries(data.by_project_type || {}).map(([scope, rows]) => (
                    <div key={scope} className="bg-white border border-slate-200 rounded-lg overflow-hidden" data-testid={`settings-scope-${scope}`}>
                        <div className="px-4 py-3 bg-slate-50 border-b border-slate-100">
                            <h3 className="font-heading text-sm font-semibold text-slate-900">
                                {scope === "All" ? "All project types" : scope.replace(/_/g, " ")}
                            </h3>
                            <p className="text-xs text-slate-500 mt-0.5">
                                {rows.length} setting{rows.length === 1 ? "" : "s"}
                            </p>
                        </div>
                        <table className="w-full text-sm">
                            <thead className="text-xs uppercase tracking-widest text-slate-500 bg-slate-50/50">
                                <tr>
                                    <th className="px-4 py-2 text-left">Key · Description</th>
                                    <th className="px-4 py-2 text-left w-48">Value</th>
                                    <th className="px-4 py-2 text-left w-28">Type</th>
                                    <th className="px-4 py-2 text-left w-28">Updated</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r) => (
                                    <SettingRow key={r.id} row={r} canEdit={canAdmin} onSave={handleSave} />
                                ))}
                            </tbody>
                        </table>
                    </div>
                ))}
            </div>
        </AppShell>
    );
}
