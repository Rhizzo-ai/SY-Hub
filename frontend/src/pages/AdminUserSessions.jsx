import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ChevronRight, Laptop, Loader2, MapPin, X } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { toast } from "sonner";

function timeAgo(iso) {
    if (!iso) return "—";
    const diff = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
    return `${Math.round(diff / 86400)} d ago`;
}
function redactIp(ip) {
    if (!ip) return "—";
    if (ip.includes(":")) return ip.split(":").slice(0, 3).join(":") + "::*";
    const p = ip.split(".");
    return p.length === 4 ? `${p[0]}.${p[1]}.${p[2]}.*` : ip;
}

export default function AdminUserSessions() {
    const { id } = useParams();
    const [user, setUser] = useState(null);
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const [u, s] = await Promise.all([
                api.get(`/users/${id}`),
                api.get(`/users/${id}/sessions`),
            ]);
            setUser(u.data); setRows(s.data);
        } finally { setLoading(false); }
    };
    useEffect(() => { load(); }, [id]); // eslint-disable-line

    const onRevokeAll = async () => {
        setBusy(true);
        try {
            await api.post(`/users/${id}/sessions/revoke-all`);
            toast.success("All sessions revoked and user notified");
            await load();
        } catch (e) {
            toast.error(e.friendlyMessage || "Failed");
        } finally { setBusy(false); }
    };

    if (loading && !user) return <div className="flex items-center gap-2 text-slate-500"><Loader2 size={14} className="animate-spin" /> Loading…</div>;
    if (!user) return <div className="text-slate-600">User not found.</div>;

    const active = rows.filter((r) => !r.revoked_at);

    return (
        <div className="space-y-6 max-w-5xl" data-testid="admin-sessions-page">
            <div className="flex items-center gap-2 text-xs text-slate-500">
                <Link to="/users" className="inline-flex items-center gap-1 hover:text-slate-900"><ArrowLeft size={12} /> Users</Link>
                <ChevronRight size={12} />
                <Link to={`/users/${id}`} className="hover:text-slate-900 mono">{user.display_name}</Link>
                <ChevronRight size={12} />
                <span>Sessions</span>
            </div>
            <header>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Users · Sessions</div>
                <h1 className="font-heading text-3xl font-bold text-slate-900 mt-1">{user.display_name}'s sessions</h1>
                <p className="text-sm text-slate-600 mt-1">All browsers or devices signed into this account.</p>
            </header>

            <section className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/60 flex items-center gap-3">
                    <h2 className="font-heading text-sm font-semibold uppercase tracking-widest text-slate-900">Sessions</h2>
                    <div className="ml-auto text-xs text-slate-500 mono tabular">
                        {active.length} active · {rows.length} total
                    </div>
                    {active.length > 0 && (
                        <Button
                            variant="outline" size="sm"
                            onClick={onRevokeAll} disabled={busy}
                            className="text-rose-700 border-rose-200 hover:bg-rose-50"
                            data-testid="admin-revoke-all-button"
                        >
                            {busy ? <Loader2 size={12} className="animate-spin mr-1" /> : <X size={12} className="mr-1" />}
                            Revoke all sessions
                        </Button>
                    )}
                </div>
                <table className="w-full text-sm">
                    <thead className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                        <tr className="bg-slate-50 border-b border-slate-200">
                            <th className="text-left px-4 py-3">Device</th>
                            <th className="text-left px-4 py-3">Location</th>
                            <th className="text-left px-4 py-3">IP</th>
                            <th className="text-left px-4 py-3">Last active</th>
                            <th className="text-left px-4 py-3">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.length === 0 && <tr><td colSpan={5} className="px-4 py-16 text-center text-slate-500">No sessions on record.</td></tr>}
                        {rows.map((s) => (
                            <tr key={s.id} className={`border-b border-slate-200 ${s.revoked_at ? "bg-slate-50 text-slate-400" : ""}`} data-testid={`admin-session-row-${s.id}`}>
                                <td className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                        <Laptop size={14} className="text-slate-500" />
                                        <div>
                                            <div className="text-slate-900 font-medium">{s.device_name || "Unknown device"}</div>
                                            <div className="text-xs text-slate-500 mono truncate max-w-[360px]" title={s.user_agent}>{s.user_agent}</div>
                                        </div>
                                    </div>
                                </td>
                                <td className="px-4 py-3 text-slate-700">
                                    <span className="inline-flex items-center gap-1"><MapPin size={12} />{s.location_country || "Unknown"}{s.location_city ? ` · ${s.location_city}` : ""}</span>
                                </td>
                                <td className="px-4 py-3 mono text-slate-700">{redactIp(s.ip_address)}</td>
                                <td className="px-4 py-3 mono tabular text-slate-700">{timeAgo(s.last_active_at)}<div className="text-[11px] text-slate-500">{formatDateTime(s.last_active_at)}</div></td>
                                <td className="px-4 py-3 text-xs">
                                    {s.revoked_at ? (
                                        <span className="inline-flex items-center text-slate-600 bg-slate-100 border border-slate-200 rounded-sm px-1.5 py-0.5">Revoked ({s.revoked_reason})</span>
                                    ) : (
                                        <span className="inline-flex items-center text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-sm px-1.5 py-0.5">Active</span>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </section>
        </div>
    );
}
