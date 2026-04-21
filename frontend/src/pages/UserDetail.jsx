import React, { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { ArrowLeft, ChevronRight, Loader2, Plus, Shield, Trash2, Unlock, UserX, Pencil } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { displayEnum, formatDateTime, formatDate } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import RoleAssignmentModal from "@/components/user/RoleAssignmentModal";
import { toast } from "sonner";

function Section({ title, children, testid }) {
    return (
        <section className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden" data-testid={testid}>
            <header className="px-6 py-3.5 border-b border-slate-200 bg-slate-50/50">
                <h2 className="font-heading text-sm font-semibold text-slate-900 uppercase tracking-widest">{title}</h2>
            </header>
            <div className="p-6">{children}</div>
        </section>
    );
}

function Field({ label, children, mono = false, testid }) {
    return (
        <div data-testid={testid}>
            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">{label}</div>
            <div className={`mt-1 text-sm text-slate-900 ${mono ? "mono tabular" : ""}`}>{children ?? "—"}</div>
        </div>
    );
}

export default function UserDetail() {
    const { id } = useParams();
    const nav = useNavigate();
    const { hasPerm, me } = useAuth();
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [showAssign, setShowAssign] = useState(false);

    const load = async () => {
        setLoading(true);
        try { setUser((await api.get(`/users/${id}`)).data); } finally { setLoading(false); }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { load(); }, [id]);

    const onUnlock = async () => {
        try { await api.post(`/users/${id}/unlock`); toast.success("Account unlocked"); load(); }
        catch (e) { toast.error(e.friendlyMessage); }
    };

    const onRevokeRole = async (urId) => {
        try { await api.delete(`/users/${id}/roles/${urId}`); toast.success("Role revoked"); load(); }
        catch (e) { toast.error(e.friendlyMessage); }
    };

    const onScrubPii = async () => {
        if (!confirm("Scrub PII for this user? This is irreversible.")) return;
        try { await api.post(`/users/${id}/scrub_pii`); toast.success("PII scrubbed"); nav("/users"); }
        catch (e) { toast.error(e.friendlyMessage); }
    };

    if (loading || !user) {
        return <div className="flex items-center gap-2 text-slate-500"><Loader2 size={14} className="animate-spin" /> Loading…</div>;
    }

    const locked = user.locked_until && new Date(user.locked_until) > new Date();

    return (
        <div className="space-y-6" data-testid="user-detail-page">
            <div className="flex items-center gap-2 text-xs text-slate-500">
                <Link to="/users" className="hover:text-slate-900 inline-flex items-center gap-1"><ArrowLeft size={12} /> Users</Link>
                <ChevronRight size={12} /><span className="mono text-slate-700">{user.display_name}</span>
            </div>

            <header className="flex items-start justify-between">
                <div>
                    <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900" data-testid="user-detail-name">
                        {user.display_name}
                    </h1>
                    <div className="mt-1 text-sm text-slate-600 mono">{user.email}</div>
                    <div className="mt-3 text-xs text-slate-500">
                        Created <span className="mono tabular">{formatDateTime(user.created_at)}</span>
                        {user.last_login_at && <> · Last login <span className="mono tabular">{formatDateTime(user.last_login_at)}</span></>}
                    </div>
                </div>
                <div className="flex gap-2">
                    {hasPerm("users.admin") && (
                        <Button
                            variant="outline"
                            onClick={() => nav(`/users/${id}/edit`)}
                            data-testid="edit-user-button"
                        >
                            <Pencil size={14} className="mr-1.5" /> Edit
                        </Button>
                    )}
                    {locked && hasPerm("users.admin") && (
                        <Button variant="outline" onClick={onUnlock} data-testid="unlock-button">
                            <Unlock size={14} className="mr-1.5" /> Unlock
                        </Button>
                    )}
                    {hasPerm("users.admin") && user.id !== me?.id && (
                        <Button variant="outline" onClick={onScrubPii} className="text-rose-700 border-rose-200 hover:bg-rose-50" data-testid="scrub-pii-button">
                            <UserX size={14} className="mr-1.5" /> Scrub PII
                        </Button>
                    )}
                </div>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Section title="Identity" testid="section-identity">
                    <div className="grid grid-cols-2 gap-6">
                        <Field label="First name" testid="field-first">{user.first_name}</Field>
                        <Field label="Last name" testid="field-last">{user.last_name}</Field>
                        <Field label="Email" mono testid="field-email">{user.email}</Field>
                        <Field label="Phone" mono testid="field-phone">{user.phone}</Field>
                        <Field label="Job title" testid="field-job">{user.job_title}</Field>
                        <Field label="Timezone" mono testid="field-tz">{user.timezone}</Field>
                    </div>
                </Section>
                <Section title="Access" testid="section-access">
                    <div className="grid grid-cols-2 gap-6">
                        <Field label="Type" testid="field-type">{displayEnum(user.user_type)}</Field>
                        <Field label="Status" testid="field-status">{displayEnum(user.status)}</Field>
                        <Field label="MFA" testid="field-mfa">{user.mfa_enabled ? `${displayEnum(user.mfa_method)} enrolled` : "Not enrolled"}</Field>
                        <Field label="Locale" mono testid="field-locale">{user.locale}</Field>
                    </div>
                </Section>
                <Section title="Security" testid="section-security">
                    <div className="grid grid-cols-2 gap-6">
                        <Field label="Failed attempts" mono testid="field-failed">{user.failed_login_attempts}</Field>
                        <Field label="Locked until" mono testid="field-locked">{user.locked_until ? formatDateTime(user.locked_until) : "—"}</Field>
                        <Field label="Email verified" testid="field-verified">{user.email_verified ? "Yes" : "No"}</Field>
                        <Field label="Last login IP" mono testid="field-lastip">{user.last_login_ip || "—"}</Field>
                    </div>
                </Section>
                <Section title="Admin" testid="section-admin">
                    <div className="space-y-4">
                        <Field label="Invited by" mono testid="field-invited-by">{user.invited_by_user_id || "—"}</Field>
                        <Field label="Invitation sent" mono testid="field-invite-sent">{user.invitation_sent_at ? formatDateTime(user.invitation_sent_at) : "—"}</Field>
                        <Field label="Admin notes" testid="field-admin-notes">
                            <pre className="whitespace-pre-wrap font-sans text-sm">{user.admin_notes || "—"}</pre>
                        </Field>
                    </div>
                </Section>
            </div>

            <section className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden" data-testid="section-roles">
                <header className="px-6 py-3.5 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
                    <h2 className="font-heading text-sm font-semibold text-slate-900 uppercase tracking-widest">Role Assignments</h2>
                    {hasPerm("users.edit") && (
                        <Button onClick={() => setShowAssign(true)} size="sm" className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="add-role-button">
                            <Plus size={14} className="mr-1" /> Add Role
                        </Button>
                    )}
                </header>
                <table className="w-full text-sm">
                    <thead>
                        <tr className="bg-slate-50 border-b border-slate-200 text-[11px] uppercase tracking-widest text-slate-500">
                            <th className="text-left px-4 py-3">Role</th>
                            <th className="text-left px-4 py-3">Entity scope</th>
                            <th className="text-left px-4 py-3">Project scope</th>
                            <th className="text-left px-4 py-3">Expires</th>
                            <th className="text-left px-4 py-3">Status</th>
                            <th className="text-right px-4 py-3">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {user.roles.length === 0 && (
                            <tr><td colSpan={6} className="px-4 py-12 text-center text-slate-500">No role assignments.</td></tr>
                        )}
                        {user.roles.map((r) => (
                            <tr key={r.id} className="border-b border-slate-200" data-testid={`role-assignment-${r.id}`}>
                                <td className="px-4 py-3">
                                    <div className="font-medium text-slate-900 inline-flex items-center gap-1"><Shield size={12} /> {r.role_name}</div>
                                    <div className="text-xs text-slate-500 mono">{r.role_code}</div>
                                </td>
                                <td className="px-4 py-3 text-slate-700 mono tabular">{r.entity_scope === "All" ? "All" : `${r.entity_ids.length} entity(ies)`}</td>
                                <td className="px-4 py-3 text-slate-700 mono tabular">{r.project_scope === "All" ? "All" : r.project_scope === "None" ? "None" : `${r.project_ids.length} project(s)`}</td>
                                <td className="px-4 py-3 mono tabular text-slate-700">{r.expires_at ? formatDate(r.expires_at) : "—"}</td>
                                <td className="px-4 py-3 text-slate-700 text-xs uppercase tracking-wider">{r.status}</td>
                                <td className="px-4 py-3 text-right">
                                    {r.status === "Active" && hasPerm("users.edit") && (
                                        <button onClick={() => onRevokeRole(r.id)} className="text-rose-600 hover:text-rose-800 text-xs inline-flex items-center gap-1" data-testid={`revoke-role-${r.id}`}>
                                            <Trash2 size={12} /> Revoke
                                        </button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </section>

            {showAssign && (
                <RoleAssignmentModal userId={id} onClose={() => setShowAssign(false)} onSuccess={() => { setShowAssign(false); load(); }} />
            )}
        </div>
    );
}
