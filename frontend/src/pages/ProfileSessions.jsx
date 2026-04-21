import React, { useEffect, useState } from "react";
import { Laptop, Loader2, MapPin, ShieldAlert, X } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

function timeAgo(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    const diff = Math.round((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
    return `${Math.round(diff / 86400)} d ago`;
}

function redactIp(ip) {
    if (!ip) return "—";
    // IPv4 — keep first three octets; IPv6 — keep first three groups.
    if (ip.includes(":")) return ip.split(":").slice(0, 3).join(":") + "::*";
    const parts = ip.split(".");
    if (parts.length === 4) return `${parts[0]}.${parts[1]}.${parts[2]}.*`;
    return ip;
}

export default function ProfileSessions() {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(null); // session id currently being revoked
    const { logout } = useAuth();
    const nav = useNavigate();

    const load = async () => {
        setLoading(true);
        try {
            const r = await api.get("/users/me/sessions");
            setRows(r.data);
        } finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    const onRevoke = async (s) => {
        if (s.is_current) {
            await logout();
            nav("/login");
            return;
        }
        setBusy(s.id);
        try {
            await api.post(`/users/me/sessions/${s.id}/revoke`);
            toast.success("Session revoked");
            await load();
        } catch (e) {
            toast.error(e.friendlyMessage || "Failed to revoke");
        } finally { setBusy(null); }
    };

    const onRevokeOthers = async () => {
        setBusy("others");
        try {
            await api.post(`/users/me/sessions/revoke-others`);
            toast.success("Other sessions revoked");
            await load();
        } catch (e) {
            toast.error(e.friendlyMessage || "Failed");
        } finally { setBusy(null); }
    };

    const active = rows.filter((r) => !r.revoked_at);

    return (
        <div className="space-y-6 max-w-4xl" data-testid="profile-sessions-page">
            <header>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Profile · Sessions</div>
                <h1 className="font-heading text-3xl font-bold text-slate-900 mt-1">Active sessions</h1>
                <p className="text-sm text-slate-600 mt-1">Every browser or device where your SY Homes account is signed in.</p>
            </header>

            <section className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/60 flex items-center gap-3">
                    <h2 className="font-heading text-sm font-semibold uppercase tracking-widest text-slate-900">Sessions</h2>
                    <div className="ml-auto text-xs text-slate-500 mono tabular">
                        {loading ? <Loader2 size={12} className="inline animate-spin" /> : `${active.length} active · ${rows.length} total`}
                    </div>
                    {active.length > 1 && (
                        <Button
                            variant="outline" size="sm"
                            onClick={onRevokeOthers} disabled={busy === "others"}
                            data-testid="revoke-others-button"
                        >
                            {busy === "others" ? <Loader2 size={12} className="animate-spin mr-1" /> : <X size={12} className="mr-1" />}
                            Revoke all other sessions
                        </Button>
                    )}
                </div>
                <table className="w-full text-sm" data-testid="sessions-table">
                    <thead className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                        <tr className="bg-slate-50 border-b border-slate-200">
                            <th className="text-left px-4 py-3">Device</th>
                            <th className="text-left px-4 py-3">Location</th>
                            <th className="text-left px-4 py-3">IP</th>
                            <th className="text-left px-4 py-3">Last active</th>
                            <th className="text-left px-4 py-3">Started</th>
                            <th className="text-right px-4 py-3">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {!loading && rows.length === 0 && (
                            <tr><td colSpan={6} className="px-4 py-16 text-center text-slate-500">No sessions found.</td></tr>
                        )}
                        {rows.map((s) => (
                            <tr key={s.id} className={`border-b border-slate-200 ${s.revoked_at ? "bg-slate-50 text-slate-400" : ""}`} data-testid={`session-row-${s.id}`}>
                                <td className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                        <Laptop size={14} className="text-slate-500" />
                                        <div>
                                            <div className="text-slate-900 font-medium">
                                                {s.device_name || "Unknown device"}
                                                {s.is_current && (
                                                    <span className="ml-2 inline-flex items-center text-[10px] uppercase tracking-widest font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-sm px-1.5 py-0.5" data-testid={`session-current-${s.id}`}>
                                                        Current
                                                    </span>
                                                )}
                                                {s.revoked_at && (
                                                    <span className="ml-2 inline-flex items-center text-[10px] uppercase tracking-widest font-semibold text-slate-500 bg-slate-100 border border-slate-200 rounded-sm px-1.5 py-0.5">
                                                        Revoked ({s.revoked_reason})
                                                    </span>
                                                )}
                                                {s.remember_me && !s.revoked_at && (
                                                    <span className="ml-2 inline-flex items-center text-[10px] uppercase tracking-widest font-semibold text-amber-800 bg-amber-50 border border-amber-200 rounded-sm px-1.5 py-0.5">
                                                        Remember
                                                    </span>
                                                )}
                                            </div>
                                            <div className="text-xs text-slate-500 mono truncate max-w-[340px]" title={s.user_agent}>
                                                {s.user_agent}
                                            </div>
                                        </div>
                                    </div>
                                </td>
                                <td className="px-4 py-3 text-slate-700">
                                    <span className="inline-flex items-center gap-1">
                                        <MapPin size={12} className="text-slate-400" />
                                        {s.location_country || "Unknown"}{s.location_city ? ` · ${s.location_city}` : ""}
                                    </span>
                                </td>
                                <td className="px-4 py-3 mono text-slate-700">{redactIp(s.ip_address)}</td>
                                <td className="px-4 py-3 mono tabular text-slate-700">{timeAgo(s.last_active_at)}</td>
                                <td className="px-4 py-3 mono tabular text-slate-500 text-xs">{formatDateTime(s.created_at)}</td>
                                <td className="px-4 py-3 text-right">
                                    {!s.revoked_at ? (
                                        <Button
                                            variant="outline" size="sm"
                                            onClick={() => onRevoke(s)}
                                            disabled={busy === s.id}
                                            data-testid={`revoke-session-${s.id}`}
                                            className={`h-7 text-xs ${s.is_current ? "" : "text-rose-700 border-rose-200 hover:bg-rose-50"}`}
                                        >
                                            {busy === s.id ? <Loader2 size={12} className="animate-spin" /> : (s.is_current ? "Sign out" : "Revoke")}
                                        </Button>
                                    ) : <span className="text-slate-300 text-xs">—</span>}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </section>

            <p className="text-xs text-slate-500 flex items-center gap-1.5">
                <ShieldAlert size={12} /> Sessions auto-expire after 60 minutes of inactivity.
            </p>
        </div>
    );
}
