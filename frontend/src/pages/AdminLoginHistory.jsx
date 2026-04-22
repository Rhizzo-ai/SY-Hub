import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ChevronRight, Download, Loader2 } from "lucide-react";
import { api, API_BASE, authedFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format";

const EVENT_TYPES = [
    "Login_Success", "Login_Failed", "Logout", "MFA_Success", "MFA_Failed",
    "MFA_Enrolled", "MFA_Disabled", "Password_Change",
    "Password_Reset_Requested", "Password_Reset_Completed",
    "Account_Locked", "Account_Unlocked",
    "Session_Revoked", "Refresh_Success", "Refresh_Failed",
    "Suspicious_Activity_Detected",
];

function eventBadgeClass(ev) {
    if (ev.endsWith("_Failed") || ev === "Account_Locked" || ev === "Suspicious_Activity_Detected")
        return "bg-rose-50 text-rose-800 border-rose-200";
    if (ev.endsWith("_Success") || ev === "Account_Unlocked")
        return "bg-emerald-50 text-emerald-800 border-emerald-200";
    return "bg-slate-50 text-slate-700 border-slate-200";
}

export default function AdminLoginHistory() {
    const { id } = useParams();
    const [user, setUser] = useState(null);
    const [page, setPage] = useState(1);
    const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 50 });
    const [types, setTypes] = useState([]);
    const [successOnly, setSuccessOnly] = useState("");
    const [loading, setLoading] = useState(true);

    const load = async () => {
        setLoading(true);
        try {
            const [u, h] = await Promise.all([
                api.get(`/users/${id}`),
                api.get(`/users/${id}/login-history`, {
                    params: {
                        page, page_size: 50,
                        event_types: types.length ? types : undefined,
                        success_only: successOnly === "" ? undefined : successOnly === "true",
                    },
                    paramsSerializer: (p) => {
                        const out = [];
                        for (const [k, v] of Object.entries(p)) {
                            if (v === undefined) continue;
                            if (Array.isArray(v)) for (const i of v) out.push(`${encodeURIComponent(k)}=${encodeURIComponent(i)}`);
                            else out.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
                        }
                        return out.join("&");
                    },
                }),
            ]);
            setUser(u.data);
            setData(h.data);
        } finally { setLoading(false); }
    };
    useEffect(() => { load(); }, [id, page, types, successOnly]); // eslint-disable-line

    const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));

    const toggleType = (t) => {
        setTypes((prev) => prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]);
        setPage(1);
    };

    const exportUrl = () => {
        const params = new URLSearchParams();
        types.forEach((t) => params.append("event_types", t));
        return `${API_BASE}/users/${id}/login-history.csv?${params.toString()}`;
    };

    const onExport = async () => {
        // Cookie-based fetch — the HttpOnly access_token cookie rides
        // automatically with credentials:"include". No Authorization header.
        const res = await authedFetch(exportUrl());
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `login-history-${id}.csv`;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
    };

    if (!user) return <div className="flex items-center gap-2 text-slate-500"><Loader2 size={14} className="animate-spin" /> Loading…</div>;

    return (
        <div className="space-y-6 max-w-6xl" data-testid="admin-login-history-page">
            <div className="flex items-center gap-2 text-xs text-slate-500">
                <Link to="/users" className="inline-flex items-center gap-1 hover:text-slate-900"><ArrowLeft size={12} /> Users</Link>
                <ChevronRight size={12} />
                <Link to={`/users/${id}`} className="hover:text-slate-900 mono">{user.display_name}</Link>
                <ChevronRight size={12} />
                <span>Login history</span>
            </div>
            <header className="flex items-start justify-between">
                <div>
                    <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Users · Login history</div>
                    <h1 className="font-heading text-3xl font-bold text-slate-900 mt-1">{user.display_name}</h1>
                    <p className="text-sm text-slate-600 mt-1">Auth events across this account — append-only.</p>
                </div>
                <Button variant="outline" onClick={onExport} data-testid="export-csv">
                    <Download size={14} className="mr-1.5" /> Export CSV
                </Button>
            </header>

            <section className="bg-white border border-slate-200 rounded-lg shadow-sm">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/60 flex flex-wrap items-center gap-2">
                    <h2 className="font-heading text-sm font-semibold uppercase tracking-widest text-slate-900 mr-2">Events</h2>
                    <select value={successOnly} onChange={(e) => { setSuccessOnly(e.target.value); setPage(1); }} className="h-8 rounded-md border border-slate-300 bg-white px-2 text-sm" data-testid="filter-success">
                        <option value="">All outcomes</option>
                        <option value="true">Success only</option>
                        <option value="false">Failures only</option>
                    </select>
                    <details className="relative">
                        <summary className="cursor-pointer select-none text-xs inline-flex items-center gap-1.5 h-8 px-2 rounded-md border border-slate-300 bg-white">Event types {types.length > 0 && <span className="bg-slate-900 text-white rounded-full px-1.5 text-[10px]">{types.length}</span>}</summary>
                        <div className="absolute z-10 mt-1 right-0 bg-white border border-slate-200 rounded-md shadow-lg p-2 grid grid-cols-1 gap-0.5 min-w-[260px] max-h-80 overflow-y-auto">
                            {EVENT_TYPES.map((t) => (
                                <label key={t} className="flex items-center gap-2 text-xs px-2 py-1 rounded hover:bg-slate-50 cursor-pointer">
                                    <input type="checkbox" checked={types.includes(t)} onChange={() => toggleType(t)} />
                                    <span className="mono">{t}</span>
                                </label>
                            ))}
                        </div>
                    </details>
                    <div className="ml-auto text-xs text-slate-500 mono tabular">{loading ? <Loader2 size={12} className="inline animate-spin" /> : `${data.total} events`}</div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="login-history-table">
                        <thead className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                            <tr className="bg-slate-50 border-b border-slate-200">
                                <th className="text-left px-4 py-3">Timestamp</th>
                                <th className="text-left px-4 py-3">Event</th>
                                <th className="text-left px-4 py-3">Reason</th>
                                <th className="text-left px-4 py-3">Email</th>
                                <th className="text-left px-4 py-3">IP</th>
                                <th className="text-left px-4 py-3">Location</th>
                                <th className="text-left px-4 py-3">User agent</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.items.length === 0 && !loading && (
                                <tr><td colSpan={7} className="px-4 py-16 text-center text-slate-500">No events.</td></tr>
                            )}
                            {data.items.map((e) => (
                                <tr key={e.id} className="border-b border-slate-200" data-testid={`history-row-${e.id}`}>
                                    <td className="px-4 py-2 mono tabular text-xs text-slate-700 whitespace-nowrap">{formatDateTime(e.created_at)}</td>
                                    <td className="px-4 py-2">
                                        <span className={`inline-flex items-center border rounded-sm px-1.5 py-0.5 text-[11px] uppercase tracking-wider font-semibold ${eventBadgeClass(e.event_type)}`}>
                                            {e.event_type}
                                        </span>
                                    </td>
                                    <td className="px-4 py-2 text-xs text-slate-700">{e.failure_reason || "—"}</td>
                                    <td className="px-4 py-2 mono text-slate-700 text-xs">{e.email_attempted}</td>
                                    <td className="px-4 py-2 mono text-slate-700 text-xs">{e.ip_address}</td>
                                    <td className="px-4 py-2 text-xs text-slate-700">{e.location_country || "—"}{e.location_city ? ` · ${e.location_city}` : ""}</td>
                                    <td className="px-4 py-2 text-xs text-slate-500 truncate max-w-[280px]" title={e.user_agent}>{e.user_agent}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {totalPages > 1 && (
                    <div className="px-6 py-3 border-t border-slate-200 bg-slate-50/60 flex items-center gap-3 text-xs">
                        <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} data-testid="page-prev">Prev</Button>
                        <span className="mono tabular text-slate-600">Page {page} / {totalPages}</span>
                        <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages} data-testid="page-next">Next</Button>
                    </div>
                )}
            </section>
        </div>
    );
}
