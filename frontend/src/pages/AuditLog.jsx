import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Download, Loader2, X } from "lucide-react";
import { api, API_BASE, authedFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format";

const ACTIONS = [
    "Create", "Update", "Delete", "Approve", "Reject", "Reopen",
    "Login", "Logout", "Export", "Permission_Change",
    "Stage_Change", "Status_Change",
];

function actionBadge(action) {
    if (action === "Delete" || action === "Reject")
        return "bg-rose-50 text-rose-800 border-rose-200";
    if (action === "Login" || action === "Create" || action === "Approve")
        return "bg-emerald-50 text-emerald-800 border-emerald-200";
    if (action === "Permission_Change" || action === "Status_Change")
        return "bg-amber-50 text-amber-800 border-amber-200";
    return "bg-slate-50 text-slate-700 border-slate-200";
}

export default function AuditLog() {
    const [searchParams, setSearchParams] = useSearchParams();
    const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 50 });
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState(null);

    const page = Number(searchParams.get("page") || 1);
    const filters = useMemo(() => ({
        resource_type: searchParams.get("resource_type") || "",
        action: searchParams.getAll("action"),
        date_from: searchParams.get("date_from") || "",
        date_to: searchParams.get("date_to") || "",
    }), [searchParams]);

    const load = async () => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            params.set("page", String(page));
            params.set("page_size", "50");
            if (filters.resource_type) params.set("resource_type", filters.resource_type);
            if (filters.date_from) params.set("date_from", filters.date_from);
            if (filters.date_to) params.set("date_to", filters.date_to);
            filters.action.forEach((a) => params.append("action", a));
            const r = await api.get(`/audit?${params.toString()}`);
            setData(r.data);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [searchParams]);

    const toggleAction = (act) => {
        const next = new URLSearchParams(searchParams);
        const curr = next.getAll("action");
        next.delete("action");
        if (curr.includes(act)) {
            curr.filter((a) => a !== act).forEach((a) => next.append("action", a));
        } else {
            [...curr, act].forEach((a) => next.append("action", a));
        }
        next.set("page", "1");
        setSearchParams(next);
    };

    const exportCsv = async () => {
        const params = new URLSearchParams();
        if (filters.resource_type) params.set("resource_type", filters.resource_type);
        if (filters.date_from) params.set("date_from", filters.date_from);
        if (filters.date_to) params.set("date_to", filters.date_to);
        filters.action.forEach((a) => params.append("action", a));
        const res = await authedFetch(`${API_BASE}/audit/export.csv?${params.toString()}`);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "audit-log.csv";
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
    };

    const totalPages = Math.max(1, Math.ceil(data.total / 50));

    return (
        <div className="px-6 py-8 max-w-7xl mx-auto" data-testid="audit-log-page">
            <div className="flex items-baseline justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Audit Log</h1>
                    <p className="text-sm text-slate-500 mt-1">
                        Forensic record of every significant platform write. Append-only.
                    </p>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={exportCsv}
                    data-testid="audit-export-csv"
                >
                    <Download className="w-4 h-4 mr-2" />
                    Export CSV
                </Button>
            </div>

            {/* Filters */}
            <div className="mb-4 border rounded-md p-4 bg-white">
                <div className="grid grid-cols-3 gap-3 mb-3">
                    <div>
                        <label className="text-xs font-medium text-slate-600">Resource type</label>
                        <Input
                            value={filters.resource_type}
                            onChange={(e) => {
                                const n = new URLSearchParams(searchParams);
                                if (e.target.value) n.set("resource_type", e.target.value);
                                else n.delete("resource_type");
                                n.set("page", "1");
                                setSearchParams(n);
                            }}
                            placeholder="entities, users, user_sessions…"
                            data-testid="audit-filter-resource-type"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-600">From</label>
                        <Input
                            type="datetime-local"
                            value={filters.date_from}
                            onChange={(e) => {
                                const n = new URLSearchParams(searchParams);
                                if (e.target.value) n.set("date_from", e.target.value);
                                else n.delete("date_from");
                                n.set("page", "1");
                                setSearchParams(n);
                            }}
                            data-testid="audit-filter-date-from"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-600">To</label>
                        <Input
                            type="datetime-local"
                            value={filters.date_to}
                            onChange={(e) => {
                                const n = new URLSearchParams(searchParams);
                                if (e.target.value) n.set("date_to", e.target.value);
                                else n.delete("date_to");
                                n.set("page", "1");
                                setSearchParams(n);
                            }}
                            data-testid="audit-filter-date-to"
                        />
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    {ACTIONS.map((a) => {
                        const on = filters.action.includes(a);
                        return (
                            <button
                                key={a}
                                onClick={() => toggleAction(a)}
                                className={`text-xs px-2 py-1 rounded-full border transition ${
                                    on
                                        ? "bg-slate-900 text-white border-slate-900"
                                        : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                                }`}
                                data-testid={`audit-filter-action-${a}`}
                            >
                                {a}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Table */}
            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                </div>
            ) : (
                <div className="border rounded-md overflow-hidden bg-white">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wide">
                            <tr>
                                <th className="text-left p-3 w-48">Timestamp</th>
                                <th className="text-left p-3">Actor</th>
                                <th className="text-left p-3">Action</th>
                                <th className="text-left p-3">Resource</th>
                                <th className="text-left p-3">Summary</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.items.length === 0 && (
                                <tr>
                                    <td colSpan={5} className="p-12 text-center text-slate-400" data-testid="audit-empty">
                                        No audit events for current filters.
                                    </td>
                                </tr>
                            )}
                            {data.items.map((row) => (
                                <tr
                                    key={row.id}
                                    className="border-t hover:bg-slate-50 cursor-pointer"
                                    onClick={() => setSelected(row)}
                                    data-testid={`audit-row-${row.id}`}
                                >
                                    <td className="p-3 text-slate-500 font-mono text-xs">
                                        {formatDateTime(row.created_at)}
                                    </td>
                                    <td className="p-3 text-slate-700">
                                        {row.actor_name || row.actor_email || (
                                            <span className="text-slate-400 italic">System</span>
                                        )}
                                    </td>
                                    <td className="p-3">
                                        <span
                                            className={`text-xs px-2 py-0.5 rounded-full border ${actionBadge(row.action)}`}
                                        >
                                            {row.action}
                                        </span>
                                    </td>
                                    <td className="p-3 text-slate-600 font-mono text-xs">
                                        <span className="text-slate-500">{row.resource_type}</span>
                                        <span className="text-slate-300 mx-1">/</span>
                                        <span>{String(row.resource_id).slice(0, 8)}</span>
                                    </td>
                                    <td className="p-3 text-slate-700">{row.summary}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {data.total > 0 && (
                        <div className="border-t p-3 flex items-center justify-between text-xs text-slate-500">
                            <span data-testid="audit-total">
                                {data.total} row{data.total === 1 ? "" : "s"}
                            </span>
                            <div className="flex items-center gap-2">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={page <= 1}
                                    onClick={() => {
                                        const n = new URLSearchParams(searchParams);
                                        n.set("page", String(page - 1));
                                        setSearchParams(n);
                                    }}
                                >
                                    Prev
                                </Button>
                                <span>
                                    Page {page} of {totalPages}
                                </span>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={page >= totalPages}
                                    onClick={() => {
                                        const n = new URLSearchParams(searchParams);
                                        n.set("page", String(page + 1));
                                        setSearchParams(n);
                                    }}
                                >
                                    Next
                                </Button>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {selected && <AuditDetailModal row={selected} onClose={() => setSelected(null)} />}
        </div>
    );
}


function AuditDetailModal({ row, onClose }) {
    return (
        <div
            className="fixed inset-0 bg-slate-900/40 flex items-start justify-center p-6 z-50 overflow-y-auto"
            onClick={onClose}
            data-testid="audit-detail-modal"
        >
            <div
                className="bg-white rounded-lg shadow-xl max-w-3xl w-full p-6 my-8"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-start justify-between mb-4">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">
                            {row.action} · {row.resource_type}
                        </h2>
                        <p className="text-xs text-slate-500 font-mono mt-1">{row.id}</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-slate-400 hover:text-slate-600"
                        data-testid="audit-detail-close"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {row.impersonator_user_id && (
                    <div className="mb-4 p-3 rounded-md bg-amber-50 border border-amber-200 text-amber-900 text-sm">
                        Acted under impersonation by <b>{row.impersonator_name}</b>.
                    </div>
                )}

                <dl className="grid grid-cols-[140px_1fr] gap-y-2 text-sm mb-4">
                    <dt className="text-slate-500">Timestamp</dt>
                    <dd className="font-mono text-xs text-slate-700">{formatDateTime(row.created_at)}</dd>

                    <dt className="text-slate-500">Actor</dt>
                    <dd>
                        {row.actor_name || row.actor_email || <span className="italic text-slate-400">System</span>}
                    </dd>

                    <dt className="text-slate-500">Resource ID</dt>
                    <dd className="font-mono text-xs">{row.resource_id}</dd>

                    {row.entity_id && (
                        <>
                            <dt className="text-slate-500">Entity</dt>
                            <dd className="font-mono text-xs">{row.entity_id}</dd>
                        </>
                    )}

                    <dt className="text-slate-500">IP</dt>
                    <dd className="font-mono text-xs">{row.ip_address || "—"}</dd>

                    <dt className="text-slate-500">User Agent</dt>
                    <dd className="text-xs text-slate-600 break-all">{row.user_agent || "—"}</dd>

                    <dt className="text-slate-500">Session</dt>
                    <dd className="font-mono text-xs">{row.session_id || "—"}</dd>
                </dl>

                {row.field_changes.length > 0 && (
                    <section className="mb-4">
                        <h3 className="text-sm font-semibold text-slate-700 mb-2">Field changes</h3>
                        <table className="w-full text-xs border rounded-md overflow-hidden">
                            <thead className="bg-slate-50 text-slate-600">
                                <tr>
                                    <th className="text-left p-2">Field</th>
                                    <th className="text-left p-2">Old</th>
                                    <th className="text-left p-2">New</th>
                                </tr>
                            </thead>
                            <tbody>
                                {row.field_changes.map((c, i) => (
                                    <tr key={i} className="border-t">
                                        <td className="p-2 font-mono">{c.field}</td>
                                        <td className="p-2 text-slate-600 break-all">{JSON.stringify(c.old)}</td>
                                        <td className="p-2 text-slate-600 break-all">{JSON.stringify(c.new)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </section>
                )}

                {Object.keys(row.metadata || {}).length > 0 && (
                    <section>
                        <h3 className="text-sm font-semibold text-slate-700 mb-2">Metadata</h3>
                        <pre className="text-xs bg-slate-50 p-3 rounded-md border overflow-x-auto">
                            {JSON.stringify(row.metadata, null, 2)}
                        </pre>
                    </section>
                )}
            </div>
        </div>
    );
}
