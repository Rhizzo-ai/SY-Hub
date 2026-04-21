import React, { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { ArrowLeft, ChevronRight, Loader2, Save, Shield } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

/**
 * Admin-only edit form for an existing user. Scope matches the close-out
 * patch brief: identity (names/email/phone) + active/suspended toggle.
 * Roles continue to be managed on the UserDetail page.
 */
export default function UserEdit() {
    const { id } = useParams();
    const nav = useNavigate();
    const { me, hasPerm } = useAuth();
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState({
        first_name: "",
        last_name: "",
        email: "",
        phone: "",
        status: "Active",
    });

    useEffect(() => {
        (async () => {
            try {
                const r = await api.get(`/users/${id}`);
                setUser(r.data);
                setForm({
                    first_name: r.data.first_name || "",
                    last_name: r.data.last_name || "",
                    email: r.data.email || "",
                    phone: r.data.phone || "",
                    status: r.data.status || "Active",
                });
            } catch (e) {
                toast.error(e.friendlyMessage || "Failed to load user");
            } finally {
                setLoading(false);
            }
        })();
    }, [id]);

    if (!hasPerm("users.admin")) {
        return (
            <div className="max-w-xl space-y-3" data-testid="user-edit-forbidden">
                <h1 className="font-heading text-2xl font-bold text-slate-900">Not permitted</h1>
                <p className="text-sm text-slate-600">You need <code className="mono">users.admin</code> to edit users.</p>
                <Button variant="outline" onClick={() => nav("/users")}>Back to users</Button>
            </div>
        );
    }

    if (loading || !user) {
        return <div className="flex items-center gap-2 text-slate-500"><Loader2 size={14} className="animate-spin" /> Loading…</div>;
    }

    const isSelf = me?.id === user.id;
    const isActive = form.status === "Active";

    // Only send fields that actually changed.
    const diff = () => {
        const d = {};
        if (form.first_name.trim() !== (user.first_name || "")) d.first_name = form.first_name.trim();
        if (form.last_name.trim() !== (user.last_name || "")) d.last_name = form.last_name.trim();
        if (form.email.trim().toLowerCase() !== (user.email || "").toLowerCase()) d.email = form.email.trim().toLowerCase();
        const phoneNow = (form.phone || "").trim() || null;
        const phoneBefore = user.phone || null;
        if (phoneNow !== phoneBefore) d.phone = phoneNow;
        if (form.status !== user.status) d.status = form.status;
        return d;
    };

    const changed = Object.keys(diff());
    const hasChanges = changed.length > 0;

    const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim());
    const firstValid = form.first_name.trim().length > 0;
    const lastValid = form.last_name.trim().length > 0;
    const canSave = hasChanges && emailValid && firstValid && lastValid && !saving;

    const onSubmit = async (e) => {
        e.preventDefault();
        if (!canSave) return;
        setSaving(true);
        try {
            const r = await api.put(`/users/${id}`, diff());
            toast.success("User updated");
            nav(`/users/${r.data.id}`);
        } catch (err) {
            toast.error(err.friendlyMessage || "Failed to update user");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="space-y-6 max-w-3xl" data-testid="user-edit-page">
            <div className="flex items-center gap-2 text-xs text-slate-500">
                <Link to="/users" className="hover:text-slate-900 inline-flex items-center gap-1"><ArrowLeft size={12} /> Users</Link>
                <ChevronRight size={12} />
                <Link to={`/users/${id}`} className="hover:text-slate-900 mono">{user.display_name}</Link>
                <ChevronRight size={12} />
                <span>Edit</span>
            </div>

            <header>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Users · Edit</div>
                <h1 className="font-heading text-3xl font-bold text-slate-900 mt-1">Edit {user.display_name}</h1>
                <p className="text-sm text-slate-600 mt-1">Modify identity and account status. Roles are managed on the detail page.</p>
            </header>

            <form onSubmit={onSubmit} className="bg-white border border-slate-200 rounded-lg shadow-sm" data-testid="user-edit-form">
                <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div>
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">First name *</label>
                        <Input
                            value={form.first_name}
                            onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                            className="bg-white h-9"
                            data-testid="edit-first-name"
                            required
                        />
                        {!firstValid && <p className="text-[11px] text-rose-600 mt-1">Required</p>}
                    </div>
                    <div>
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Last name *</label>
                        <Input
                            value={form.last_name}
                            onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                            className="bg-white h-9"
                            data-testid="edit-last-name"
                            required
                        />
                        {!lastValid && <p className="text-[11px] text-rose-600 mt-1">Required</p>}
                    </div>
                    <div className="md:col-span-2">
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Email *</label>
                        <Input
                            type="email"
                            value={form.email}
                            onChange={(e) => setForm({ ...form, email: e.target.value })}
                            className="bg-white h-9 mono"
                            data-testid="edit-email"
                            required
                        />
                        {!emailValid && form.email.length > 0 && (
                            <p className="text-[11px] text-rose-600 mt-1">Enter a valid email address</p>
                        )}
                        {form.email.trim().toLowerCase() !== (user.email || "").toLowerCase() && (
                            <p className="text-[11px] text-amber-700 mt-1">
                                Changing the email will flag the account unverified; the user must re-verify on next login.
                            </p>
                        )}
                    </div>
                    <div>
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Phone</label>
                        <Input
                            value={form.phone || ""}
                            onChange={(e) => setForm({ ...form, phone: e.target.value })}
                            className="bg-white h-9 mono"
                            data-testid="edit-phone"
                        />
                    </div>
                    <div>
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Account status</label>
                        <div className="flex items-center gap-3 h-9" data-testid="edit-status-toggle">
                            <button
                                type="button"
                                role="switch"
                                aria-checked={isActive}
                                disabled={isSelf}
                                onClick={() => setForm({ ...form, status: isActive ? "Suspended" : "Active" })}
                                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${isActive ? "bg-emerald-500" : "bg-slate-300"} ${isSelf ? "opacity-50 cursor-not-allowed" : ""}`}
                                data-testid="edit-status-switch"
                            >
                                <span className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${isActive ? "translate-x-5" : "translate-x-0.5"}`} />
                            </button>
                            <span className={`text-sm font-medium ${isActive ? "text-emerald-700" : "text-slate-600"}`} data-testid="edit-status-label">
                                {isActive ? "Active" : "Suspended"}
                            </span>
                        </div>
                        {isSelf && (
                            <p className="text-[11px] text-slate-500 mt-1">You cannot deactivate your own account.</p>
                        )}
                        {!isActive && !isSelf && (
                            <p className="text-[11px] text-amber-700 mt-1">Suspended users cannot log in until reactivated.</p>
                        )}
                    </div>
                </div>

                <div className="px-6 py-3 border-t border-slate-200 bg-slate-50/50 flex items-center gap-3">
                    <Link
                        to={`/users/${id}`}
                        className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900"
                        data-testid="edit-manage-roles-link"
                    >
                        <Shield size={12} /> Manage roles on detail page →
                    </Link>
                    <div className="ml-auto flex items-center gap-2">
                        <span className="text-[11px] text-slate-500 mono tabular" data-testid="edit-diff-count">
                            {hasChanges ? `${changed.length} change${changed.length === 1 ? "" : "s"}` : "No changes"}
                        </span>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => nav(`/users/${id}`)}
                            data-testid="edit-cancel"
                        >
                            Cancel
                        </Button>
                        <Button
                            type="submit"
                            disabled={!canSave}
                            className="bg-slate-900 hover:bg-slate-800 text-white"
                            data-testid="edit-save"
                        >
                            {saving && <Loader2 size={14} className="mr-1.5 animate-spin" />}
                            <Save size={14} className="mr-1.5" /> Save changes
                        </Button>
                    </div>
                </div>
            </form>
        </div>
    );
}
