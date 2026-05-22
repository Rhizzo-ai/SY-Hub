import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Loader2, RefreshCw, AlertTriangle, ChevronDown, ChevronRight, X } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { displayEnum, formatDate, formatDateTime, formatMoney, formatPercent } from "@/lib/format";
import { toast } from "sonner";
import NudgeBanner from "@/components/appraisal/NudgeBanner";

const STAGES = [
    "Lead", "Appraisal", "Deal_Pipeline", "Planning", "Pre_Con",
    "Construction", "Sales", "Post_Completion", "Closed", "Dead",
];

// Must mirror backend FORWARD_TRANSITIONS (app/services/project_stage.py).
const FORWARD = {
    Lead: ["Appraisal", "Dead"],
    Appraisal: ["Deal_Pipeline", "Dead"],
    Deal_Pipeline: ["Planning", "Dead"],
    Planning: ["Pre_Con", "Dead"],
    Pre_Con: ["Construction", "Dead"],
    Construction: ["Sales", "Post_Completion", "Dead"],
    Sales: ["Post_Completion", "Dead"],
    Post_Completion: ["Closed", "Dead"],
    Closed: [],
    Dead: [],
};

const TEAM_ROLES = [
    "Project_Lead", "Contracts_Manager", "Site_Manager", "Quantity_Surveyor",
    "Designer", "Consultant", "Finance", "Sales", "Support",
];

function stageBadge(stage) {
    if (stage === "Dead") return "bg-rose-50 text-rose-800 border-rose-200";
    if (stage === "Closed") return "bg-slate-100 text-slate-700 border-slate-300";
    if (stage === "Construction" || stage === "Sales") {
        return "bg-emerald-50 text-emerald-800 border-emerald-200";
    }
    return "bg-blue-50 text-blue-800 border-blue-200";
}

export default function ProjectDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { me } = useAuth();
    const perms = me?.permissions || [];
    const isSuper = me?.is_super_admin;
    const canEdit = perms.includes("projects.edit") || isSuper;
    const canViewSensitive = perms.includes("projects.view_sensitive") || isSuper;
    const canDelete = perms.includes("projects.delete") || isSuper;

    const [project, setProject] = useState(null);
    const [loading, setLoading] = useState(true);
    const [tab, setTab] = useState("overview");

    const [advanceOpen, setAdvanceOpen] = useState(null);    // target stage
    const [overrideOpen, setOverrideOpen] = useState(false);
    const [refreshingFin, setRefreshingFin] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const r = await api.get(`/projects/${id}`);
            setProject(r.data);
        } catch (err) {
            if (err?.response?.status === 404) {
                toast.error("Project not found");
                navigate("/projects");
                return;
            }
            toast.error(err.friendlyMessage || "Failed to load project");
        } finally {
            setLoading(false);
        }
    }, [id, navigate]);

    useEffect(() => { load(); }, [load]);

    const refreshFinancials = async () => {
        setRefreshingFin(true);
        try {
            await api.post(`/projects/${id}/financials/refresh`);
            toast.success("Financials refreshed");
            load();
        } catch (err) {
            toast.error(err.friendlyMessage || "Refresh failed");
        } finally {
            setRefreshingFin(false);
        }
    };

    const onDelete = async () => {
        if (!window.confirm(`Delete ${project.project_code}? This cannot be undone.`)) return;
        try {
            await api.delete(`/projects/${id}`);
            toast.success("Project deleted");
            navigate("/projects");
        } catch (err) {
            toast.error(err.friendlyMessage || "Delete failed");
        }
    };

    if (loading || !project) {
        return (
            <div className="flex items-center justify-center py-16" data-testid="project-loading">
                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            </div>
        );
    }

    const allowedNext = FORWARD[project.current_stage] || [];

    return (
        <div className="space-y-6" data-testid="project-detail-page">
            <button onClick={() => navigate("/projects")}
                    className="text-sm text-slate-600 hover:text-slate-900 inline-flex items-center gap-1"
                    data-testid="back-to-projects">
                <ArrowLeft size={14} /> Back to projects
            </button>

            <NudgeBanner projectId={id} />

            {/* Header */}
            <header className="flex items-start justify-between gap-6">
                <div>
                    <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mono">
                        {project.project_code}
                    </div>
                    <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-1"
                        data-testid="project-name">
                        {project.name}
                    </h1>
                    <div className="mt-2 flex items-center gap-2">
                        <span className={`text-xs px-2 py-0.5 rounded-full border ${stageBadge(project.current_stage)}`}
                              data-testid="current-stage-badge">
                            {displayEnum(project.current_stage)}
                        </span>
                        <span className="text-xs text-slate-500">
                            entered {formatDate(project.stage_entered_at)}
                        </span>
                        <span className="text-xs text-slate-400">·</span>
                        <span className="text-xs text-slate-600">Status: {displayEnum(project.status)}</span>
                    </div>
                    {project.status === "Dead" && project.dead_reason && (
                        <div className="mt-3 p-3 rounded-md bg-rose-50 border border-rose-200 text-rose-900 text-sm flex gap-2 max-w-xl"
                             data-testid="dead-banner">
                            <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
                            <div><b>Project marked Dead.</b> {project.dead_reason}</div>
                        </div>
                    )}
                </div>

                {canEdit && (
                    <div className="flex items-center gap-2">
                        {allowedNext.map((s) => (
                            <Button key={s}
                                    size="sm"
                                    variant={s === "Dead" ? "outline" : "default"}
                                    className={s === "Dead" ? "text-rose-700 border-rose-200 hover:bg-rose-50" : "bg-slate-900 hover:bg-slate-800 text-white"}
                                    onClick={() => setAdvanceOpen(s)}
                                    data-testid={`advance-stage-${s}`}>
                                → {displayEnum(s)}
                            </Button>
                        ))}
                        {isSuper && (
                            <Button size="sm" variant="outline"
                                    onClick={() => setOverrideOpen(true)}
                                    data-testid="override-stage-button">
                                Override stage
                            </Button>
                        )}
                        {canDelete && (
                            <Button size="sm" variant="outline"
                                    onClick={onDelete}
                                    className="text-rose-700 border-rose-200 hover:bg-rose-50"
                                    data-testid="delete-project-button">
                                Delete
                            </Button>
                        )}
                    </div>
                )}
            </header>

            {/* Tabs */}
            <nav className="border-b border-slate-200 flex gap-6" data-testid="project-tabs">
                {[
                    { k: "overview", l: "Overview" },
                    { k: "team", l: "Team" },
                    { k: "audit", l: "Audit" },
                ].map((t) => (
                    <button key={t.k}
                            onClick={() => setTab(t.k)}
                            className={`pb-2 text-sm font-medium transition-colors ${
                                tab === t.k
                                    ? "text-slate-900 border-b-2 border-slate-900"
                                    : "text-slate-500 hover:text-slate-700"
                            }`}
                            data-testid={`tab-${t.k}`}>
                        {t.l}
                    </button>
                ))}
                <Link to={`/projects/${project.id}/cost-codes`}
                      className="pb-2 text-sm font-medium text-slate-500 hover:text-slate-700"
                      data-testid="tab-cost-codes">
                    Cost Codes
                </Link>
                <Link to={`/projects/${project.id}/appraisals`}
                      className="pb-2 text-sm font-medium text-slate-500 hover:text-slate-700"
                      data-testid="tab-appraisals">
                    Appraisals
                </Link>
                {(perms.includes('budgets.view') || me?.is_super_admin) && (
                    <Link to={`/projects/${project.id}/budgets`}
                          className="pb-2 text-sm font-medium text-slate-500 hover:text-slate-700"
                          data-testid="tab-budgets">
                        Budgets
                    </Link>
                )}
                {(perms.includes('actuals.view') || me?.is_super_admin) && (
                    <Link to={`/projects/${project.id}/actuals`}
                          className="pb-2 text-sm font-medium text-slate-500 hover:text-slate-700"
                          data-testid="tab-actuals">
                        Actuals
                    </Link>
                )}
            </nav>

            {tab === "overview" && (
                <OverviewTab project={project} canViewSensitive={canViewSensitive}
                             refreshingFin={refreshingFin}
                             onRefreshFin={canViewSensitive ? refreshFinancials : null} />
            )}
            {tab === "team" && (
                <TeamTab projectId={project.id} canEdit={canEdit} onTeamChange={load} />
            )}
            {tab === "audit" && (
                <AuditTab projectId={project.id} />
            )}

            {advanceOpen && (
                <AdvanceStageModal project={project}
                                   target={advanceOpen}
                                   onClose={() => setAdvanceOpen(null)}
                                   onSuccess={() => { setAdvanceOpen(null); load(); }} />
            )}
            {overrideOpen && (
                <OverrideStageModal project={project}
                                    onClose={() => setOverrideOpen(false)}
                                    onSuccess={() => { setOverrideOpen(false); load(); }} />
            )}
        </div>
    );
}


// -------------------- Overview --------------------
function OverviewTab({ project, canViewSensitive, refreshingFin, onRefreshFin }) {
    return (
        <div className="space-y-4" data-testid="overview-tab">
            <CollapsibleSection title="Summary" defaultOpen>
                <KVGrid>
                    <KV k="Name" v={project.name} />
                    <KV k="Code" v={<span className="mono">{project.project_code}</span>} />
                    <KV k="Type" v={displayEnum(project.project_type)} />
                    <KV k="Tenure" v={displayEnum(project.tenure)} />
                    <KV k="Land ownership" v={displayEnum(project.land_ownership_method)} />
                    <KV k="Land type" v={project.land_type ? displayEnum(project.land_type) : "—"} />
                </KVGrid>
            </CollapsibleSection>

            <CollapsibleSection title="Site">
                <KVGrid>
                    <KV k="Address" v={project.site_address} />
                    <KV k="Postcode" v={<span className="mono">{project.site_postcode}</span>} />
                    <KV k="Local authority" v={project.local_authority || "—"} />
                    <KV k="Area (ha)" v={project.site_area_ha != null
                        ? <span className="mono tabular">{Number(project.site_area_ha).toFixed(4)}</span>
                        : "—"} />
                    <KV k="Area (acres)" v={project.site_area_acres != null
                        ? <span className="mono tabular">{Number(project.site_area_acres).toFixed(4)}</span>
                        : "—"} />
                </KVGrid>
            </CollapsibleSection>

            <CollapsibleSection title="Planning">
                <KVGrid>
                    <KV k="Ref" v={project.planning_ref || "—"} />
                    <KV k="Type" v={project.planning_type ? displayEnum(project.planning_type) : "—"} />
                    <KV k="Status" v={project.planning_status ? displayEnum(project.planning_status) : "—"} />
                    <KV k="Approval date" v={formatDate(project.planning_approval_date)} />
                    <KV k="Expiry date" v={formatDate(project.planning_expiry_date)} />
                    <KV k="Implementation required" v={project.implementation_required ? "Yes" : "No"} />
                    <KV k="S106 required" v={project.s106_required ? "Yes" : "No"} />
                    <KV k="CIL required" v={project.cil_required ? "Yes" : "No"} />
                </KVGrid>
            </CollapsibleSection>

            <CollapsibleSection title="Targets & delivery">
                <KVGrid>
                    <KV k="Units target" v={project.units_target ?? "—"} />
                    <KV k="Units actual" v={project.units_actual ?? "—"} />
                    <KV k="Affordable %" v={project.affordable_housing_pct != null
                        ? formatPercent(project.affordable_housing_pct) : "—"} />
                    <KV k="Target start" v={formatDate(project.target_start_date)} />
                    <KV k="Target PC" v={formatDate(project.target_pc_date)} />
                    <KV k="Actual start" v={formatDate(project.actual_start_date)} />
                    <KV k="Actual PC" v={formatDate(project.actual_pc_date)} />
                </KVGrid>
            </CollapsibleSection>

            {canViewSensitive && (
                <CollapsibleSection title="Financials (cached)" defaultOpen>
                    <div className="flex items-center justify-between mb-3">
                        <div className="text-xs text-slate-500">
                            Last refreshed: {project.financials_refreshed_at
                                ? formatDateTime(project.financials_refreshed_at)
                                : <span className="text-amber-700">never</span>}
                        </div>
                        {onRefreshFin && (
                            <Button size="sm" variant="outline"
                                    onClick={onRefreshFin}
                                    disabled={refreshingFin}
                                    data-testid="refresh-financials">
                                {refreshingFin
                                    ? <Loader2 size={14} className="animate-spin mr-1.5" />
                                    : <RefreshCw size={14} className="mr-1.5" />}
                                Refresh
                            </Button>
                        )}
                    </div>
                    <KVGrid>
                        <KV k="GDV actual" v={formatMoney(project.gdv_actual)} />
                        <KV k="Build cost actual" v={formatMoney(project.build_cost_actual)} />
                        <KV k="All-in cost" v={formatMoney(project.all_in_cost_actual)} />
                        <KV k="Profit actual" v={formatMoney(project.profit_actual)} />
                        <KV k="Margin actual" v={project.margin_actual_pct != null
                            ? formatPercent(project.margin_actual_pct) : "—"} />
                    </KVGrid>
                    <p className="mt-3 text-xs text-slate-500 italic">
                        Live rollups arrive in Prompt 2.5 (actuals) + 2.7 (cash flow). Today
                        the refresh endpoint returns zeroes and stamps the timestamp.
                    </p>
                </CollapsibleSection>
            )}

            {project.notes && (
                <CollapsibleSection title="Notes">
                    <p className="text-sm text-slate-700 whitespace-pre-wrap"
                       data-testid="project-notes">{project.notes}</p>
                </CollapsibleSection>
            )}
        </div>
    );
}


// -------------------- Team --------------------
function TeamTab({ projectId, canEdit, onTeamChange }) {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showHistory, setShowHistory] = useState(false);
    const [adding, setAdding] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const r = await api.get(`/projects/${projectId}/team`,
                { params: { history: showHistory } });
            setRows(r.data || []);
        } finally {
            setLoading(false);
        }
    }, [projectId, showHistory]);

    useEffect(() => { load(); }, [load]);

    const remove = async (tmId) => {
        if (!window.confirm("Remove this team member? Historical record preserved.")) return;
        try {
            await api.delete(`/projects/${projectId}/team/${tmId}`);
            toast.success("Team member removed");
            load();
            onTeamChange?.();
        } catch (err) {
            toast.error(err.friendlyMessage || "Remove failed");
        }
    };

    return (
        <div className="space-y-4" data-testid="team-tab">
            <div className="flex items-center justify-between">
                <label className="text-xs text-slate-600 flex items-center gap-2">
                    <input type="checkbox" checked={showHistory}
                           onChange={(e) => setShowHistory(e.target.checked)}
                           data-testid="team-history-toggle" />
                    Show removed members
                </label>
                {canEdit && (
                    <Button size="sm" className="bg-slate-900 hover:bg-slate-800 text-white"
                            onClick={() => setAdding(true)}
                            data-testid="add-team-member-button">
                        Add team member
                    </Button>
                )}
            </div>

            <div className="border border-slate-200 rounded-md bg-white overflow-hidden">
                <table className="w-full text-sm" data-testid="team-table">
                    <thead className="bg-slate-50 text-slate-600 text-[11px] uppercase tracking-widest">
                        <tr>
                            <th className="text-left p-3">User</th>
                            <th className="text-left p-3">Role</th>
                            <th className="text-left p-3">Primary</th>
                            <th className="text-left p-3">Assigned</th>
                            <th className="text-left p-3">Removed</th>
                            {canEdit && <th className="p-3" />}
                        </tr>
                    </thead>
                    <tbody>
                        {loading && (
                            <tr><td colSpan={6} className="p-8 text-center text-slate-400">
                                <Loader2 className="w-4 h-4 animate-spin inline" />
                            </td></tr>
                        )}
                        {!loading && rows.length === 0 && (
                            <tr><td colSpan={6} className="p-8 text-center text-slate-500"
                                    data-testid="team-empty">No team members assigned yet.</td></tr>
                        )}
                        {rows.map((r) => (
                            <tr key={r.id}
                                className={`border-t border-slate-200 ${r.removed_at ? "bg-slate-50 text-slate-500" : ""}`}
                                data-testid={`team-row-${r.id}`}>
                                <td className="p-3 mono text-xs">{String(r.user_id).slice(0, 8)}…</td>
                                <td className="p-3">{displayEnum(r.role_on_project)}</td>
                                <td className="p-3">{r.is_primary ? "★" : "—"}</td>
                                <td className="p-3 text-xs">{formatDate(r.assigned_at)}</td>
                                <td className="p-3 text-xs">{r.removed_at ? formatDate(r.removed_at) : "—"}</td>
                                {canEdit && (
                                    <td className="p-3 text-right">
                                        {!r.removed_at && (
                                            <button onClick={() => remove(r.id)}
                                                    className="text-xs text-rose-700 hover:underline"
                                                    data-testid={`remove-team-${r.id}`}>
                                                Remove
                                            </button>
                                        )}
                                    </td>
                                )}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {adding && (
                <AddTeamMemberModal projectId={projectId}
                                    onClose={() => setAdding(false)}
                                    onSuccess={() => { setAdding(false); load(); onTeamChange?.(); }} />
            )}
        </div>
    );
}


function AddTeamMemberModal({ projectId, onClose, onSuccess }) {
    const [users, setUsers] = useState([]);
    const [form, setForm] = useState({
        user_id: "", role_on_project: "Project_Lead", is_primary: false, notes: "",
    });
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        api.get("/users", { params: { page: 1, page_size: 200 } })
            .then((r) => setUsers(r.data.items || []));
    }, []);

    const submit = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            await api.post(`/projects/${projectId}/team`, form);
            toast.success("Team member added");
            onSuccess();
        } catch (err) {
            toast.error(err.friendlyMessage || "Add failed");
        } finally {
            setSaving(false);
        }
    };

    return (
        <ModalShell title="Add team member" onClose={onClose} testid="add-team-modal">
            <form onSubmit={submit} className="space-y-4">
                <div>
                    <label className="text-xs font-medium text-slate-700 mb-1 block">User</label>
                    <select value={form.user_id}
                            onChange={(e) => setForm({ ...form, user_id: e.target.value })}
                            className="w-full h-9 rounded-md border border-slate-300 px-3 text-sm"
                            required
                            data-testid="team-user-select">
                        <option value="">— Select user —</option>
                        {users.map((u) => (
                            <option key={u.id} value={u.id}>
                                {u.display_name} ({u.email})
                            </option>
                        ))}
                    </select>
                </div>
                <div>
                    <label className="text-xs font-medium text-slate-700 mb-1 block">Role</label>
                    <select value={form.role_on_project}
                            onChange={(e) => setForm({ ...form, role_on_project: e.target.value })}
                            className="w-full h-9 rounded-md border border-slate-300 px-3 text-sm"
                            data-testid="team-role-select">
                        {TEAM_ROLES.map((r) => (
                            <option key={r} value={r}>{displayEnum(r)}</option>
                        ))}
                    </select>
                </div>
                <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.is_primary}
                           onChange={(e) => setForm({ ...form, is_primary: e.target.checked })}
                           data-testid="team-primary-toggle" />
                    Primary for this role (only one active primary allowed)
                </label>
                <div>
                    <label className="text-xs font-medium text-slate-700 mb-1 block">Notes</label>
                    <Input value={form.notes}
                           onChange={(e) => setForm({ ...form, notes: e.target.value })}
                           data-testid="team-notes" />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                    <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
                    <Button type="submit" disabled={!form.user_id || saving}
                            className="bg-slate-900 hover:bg-slate-800 text-white"
                            data-testid="team-submit">
                        {saving && <Loader2 size={14} className="animate-spin mr-2" />}Add
                    </Button>
                </div>
            </form>
        </ModalShell>
    );
}


// -------------------- Audit --------------------
function AuditTab({ projectId }) {
    const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 50 });
    const [loading, setLoading] = useState(true);
    const [forbidden, setForbidden] = useState(false);

    useEffect(() => {
        setLoading(true);
        setForbidden(false);
        api.get("/audit", {
            params: { project_id: projectId, page: 1, page_size: 50 },
        })
        .then((r) => setData(r.data))
        .catch((err) => {
            if (err?.response?.status === 403) setForbidden(true);
            else toast.error(err.friendlyMessage || "Failed to load audit");
        })
        .finally(() => setLoading(false));
    }, [projectId]);

    if (forbidden) {
        return (
            <div className="border border-slate-200 rounded-md bg-white p-8 text-center text-sm text-slate-600"
                 data-testid="audit-forbidden">
                <AlertTriangle size={18} className="mx-auto text-amber-500 mb-2" />
                You don't have permission to view audit events. Ask an administrator
                for <span className="mono">audit.view</span>.
            </div>
        );
    }

    return (
        <div className="space-y-4" data-testid="audit-tab">
            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                </div>
            ) : (
                <div className="border border-slate-200 rounded-md overflow-hidden bg-white">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 text-slate-600 text-[11px] uppercase tracking-widest">
                            <tr>
                                <th className="text-left p-3 w-48">Timestamp</th>
                                <th className="text-left p-3">Actor</th>
                                <th className="text-left p-3">Action</th>
                                <th className="text-left p-3">Summary</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.items.length === 0 && (
                                <tr><td colSpan={4} className="p-8 text-center text-slate-400"
                                        data-testid="audit-empty">No audit events yet.</td></tr>
                            )}
                            {data.items.map((row) => (
                                <tr key={row.id} className="border-t border-slate-200"
                                    data-testid={`audit-row-${row.id}`}>
                                    <td className="p-3 text-slate-500 font-mono text-xs">
                                        {formatDateTime(row.created_at)}
                                    </td>
                                    <td className="p-3 text-slate-700 text-xs">
                                        {row.actor_name || row.actor_email || <span className="italic text-slate-400">System</span>}
                                    </td>
                                    <td className="p-3">
                                        <span className="text-xs px-2 py-0.5 rounded-full border bg-slate-50 text-slate-700 border-slate-200">
                                            {row.action}
                                        </span>
                                    </td>
                                    <td className="p-3 text-slate-700 text-xs">{row.summary}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <div className="px-3 py-2 border-t border-slate-200 text-xs text-slate-500">
                        Showing {data.items.length} of {data.total} events. See{" "}
                        <Link to={`/audit?project_id=${projectId}`}
                              className="underline decoration-dotted"
                              data-testid="audit-see-all">full audit page</Link>.
                    </div>
                </div>
            )}
        </div>
    );
}


// -------------------- Stage modals --------------------
function AdvanceStageModal({ project, target, onClose, onSuccess }) {
    const [reason, setReason] = useState("");
    const [saving, setSaving] = useState(false);
    const isDead = target === "Dead";

    const submit = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            await api.post(`/projects/${project.id}/stage/advance`, {
                new_stage: target,
                dead_reason: isDead ? reason : undefined,
            });
            toast.success(`Stage advanced to ${displayEnum(target)}`);
            onSuccess();
        } catch (err) {
            toast.error(err.friendlyMessage || "Advance failed");
        } finally {
            setSaving(false);
        }
    };

    return (
        <ModalShell title={`Advance to ${displayEnum(target)}`} onClose={onClose}
                    testid="advance-stage-modal">
            <form onSubmit={submit} className="space-y-4">
                <p className="text-sm text-slate-600">
                    Current stage: <b>{displayEnum(project.current_stage)}</b> →{" "}
                    <b>{displayEnum(target)}</b>
                </p>
                {isDead && (
                    <div>
                        <label className="text-xs font-medium text-slate-700 mb-1 block">
                            Reason (required)
                        </label>
                        <textarea value={reason}
                                  onChange={(e) => setReason(e.target.value)}
                                  rows={3}
                                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                                  required
                                  data-testid="advance-dead-reason" />
                    </div>
                )}
                <div className="flex justify-end gap-2">
                    <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
                    <Button type="submit"
                            disabled={saving || (isDead && !reason.trim())}
                            className="bg-slate-900 hover:bg-slate-800 text-white"
                            data-testid="advance-submit">
                        {saving && <Loader2 size={14} className="animate-spin mr-2" />}
                        Confirm
                    </Button>
                </div>
            </form>
        </ModalShell>
    );
}


function OverrideStageModal({ project, onClose, onSuccess }) {
    const [newStage, setNewStage] = useState("");
    const [reason, setReason] = useState("");
    const [deadReason, setDeadReason] = useState("");
    const [saving, setSaving] = useState(false);
    const isDead = newStage === "Dead";

    const canSubmit = newStage && newStage !== project.current_stage
        && reason.trim().length >= 10 && (!isDead || deadReason.trim());

    const submit = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            await api.post(`/projects/${project.id}/stage/override`, {
                new_stage: newStage,
                reason: reason.trim(),
                dead_reason: isDead ? deadReason.trim() : undefined,
            });
            toast.success(`Stage overridden to ${displayEnum(newStage)}`);
            onSuccess();
        } catch (err) {
            toast.error(err.friendlyMessage || "Override failed");
        } finally {
            setSaving(false);
        }
    };

    return (
        <ModalShell title="Override stage (super admin)" onClose={onClose}
                    testid="override-stage-modal">
            <div className="mb-3 p-3 rounded-md bg-amber-50 border border-amber-200 text-amber-900 text-xs flex gap-2">
                <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                Override bypasses the forward-only stage machine. All directors assigned
                to this project's entity will be notified.
            </div>
            <form onSubmit={submit} className="space-y-4">
                <div>
                    <label className="text-xs font-medium text-slate-700 mb-1 block">New stage</label>
                    <select value={newStage}
                            onChange={(e) => setNewStage(e.target.value)}
                            className="w-full h-9 rounded-md border border-slate-300 px-3 text-sm"
                            required
                            data-testid="override-new-stage">
                        <option value="">— Select —</option>
                        {STAGES.filter((s) => s !== project.current_stage)
                               .map((s) => (
                                   <option key={s} value={s}>{displayEnum(s)}</option>
                               ))}
                    </select>
                </div>
                <div>
                    <label className="text-xs font-medium text-slate-700 mb-1 block">
                        Reason (min 10 characters)
                    </label>
                    <textarea value={reason}
                              onChange={(e) => setReason(e.target.value)}
                              rows={3}
                              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                              required
                              data-testid="override-reason" />
                    <div className="text-xs text-slate-500 mt-1">
                        {reason.trim().length}/10 characters minimum
                    </div>
                </div>
                {isDead && (
                    <div>
                        <label className="text-xs font-medium text-slate-700 mb-1 block">
                            Dead reason (required)
                        </label>
                        <Input value={deadReason}
                               onChange={(e) => setDeadReason(e.target.value)}
                               data-testid="override-dead-reason" />
                    </div>
                )}
                <div className="flex justify-end gap-2">
                    <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
                    <Button type="submit" disabled={!canSubmit || saving}
                            className="bg-amber-700 hover:bg-amber-800 text-white"
                            data-testid="override-submit">
                        {saving && <Loader2 size={14} className="animate-spin mr-2" />}
                        Override
                    </Button>
                </div>
            </form>
        </ModalShell>
    );
}


// -------------------- Shared primitives --------------------
function ModalShell({ title, onClose, testid, children }) {
    return (
        <div className="fixed inset-0 bg-slate-900/40 flex items-start justify-center p-6 z-50 overflow-y-auto"
             onClick={onClose}
             data-testid={testid}>
            <div className="bg-white rounded-lg shadow-xl max-w-lg w-full p-6 my-8"
                 onClick={(e) => e.stopPropagation()}>
                <div className="flex items-start justify-between mb-4">
                    <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-600"
                            data-testid={`${testid}-close`}>
                        <X size={18} />
                    </button>
                </div>
                {children}
            </div>
        </div>
    );
}

function CollapsibleSection({ title, defaultOpen = false, children }) {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <section className="bg-white border border-slate-200 rounded-md">
            <button onClick={() => setOpen(!open)}
                    className="w-full flex items-center justify-between px-5 py-3 text-left"
                    data-testid={`section-${title.toLowerCase().replace(/[^a-z]+/g, '-')}`}>
                <div className="text-sm font-semibold uppercase tracking-widest text-slate-500">{title}</div>
                {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </button>
            {open && <div className="px-5 pb-5 pt-1 border-t border-slate-100">{children}</div>}
        </section>
    );
}

function KVGrid({ children }) {
    return <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">{children}</dl>;
}

function KV({ k, v }) {
    return (
        <div className="flex flex-col">
            <dt className="text-[11px] uppercase tracking-wider text-slate-500">{k}</dt>
            <dd className="text-slate-800 mt-0.5">{v ?? "—"}</dd>
        </div>
    );
}
