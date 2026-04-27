import React, { useEffect, useState, useMemo, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { displayEnum } from "@/lib/format";
import { toast } from "sonner";

const SECTION_HEADER_ORDER = [
    "acquisition", "planning", "design", "construction",
    "sales_marketing", "finance", "company_overheads",
    "accounting", "contingency",
];

export default function ProjectCostCodes() {
    const { id: projectId } = useParams();
    const { me } = useAuth();
    const canEdit = (me?.permissions || []).includes("projects.edit")
                    || me?.is_super_admin;

    const [project, setProject] = useState(null);
    const [sections, setSections] = useState([]);
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [collapsed, setCollapsed] = useState({});
    const [overrideEdits, setOverrideEdits] = useState({});

    const load = useCallback(async () => {
        setLoading(true);
        const [p, s, r] = await Promise.all([
            api.get(`/projects/${projectId}`),
            api.get("/cost-code-sections"),
            api.get(`/projects/${projectId}/cost-codes`),
        ]);
        setProject(p.data); setSections(s.data); setRows(r.data);
        setLoading(false);
    }, [projectId]);

    useEffect(() => { load(); }, [load]);

    const grouped = useMemo(() => {
        const out = {};
        for (const s of sections) out[s.code] = { ...s, rows: [] };
        for (const r of rows) {
            const sec = sections.find((s) => s.id === r.section_id);
            if (sec) out[sec.code]?.rows.push(r);
        }
        return out;
    }, [sections, rows]);

    const toggle = (k) => setCollapsed((c) => ({ ...c, [k]: !c[k] }));

    const flipRow = async (row, isEnabled) => {
        if (!canEdit) return;
        try {
            const r = await api.patch(
                `/projects/${projectId}/cost-codes/${row.cost_code_id}`,
                { is_enabled: isEnabled }
            );
            setRows((all) => all.map((x) => x.id === row.id ? r.data : x));
        } catch (err) {
            toast.error(err.friendlyMessage || "Update failed");
        }
    };

    const saveOverride = async (row) => {
        const v = overrideEdits[row.id];
        if (v === undefined) return;
        try {
            const r = await api.patch(
                `/projects/${projectId}/cost-codes/${row.cost_code_id}`,
                { project_override_name: v || null }
            );
            setRows((all) => all.map((x) => x.id === row.id ? r.data : x));
            setOverrideEdits((e) => { const c = { ...e }; delete c[row.id]; return c; });
            toast.success("Override saved");
        } catch (err) {
            toast.error(err.friendlyMessage || "Save failed");
        }
    };

    const bulkToggle = async (sectionCode, isEnabled) => {
        if (!canEdit) return;
        try {
            const r = await api.post(
                `/projects/${projectId}/cost-codes/bulk-toggle`,
                { section_code: sectionCode, is_enabled: isEnabled }
            );
            toast.success(`${r.data.rows_updated} rows ${isEnabled ? "enabled" : "disabled"}`
                + (r.data.skipped_retired
                    ? ` · ${r.data.skipped_retired} retired skipped`
                    : ""));
            load();
        } catch (err) {
            toast.error(err.friendlyMessage || "Bulk toggle failed");
        }
    };

    if (loading || !project) {
        return (
            <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            </div>
        );
    }

    return (
        <div className="space-y-6" data-testid="project-cost-codes-page">
            <Link to={`/projects/${projectId}`}
                  className="text-sm text-slate-600 hover:text-slate-900 inline-flex items-center gap-1">
                <ArrowLeft size={14} /> Back to project
            </Link>

            <header>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mono">
                    {project.project_code}
                </div>
                <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-1">
                    {project.name} — Cost Codes
                </h1>
                <p className="text-sm text-slate-600 mt-1">
                    Toggle which cost codes apply to this project. Auto-populated on
                    project creation per <b>{displayEnum(project.project_type)}</b>{" "}
                    rules; refine here.
                </p>
            </header>

            <section className="bg-white border border-slate-200 rounded-lg shadow-sm divide-y divide-slate-200">
                {SECTION_HEADER_ORDER.map((sCode) => {
                    const sec = grouped[sCode];
                    if (!sec || sec.rows.length === 0) return null;
                    const isOpen = !collapsed[sCode];
                    const enabledCount = sec.rows.filter((r) => r.is_enabled).length;
                    return (
                        <div key={sec.code}
                             data-testid={`pcc-section-${sec.code}`}>
                            <div className="px-6 py-3 flex items-center justify-between hover:bg-slate-50">
                                <button onClick={() => toggle(sCode)}
                                        className="flex items-center gap-3 text-left flex-1">
                                    {isOpen
                                        ? <ChevronDown size={16} className="text-slate-400" />
                                        : <ChevronRight size={16} className="text-slate-400" />}
                                    <div>
                                        <div className="text-sm font-semibold text-slate-900">{sec.name}</div>
                                        <div className="text-xs text-slate-500">
                                            {enabledCount} of {sec.rows.length} enabled
                                        </div>
                                    </div>
                                </button>
                                {canEdit && (
                                    <div className="flex gap-2">
                                        <Button size="sm" variant="outline"
                                                onClick={() => bulkToggle(sec.code, true)}
                                                data-testid={`bulk-enable-${sec.code}`}>
                                            Enable all
                                        </Button>
                                        <Button size="sm" variant="outline"
                                                onClick={() => bulkToggle(sec.code, false)}
                                                data-testid={`bulk-disable-${sec.code}`}>
                                            Disable all
                                        </Button>
                                    </div>
                                )}
                            </div>
                            {isOpen && (
                                <table className="w-full text-sm border-t border-slate-200">
                                    <tbody>
                                        {sec.rows.map((r) => {
                                            const isRetired = r.cost_code_status === "Retired";
                                            return (
                                                <tr key={r.id}
                                                    className={`border-b border-slate-100 ${isRetired ? "opacity-60" : ""}`}
                                                    data-testid={`pcc-row-${r.code}`}>
                                                    <td className="px-12 py-2 w-[100px]">
                                                        <code className="text-xs tabular bg-slate-100 px-2 py-0.5 rounded">
                                                            {r.code}
                                                        </code>
                                                    </td>
                                                    <td className="py-2 text-slate-800">
                                                        {r.name}
                                                        {isRetired && (
                                                            <span className="ml-2 text-xs text-rose-700">(retired)</span>
                                                        )}
                                                    </td>
                                                    <td className="py-2 px-3 w-[260px]">
                                                        <Input
                                                            value={overrideEdits[r.id] !== undefined
                                                                ? overrideEdits[r.id]
                                                                : (r.project_override_name || "")}
                                                            onChange={(e) => setOverrideEdits((s) => ({
                                                                ...s, [r.id]: e.target.value,
                                                            }))}
                                                            onBlur={() => saveOverride(r)}
                                                            placeholder="Project override name…"
                                                            disabled={!canEdit || isRetired}
                                                            className="h-7 text-xs"
                                                            data-testid={`override-${r.code}`} />
                                                    </td>
                                                    <td className="py-2 px-3 w-[100px] text-right">
                                                        <label className="inline-flex items-center gap-1 cursor-pointer">
                                                            <input type="checkbox"
                                                                   checked={r.is_enabled}
                                                                   onChange={(e) => flipRow(r, e.target.checked)}
                                                                   disabled={!canEdit || isRetired}
                                                                   data-testid={`toggle-${r.code}`} />
                                                            <span className="text-xs">{r.is_enabled ? "On" : "Off"}</span>
                                                        </label>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            )}
                        </div>
                    );
                })}
            </section>
        </div>
    );
}
