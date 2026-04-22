import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { displayEnum } from "@/lib/format";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

export default function RoleAssignmentModal({ userId, onClose, onSuccess }) {
    const [roles, setRoles] = useState([]);
    const [entities, setEntities] = useState([]);
    const [permissions, setPermissions] = useState([]);
    const [selectedRole, setSelectedRole] = useState("");
    const [entityScope, setEntityScope] = useState("All");
    const [projectScope, setProjectScope] = useState("All");
    const [entityIds, setEntityIds] = useState([]);
    const [overrides, setOverrides] = useState([]);
    const [expiresAt, setExpiresAt] = useState("");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        Promise.all([
            api.get("/roles"),
            api.get("/entities", { params: { page_size: 200 } }),
        ]).then(([r, e]) => { setRoles(r.data); setEntities(e.data.items); });
    }, []);

    useEffect(() => {
        if (!selectedRole) { setPermissions([]); return; }
        api.get(`/roles/${selectedRole}`).then((r) => setPermissions(r.data.permissions));
    }, [selectedRole]);

    const toggleEntity = (id) => setEntityIds(
        entityIds.includes(id) ? entityIds.filter((x) => x !== id) : [...entityIds, id]
    );
    const toggleOverride = (code) => setOverrides(
        overrides.includes(code) ? overrides.filter((x) => x !== code) : [...overrides, code]
    );

    const onSubmit = async (e) => {
        e.preventDefault();
        if (!selectedRole) { toast.error("Select a role"); return; }
        if (entityScope === "Specific" && entityIds.length === 0) {
            toast.error("Select at least one entity or switch to 'All'"); return;
        }
        setBusy(true);
        try {
            await api.post(`/users/${userId}/roles`, {
                role_id: selectedRole,
                entity_scope: entityScope,
                project_scope: projectScope,
                entity_ids: entityIds,
                project_ids: [],
                view_overrides: overrides,
                expires_at: expiresAt || null,
            });
            toast.success("Role assigned");
            onSuccess();
        } catch (err) {
            toast.error(err.friendlyMessage || "Failed to assign role");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-slate-900/60 z-50 flex items-center justify-center p-4" data-testid="role-assignment-modal">
            <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
                <header className="px-6 py-4 border-b border-slate-200 sticky top-0 bg-white z-10">
                    <h2 className="font-heading text-lg font-semibold">Assign Role</h2>
                </header>
                <form onSubmit={onSubmit} className="p-6 space-y-6">
                    <div>
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Role</label>
                        <select value={selectedRole} onChange={(e) => setSelectedRole(e.target.value)} className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" data-testid="assign-role-select">
                            <option value="">Select role…</option>
                            {roles.map((r) => <option key={r.id} value={r.id}>{r.name} · {r.code}</option>)}
                        </select>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Entity scope</label>
                            <select value={entityScope} onChange={(e) => setEntityScope(e.target.value)} className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" data-testid="assign-entity-scope">
                                <option value="All">All entities</option>
                                <option value="Specific">Specific entities</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Project scope</label>
                            <select value={projectScope} onChange={(e) => setProjectScope(e.target.value)} className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm" data-testid="assign-project-scope">
                                <option value="All">All projects</option>
                                <option value="None">None</option>
                                <option value="Specific" disabled>Specific (enabled in Prompt 1.5)</option>
                            </select>
                        </div>
                    </div>

                    {entityScope === "Specific" && (
                        <div data-testid="entity-picker">
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Entities</label>
                            <div className="border border-slate-200 rounded-md max-h-40 overflow-y-auto divide-y divide-slate-100">
                                {entities.map((e) => (
                                    <label key={e.id} className="flex items-center gap-2 px-3 py-2 hover:bg-slate-50 cursor-pointer">
                                        <input type="checkbox" checked={entityIds.includes(e.id)} onChange={() => toggleEntity(e.id)} data-testid={`entity-toggle-${e.id}`} />
                                        <span className="text-sm">{e.name} · <span className="text-slate-500 mono">{displayEnum(e.entity_type)}</span></span>
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}

                    <div>
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Expires (optional)</label>
                        <Input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} className="bg-white mono" data-testid="assign-expires" />
                    </div>

                    {permissions.length > 0 && (
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">
                                Remove permissions for this assignment (optional)
                            </label>
                            <div className="border border-slate-200 rounded-md max-h-40 overflow-y-auto divide-y divide-slate-100">
                                {permissions.map((p) => (
                                    <label key={p.id} className="flex items-center gap-2 px-3 py-2 hover:bg-slate-50 cursor-pointer text-sm">
                                        <input type="checkbox" checked={overrides.includes(p.code)} onChange={() => toggleOverride(p.code)} data-testid={`override-toggle-${p.code}`} />
                                        <span className="mono text-slate-700">{p.code}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="flex justify-end gap-2 pt-4 border-t border-slate-200">
                        <Button type="button" variant="outline" onClick={onClose} data-testid="assign-cancel">Cancel</Button>
                        <Button type="submit" disabled={busy} className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="assign-submit">
                            {busy && <Loader2 size={14} className="mr-1.5 animate-spin" />} Assign Role
                        </Button>
                    </div>
                </form>
            </div>
        </div>
    );
}
