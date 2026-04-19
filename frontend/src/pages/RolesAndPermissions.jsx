import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Shield, ShieldCheck, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { displayEnum } from "@/lib/format";

export function RolesList() {
    const [roles, setRoles] = useState(null);
    useEffect(() => { api.get("/roles").then((r) => setRoles(r.data)); }, []);
    if (!roles) return <div className="text-slate-500"><Loader2 size={14} className="animate-spin inline" /> Loading…</div>;
    return (
        <div className="space-y-6" data-testid="roles-list-page">
            <header>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Module 02 · Roles</div>
                <h1 className="font-heading text-3xl font-bold text-slate-900 mt-1">Roles</h1>
                <p className="text-sm text-slate-600 mt-1">10 system roles seeded. Permissions cannot be edited on system roles.</p>
            </header>
            <section className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-[11px] uppercase tracking-widest text-slate-500">
                            <th className="text-left px-4 py-3">Name</th>
                            <th className="text-left px-4 py-3">Code</th>
                            <th className="text-left px-4 py-3">Description</th>
                            <th className="text-left px-4 py-3">Permissions</th>
                            <th className="text-left px-4 py-3">Users</th>
                            <th className="text-left px-4 py-3">System</th>
                        </tr>
                    </thead>
                    <tbody>
                        {roles.map((r) => (
                            <tr key={r.id} className="border-b border-slate-200 hover:bg-slate-50/80" data-testid={`role-row-${r.code}`}>
                                <td className="px-4 py-3">
                                    <Link to={`/roles/${r.id}`} className="font-medium text-slate-900 inline-flex items-center gap-1.5 hover:underline">
                                        <Shield size={14} /> {r.name}
                                    </Link>
                                </td>
                                <td className="px-4 py-3 mono text-slate-700">{r.code}</td>
                                <td className="px-4 py-3 text-slate-600 max-w-md">{r.description}</td>
                                <td className="px-4 py-3 mono tabular text-slate-700">{r.permission_count}</td>
                                <td className="px-4 py-3 mono tabular text-slate-700">{r.user_count}</td>
                                <td className="px-4 py-3">{r.is_system_role && <ShieldCheck size={14} className="text-slate-600" />}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </section>
        </div>
    );
}

export function RoleDetail() {
    const { id } = useParams();
    const [role, setRole] = useState(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { api.get(`/roles/${id}`).then((r) => setRole(r.data)); }, [id]);
    if (!role) return <div className="text-slate-500"><Loader2 size={14} className="animate-spin inline" /> Loading…</div>;

    const grouped = role.permissions.reduce((acc, p) => {
        (acc[p.resource] ||= []).push(p);
        return acc;
    }, {});

    return (
        <div className="space-y-6" data-testid="role-detail-page">
            <Link to="/roles" className="text-xs text-slate-500 hover:text-slate-900">← Roles</Link>
            <header>
                <h1 className="font-heading text-3xl font-bold text-slate-900">{role.name}</h1>
                <div className="mt-1 text-sm text-slate-600 mono">{role.code}</div>
                <p className="text-sm text-slate-600 mt-2 max-w-2xl">{role.description}</p>
                {role.is_system_role && (
                    <div className="mt-3 text-xs text-amber-700 inline-flex items-center gap-1 bg-amber-50 border border-amber-200 rounded-sm px-2 py-0.5">
                        <ShieldCheck size={12} /> System role — permissions are read-only
                    </div>
                )}
            </header>
            <section className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden" data-testid="role-permissions">
                <header className="px-6 py-3.5 border-b border-slate-200 bg-slate-50/50">
                    <h2 className="font-heading text-sm font-semibold uppercase tracking-widest text-slate-900">
                        Permissions ({role.permissions.length})
                    </h2>
                </header>
                <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
                    {Object.entries(grouped).sort().map(([resource, perms]) => (
                        <div key={resource} className="border border-slate-200 rounded-md p-3" data-testid={`perms-resource-${resource}`}>
                            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold mb-2">{displayEnum(resource)}</div>
                            <ul className="space-y-1">
                                {perms.map((p) => (
                                    <li key={p.code} className="text-xs mono text-slate-700 flex items-center justify-between">
                                        <span>{p.action}</span>
                                        {p.is_sensitive && <span className="text-rose-600 text-[10px] uppercase">sensitive</span>}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>
            </section>
        </div>
    );
}

export function PermissionsList() {
    const [perms, setPerms] = useState(null);
    useEffect(() => { api.get("/permissions").then((r) => setPerms(r.data)); }, []);
    if (!perms) return <div className="text-slate-500"><Loader2 size={14} className="animate-spin inline" /> Loading…</div>;

    const grouped = perms.reduce((acc, p) => { (acc[p.resource] ||= []).push(p); return acc; }, {});

    return (
        <div className="space-y-6" data-testid="permissions-list-page">
            <header>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Module 02 · Permissions</div>
                <h1 className="font-heading text-3xl font-bold text-slate-900 mt-1">Permissions</h1>
                <p className="text-sm text-slate-600 mt-1">{perms.length} atomic permissions registered across {Object.keys(grouped).length} resources.</p>
            </header>
            <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {Object.entries(grouped).sort().map(([resource, rows]) => (
                    <div key={resource} className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                        <header className="px-4 py-2 bg-slate-50 border-b border-slate-200 text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                            {displayEnum(resource)}
                        </header>
                        <ul className="divide-y divide-slate-100">
                            {rows.map((p) => (
                                <li key={p.id} className="px-4 py-2 text-sm flex items-center justify-between" data-testid={`perm-${p.code}`}>
                                    <div>
                                        <div className="mono text-slate-900">{p.code}</div>
                                        <div className="text-xs text-slate-500">{p.description}</div>
                                    </div>
                                    {p.is_sensitive && <span className="text-rose-600 text-[10px] uppercase tracking-widest">sensitive</span>}
                                </li>
                            ))}
                        </ul>
                    </div>
                ))}
            </section>
        </div>
    );
}
