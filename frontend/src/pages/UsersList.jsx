import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, Search, Loader2, ShieldCheck, ShieldAlert, Lock, Unlock, Pencil } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { formatDateTime, displayEnum } from "@/lib/format";
import { toast } from "sonner";

const USER_TYPES = [
    "Internal", "External_Subcontractor", "External_Consultant",
    "External_Funder", "Service_Account",
];
const STATUSES = ["Pending_Invitation", "Active", "Suspended", "Archived"];

function StatusBadge({ status }) {
    const styles = {
        Active: "bg-emerald-100 text-emerald-800 border-emerald-200",
        Pending_Invitation: "bg-sky-100 text-sky-800 border-sky-200",
        Suspended: "bg-amber-100 text-amber-800 border-amber-200",
        Archived: "bg-slate-100 text-slate-600 border-slate-200",
    };
    return (
        <span
            className={`inline-flex items-center rounded-sm border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider ${styles[status] || ""}`}
            data-testid={`user-status-${status}`}
        >
            {displayEnum(status)}
        </span>
    );
}

function isLocked(u) {
    return u.locked_until && new Date(u.locked_until) > new Date();
}

export default function UsersList() {
    const nav = useNavigate();
    const { hasPerm } = useAuth();
    const [data, setData] = useState({ items: [], total: 0 });
    const [loading, setLoading] = useState(true);
    const [unlockingId, setUnlockingId] = useState(null);
    const [q, setQ] = useState("");
    const [type, setType] = useState("");
    const [status, setStatus] = useState("");

    const load = async () => {
        setLoading(true);
        const params = { q: q || undefined, user_type: type || undefined, status: status || undefined };
        try {
            const r = await api.get("/users", { params });
            setData(r.data);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [type, status]);
    const onSearch = (e) => { e.preventDefault(); load(); };

    const onUnlock = async (e, u) => {
        e.stopPropagation();
        setUnlockingId(u.id);
        try {
            await api.post(`/users/${u.id}/unlock`);
            toast.success(`Unlocked ${u.display_name || u.email}`);
            await load();
        } catch (err) {
            toast.error(err.friendlyMessage || "Unlock failed");
        } finally {
            setUnlockingId(null);
        }
    };

    const canUnlock = hasPerm("users.admin");

    return (
        <div className="space-y-6" data-testid="users-list-page">
            <header className="flex items-start justify-between">
                <div>
                    <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Module 02</div>
                    <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-1">Users</h1>
                    <p className="text-sm text-slate-600 mt-1">People and service accounts with access to SY Homes operations.</p>
                </div>
                {hasPerm("users.create") && (
                    <Button
                        onClick={() => nav("/users/new")}
                        className="bg-slate-900 hover:bg-slate-800 text-white"
                        data-testid="invite-user-button"
                    >
                        <Plus size={16} className="mr-1.5" /> Invite User
                    </Button>
                )}
            </header>

            <section className="bg-white border border-slate-200 rounded-lg shadow-sm">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/60 flex flex-wrap items-center gap-3">
                    <form onSubmit={onSearch} className="relative flex-1 min-w-[240px] max-w-md" data-testid="users-search-form">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or email…" className="pl-9 h-9 bg-white" data-testid="users-search-input" />
                    </form>
                    <select value={type} onChange={(e) => setType(e.target.value)} className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm" data-testid="filter-user-type">
                        <option value="">All types</option>
                        {USER_TYPES.map((t) => <option key={t} value={t}>{displayEnum(t)}</option>)}
                    </select>
                    <select value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm" data-testid="filter-user-status">
                        <option value="">Active + Pending + Suspended</option>
                        {STATUSES.map((s) => <option key={s} value={s}>{displayEnum(s)}</option>)}
                    </select>
                    <div className="ml-auto text-xs text-slate-500 mono tabular">
                        {loading ? <Loader2 size={12} className="animate-spin inline mr-1" /> : `${data.total} ${data.total === 1 ? "user" : "users"}`}
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="users-table">
                        <thead>
                            <tr className="bg-slate-50 border-y border-slate-200 text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                                <th className="text-left px-4 py-3">Name</th>
                                <th className="text-left px-4 py-3">Email</th>
                                <th className="text-left px-4 py-3">Type</th>
                                <th className="text-left px-4 py-3">Status</th>
                                <th className="text-left px-4 py-3">MFA</th>
                                <th className="text-left px-4 py-3">Last Login</th>
                                <th className="text-left px-4 py-3">Roles</th>
                                {canUnlock && <th className="text-right px-4 py-3">Actions</th>}
                            </tr>
                        </thead>
                        <tbody>
                            {!loading && data.items.length === 0 && (
                                <tr><td colSpan={canUnlock ? 8 : 7} className="px-4 py-16 text-center text-slate-500">No users found.</td></tr>
                            )}
                            {data.items.map((u) => {
                                const locked = isLocked(u);
                                return (
                                    <tr key={u.id} onClick={() => nav(`/users/${u.id}`)} className="border-b border-slate-200 hover:bg-slate-50/80 cursor-pointer" data-testid={`user-row-${u.id}`}>
                                        <td className="px-4 py-3 font-medium text-slate-900">
                                            <div className="inline-flex items-center gap-2">
                                                {locked && (
                                                    <span
                                                        className="inline-flex items-center gap-1 text-[10px] uppercase tracking-widest font-semibold text-rose-700 bg-rose-50 border border-rose-200 rounded-sm px-1.5 py-0.5"
                                                        title={`Locked until ${formatDateTime(u.locked_until)}`}
                                                        data-testid={`user-lock-badge-${u.id}`}
                                                    >
                                                        <Lock size={10} /> Locked
                                                    </span>
                                                )}
                                                {u.display_name || `${u.first_name} ${u.last_name}`}
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 mono text-slate-700">{u.email}</td>
                                        <td className="px-4 py-3 text-slate-700">{displayEnum(u.user_type)}</td>
                                        <td className="px-4 py-3"><StatusBadge status={u.status} /></td>
                                        <td className="px-4 py-3">
                                            {u.mfa_enabled
                                                ? <span className="inline-flex items-center gap-1 text-emerald-700 text-xs"><ShieldCheck size={12} /> TOTP</span>
                                                : <span className="inline-flex items-center gap-1 text-slate-500 text-xs"><ShieldAlert size={12} /> Off</span>}
                                        </td>
                                        <td className="px-4 py-3 mono tabular text-slate-700">{u.last_login_at ? formatDateTime(u.last_login_at) : "—"}</td>
                                        <td className="px-4 py-3 mono tabular text-slate-700">{u.role_count}</td>
                                        {canUnlock && (
                                            <td className="px-4 py-3 text-right">
                                                <div className="inline-flex items-center gap-1 justify-end">
                                                    {locked ? (
                                                        <Button
                                                            variant="outline"
                                                            size="sm"
                                                            className="h-7 text-xs"
                                                            disabled={unlockingId === u.id}
                                                            onClick={(e) => onUnlock(e, u)}
                                                            data-testid={`unlock-user-${u.id}`}
                                                        >
                                                            {unlockingId === u.id
                                                                ? <Loader2 size={12} className="animate-spin" />
                                                                : <><Unlock size={12} className="mr-1" /> Unlock</>}
                                                        </Button>
                                                    ) : null}
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        className="h-7 text-xs"
                                                        onClick={(e) => { e.stopPropagation(); nav(`/users/${u.id}/edit`); }}
                                                        data-testid={`edit-user-${u.id}`}
                                                    >
                                                        <Pencil size={12} className="mr-1" /> Edit
                                                    </Button>
                                                </div>
                                            </td>
                                        )}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </section>
        </div>
    );
}
