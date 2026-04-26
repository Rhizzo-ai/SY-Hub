import React, { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import { CheckCircle2, X, Loader2 } from "lucide-react";

const TYPES = [
    "Approval_Requested", "Approval_Decision", "Budget_Variance",
    "Programme_Alert", "Document_Shared", "Mention", "Assignment",
    "System_Announcement", "Integration_Error", "Security_Alert",
    "Deadline_Approaching", "Task_Overdue", "Xero_Sync_Error",
    "Insurance_Expiry", "Certificate_Expiry",
];
const PRIORITIES = ["Low", "Normal", "High", "Critical"];
const PRIORITY_BG = {
    Critical: "bg-rose-100 text-rose-700 border-rose-200",
    High: "bg-amber-100 text-amber-800 border-amber-200",
    Normal: "bg-slate-100 text-slate-700 border-slate-200",
    Low: "bg-slate-50 text-slate-500 border-slate-100",
};

function formatDate(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString();
}

export default function NotificationsPage() {
    const [filters, setFilters] = useState({
        type: "", priority: "", is_read: "", is_dismissed: "false",
    });
    const [page, setPage] = useState(1);
    const pageSize = 25;
    const [data, setData] = useState({ items: [], total: 0 });
    const [busyId, setBusyId] = useState(null);
    const [loading, setLoading] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const params = { page, page_size: pageSize };
            if (filters.type) params.type = filters.type;
            if (filters.priority) params.priority = filters.priority;
            if (filters.is_read !== "") params.is_read = filters.is_read;
            if (filters.is_dismissed !== "") params.is_dismissed = filters.is_dismissed;
            const r = await api.get("/v1/notifications", { params });
            setData(r.data);
        } finally { setLoading(false); }
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, filters]);

    const markRead = async (id) => {
        setBusyId(id);
        try { await api.patch(`/v1/notifications/${id}/read`); await load(); }
        finally { setBusyId(null); }
    };
    const dismiss = async (id) => {
        setBusyId(id);
        try { await api.patch(`/v1/notifications/${id}/dismiss`); await load(); }
        finally { setBusyId(null); }
    };

    const totalPages = Math.max(1, Math.ceil(data.total / pageSize));

    return (
        <AppShell>
            <div data-testid="notifications-page" className="space-y-6">
                <div>
                    <h1 className="font-heading text-3xl font-semibold text-slate-900" data-testid="notifications-page-title">
                        Notifications
                    </h1>
                    <p className="text-sm text-slate-600 mt-1">
                        Full inbox. Filter by type, priority, read state, dismissal.
                    </p>
                </div>

                <div className="flex flex-wrap gap-3 items-end bg-white border border-slate-200 rounded-lg p-4">
                    <div>
                        <label className="block text-xs uppercase tracking-widest text-slate-500 mb-1">Type</label>
                        <select
                            className="border border-slate-300 rounded px-2 py-1 text-sm"
                            value={filters.type}
                            onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, type: e.target.value })); }}
                            data-testid="notifications-filter-type"
                        >
                            <option value="">All</option>
                            {TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs uppercase tracking-widest text-slate-500 mb-1">Priority</label>
                        <select
                            className="border border-slate-300 rounded px-2 py-1 text-sm"
                            value={filters.priority}
                            onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, priority: e.target.value })); }}
                            data-testid="notifications-filter-priority"
                        >
                            <option value="">All</option>
                            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs uppercase tracking-widest text-slate-500 mb-1">Read</label>
                        <select
                            className="border border-slate-300 rounded px-2 py-1 text-sm"
                            value={filters.is_read}
                            onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, is_read: e.target.value })); }}
                            data-testid="notifications-filter-read"
                        >
                            <option value="">All</option>
                            <option value="false">Unread</option>
                            <option value="true">Read</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs uppercase tracking-widest text-slate-500 mb-1">Dismissed</label>
                        <select
                            className="border border-slate-300 rounded px-2 py-1 text-sm"
                            value={filters.is_dismissed}
                            onChange={(e) => { setPage(1); setFilters((f) => ({ ...f, is_dismissed: e.target.value })); }}
                            data-testid="notifications-filter-dismissed"
                        >
                            <option value="">All</option>
                            <option value="false">Active</option>
                            <option value="true">Dismissed</option>
                        </select>
                    </div>
                    <div className="ml-auto text-xs text-slate-500" data-testid="notifications-total">
                        {data.total} total
                    </div>
                </div>

                <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-xs uppercase tracking-widest text-slate-500">
                            <tr>
                                <th className="px-4 py-2 text-left">Title</th>
                                <th className="px-4 py-2 text-left w-32">Type</th>
                                <th className="px-4 py-2 text-left w-28">Priority</th>
                                <th className="px-4 py-2 text-left w-28">Status</th>
                                <th className="px-4 py-2 text-left w-44">When</th>
                                <th className="px-4 py-2 text-left w-32"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && (
                                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                                    <Loader2 size={16} className="inline animate-spin mr-2" />Loading…
                                </td></tr>
                            )}
                            {!loading && data.items.length === 0 && (
                                <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500" data-testid="notifications-empty">
                                    No notifications match the current filters.
                                </td></tr>
                            )}
                            {data.items.map((n) => (
                                <tr key={n.id} className={`border-t border-slate-100 ${n.is_read ? "" : "bg-slate-50"}`} data-testid={`notification-row-${n.id}`}>
                                    <td className="px-4 py-3 align-top">
                                        <div className={`text-sm ${n.is_read ? "text-slate-700" : "font-medium text-slate-900"}`}>
                                            {n.title}
                                        </div>
                                        <div className="text-xs text-slate-500 line-clamp-2 mt-0.5">{n.body}</div>
                                        {n.action_url && (
                                            <a href={n.action_url} className="text-xs text-blue-600 hover:underline mt-1 inline-block" data-testid={`notification-action-${n.id}`}>
                                                {n.action_label || "View"}
                                            </a>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 align-top text-xs text-slate-500">
                                        {n.notification_type.replace(/_/g, " ")}
                                    </td>
                                    <td className="px-4 py-3 align-top">
                                        <span className={`inline-block text-[11px] uppercase tracking-widest px-2 py-0.5 rounded border ${PRIORITY_BG[n.priority]}`}>
                                            {n.priority}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 align-top text-xs text-slate-500">
                                        {n.is_dismissed ? "Dismissed" : n.is_read ? "Read" : "Unread"}
                                    </td>
                                    <td className="px-4 py-3 align-top text-xs text-slate-500 font-mono">
                                        {formatDate(n.created_at)}
                                    </td>
                                    <td className="px-4 py-3 align-top">
                                        <div className="flex items-center gap-2">
                                            {!n.is_read && (
                                                <button
                                                    onClick={() => markRead(n.id)}
                                                    disabled={busyId === n.id}
                                                    className="text-xs px-2 py-1 rounded border border-slate-200 hover:border-slate-400 text-slate-700 flex items-center gap-1"
                                                    data-testid={`notification-mark-read-${n.id}`}
                                                >
                                                    <CheckCircle2 size={12} />Read
                                                </button>
                                            )}
                                            {!n.is_dismissed && (
                                                <button
                                                    onClick={() => dismiss(n.id)}
                                                    disabled={busyId === n.id}
                                                    className="text-xs px-2 py-1 rounded border border-slate-200 hover:border-slate-400 text-slate-700 flex items-center gap-1"
                                                    data-testid={`notification-dismiss-${n.id}`}
                                                >
                                                    <X size={12} />Dismiss
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {totalPages > 1 && (
                    <div className="flex items-center justify-between" data-testid="notifications-pager">
                        <span className="text-xs text-slate-500">Page {page} of {totalPages}</span>
                        <div className="flex gap-2">
                            <button
                                onClick={() => setPage((p) => Math.max(1, p - 1))}
                                disabled={page <= 1}
                                className="text-xs px-3 py-1 rounded border border-slate-200 hover:border-slate-400 disabled:opacity-40"
                                data-testid="notifications-pager-prev"
                            >Previous</button>
                            <button
                                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                                disabled={page >= totalPages}
                                className="text-xs px-3 py-1 rounded border border-slate-200 hover:border-slate-400 disabled:opacity-40"
                                data-testid="notifications-pager-next"
                            >Next</button>
                        </div>
                    </div>
                )}
            </div>
        </AppShell>
    );
}
