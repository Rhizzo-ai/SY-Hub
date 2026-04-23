import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { Plus, Search, X, Loader2, Layers } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { displayEnum, formatPercent, formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const PROJECT_TYPES = [
    "Pure_Dev", "Dev_Build", "DB_Contract", "JV", "Main_Contract",
];
const STAGES = [
    "Lead", "Appraisal", "Deal_Pipeline", "Planning", "Pre_Con",
    "Construction", "Sales", "Post_Completion", "Closed", "Dead",
];
const STATUSES = ["Active", "On_Hold", "Dead", "Complete"];

function stageBadge(stage) {
    if (stage === "Dead") return "bg-rose-50 text-rose-800 border-rose-200";
    if (stage === "Closed") return "bg-slate-100 text-slate-700 border-slate-300";
    if (stage === "Construction" || stage === "Sales") {
        return "bg-emerald-50 text-emerald-800 border-emerald-200";
    }
    return "bg-blue-50 text-blue-800 border-blue-200";
}

function statusBadge(status) {
    if (status === "Dead") return "bg-rose-50 text-rose-800 border-rose-200";
    if (status === "On_Hold") return "bg-amber-50 text-amber-800 border-amber-200";
    if (status === "Complete") return "bg-slate-100 text-slate-700 border-slate-300";
    return "bg-emerald-50 text-emerald-800 border-emerald-200";
}

export default function ProjectsList() {
    const [params, setParams] = useSearchParams();
    const navigate = useNavigate();
    const { me } = useAuth();

    const canCreate = (me?.permissions || []).includes("projects.create") || me?.is_super_admin;
    const canViewSensitive =
        (me?.permissions || []).includes("projects.view_sensitive") || me?.is_super_admin;

    const q = params.get("q") ?? "";
    const ptype = params.get("project_type") ?? "";
    const stage = params.get("current_stage") ?? "";
    const status = params.get("status") ?? "";
    const page = parseInt(params.get("page") ?? "1", 10);
    const pageSize = 50;

    const [searchValue, setSearchValue] = useState(q);
    const [data, setData] = useState({ items: [], total: 0 });
    const [loading, setLoading] = useState(true);

    useEffect(() => { setSearchValue(q); }, [q]);

    useEffect(() => {
        let alive = true;
        setLoading(true);
        const query = {
            q: q || undefined,
            project_type: ptype || undefined,
            current_stage: stage || undefined,
            status: status || undefined,
            page, page_size: pageSize,
        };
        api.get("/projects", { params: query })
            .then((r) => { if (alive) setData(r.data); })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, [q, ptype, stage, status, page]);

    const setParam = (key, value) => {
        const next = new URLSearchParams(params);
        if (!value) next.delete(key); else next.set(key, value);
        if (key !== "page") next.set("page", "1");
        setParams(next);
    };

    const onSearchSubmit = (e) => {
        e.preventDefault();
        setParam("q", searchValue.trim());
    };

    const totalPages = Math.max(1, Math.ceil(data.total / pageSize));
    const filterChips = useMemo(() => [
        ptype && { key: "project_type", label: `Type: ${displayEnum(ptype)}` },
        stage && { key: "current_stage", label: `Stage: ${displayEnum(stage)}` },
        status && { key: "status", label: `Status: ${displayEnum(status)}` },
        q && { key: "q", label: `Search: "${q}"` },
    ].filter(Boolean), [ptype, stage, status, q]);

    return (
        <div className="space-y-6" data-testid="projects-list-page">
            <header className="flex items-start justify-between gap-4">
                <div>
                    <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">
                        Module 03
                    </div>
                    <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-1">
                        Projects
                    </h1>
                    <p className="text-sm text-slate-600 mt-1 max-w-xl">
                        Every development site from first lead through post-completion — the
                        project is the unit of truth for planning, build, sales and cashflow.
                    </p>
                </div>
                {canCreate && (
                    <Button
                        onClick={() => navigate("/projects/new")}
                        className="bg-slate-900 hover:bg-slate-800 text-white"
                        data-testid="new-project-button"
                    >
                        <Plus size={16} strokeWidth={1.75} className="mr-1.5" />
                        New Project
                    </Button>
                )}
            </header>

            <section className="bg-white border border-slate-200 rounded-lg shadow-sm">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/60 flex flex-wrap items-center gap-3">
                    <form onSubmit={onSearchSubmit} className="relative flex-1 min-w-[240px] max-w-md"
                          data-testid="projects-search-form">
                        <Search size={14} strokeWidth={1.75}
                                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input value={searchValue}
                               onChange={(e) => setSearchValue(e.target.value)}
                               placeholder="Search name, code, address…"
                               className="pl-9 h-9 bg-white"
                               data-testid="projects-search-input" />
                    </form>

                    <select value={ptype}
                            onChange={(e) => setParam("project_type", e.target.value)}
                            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                            data-testid="filter-project-type">
                        <option value="">All types</option>
                        {PROJECT_TYPES.map((t) => (
                            <option key={t} value={t}>{displayEnum(t)}</option>
                        ))}
                    </select>

                    <select value={stage}
                            onChange={(e) => setParam("current_stage", e.target.value)}
                            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                            data-testid="filter-stage">
                        <option value="">All stages</option>
                        {STAGES.map((s) => (
                            <option key={s} value={s}>{displayEnum(s)}</option>
                        ))}
                    </select>

                    <select value={status}
                            onChange={(e) => setParam("status", e.target.value)}
                            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                            data-testid="filter-status">
                        <option value="">All statuses</option>
                        {STATUSES.map((s) => (
                            <option key={s} value={s}>{displayEnum(s)}</option>
                        ))}
                    </select>

                    {filterChips.length > 0 && (
                        <button type="button"
                                onClick={() => setParams(new URLSearchParams())}
                                className="text-xs text-slate-600 hover:text-slate-900 underline decoration-dotted"
                                data-testid="clear-filters-button">
                            Clear all
                        </button>
                    )}

                    <div className="ml-auto text-xs text-slate-500 tabular font-mono">
                        {loading ? (
                            <span className="flex items-center gap-1.5">
                                <Loader2 size={12} className="animate-spin" />Loading…
                            </span>
                        ) : (
                            <>{data.total} {data.total === 1 ? "project" : "projects"}</>
                        )}
                    </div>
                </div>

                {filterChips.length > 0 && (
                    <div className="px-6 pt-3 flex flex-wrap gap-2" data-testid="filter-chips">
                        {filterChips.map((c) => (
                            <span key={c.key}
                                  className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 border border-slate-200 pl-3 pr-1 py-0.5 text-xs text-slate-700">
                                {c.label}
                                <button className="h-5 w-5 rounded-full hover:bg-slate-200 flex items-center justify-center"
                                        onClick={() => setParam(c.key, "")}
                                        data-testid={`remove-chip-${c.key}`}>
                                    <X size={11} />
                                </button>
                            </span>
                        ))}
                    </div>
                )}

                <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="projects-table">
                        <thead>
                            <tr className="bg-slate-50 border-y border-slate-200">
                                <th className="text-left px-4 py-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500 w-[14%]">Code</th>
                                <th className="text-left px-4 py-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500 w-[24%]">Name</th>
                                <th className="text-left px-4 py-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500 w-[12%]">Type</th>
                                <th className="text-left px-4 py-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500 w-[14%]">Stage</th>
                                <th className="text-left px-4 py-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500 w-[10%]">Status</th>
                                <th className="text-left px-4 py-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500">Site</th>
                                {canViewSensitive && (
                                    <th className="text-right px-4 py-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500 w-[10%]">Margin %</th>
                                )}
                            </tr>
                        </thead>
                        <tbody>
                            {loading && data.items.length === 0 && (
                                Array.from({ length: 4 }).map((_, i) => (
                                    <tr key={i} className="border-b border-slate-200">
                                        <td colSpan={canViewSensitive ? 7 : 6} className="px-4 py-3">
                                            <div className="h-3 w-full rounded bg-slate-200 animate-pulse" />
                                        </td>
                                    </tr>
                                ))
                            )}
                            {!loading && data.items.length === 0 && (
                                <tr>
                                    <td colSpan={canViewSensitive ? 7 : 6}
                                        className="px-4 py-16 text-center text-slate-500"
                                        data-testid="projects-empty-state">
                                        <Layers className="mx-auto mb-2 text-slate-300" size={28} />
                                        <div className="font-heading text-lg text-slate-700">No projects match these filters.</div>
                                        {canCreate && (
                                            <p className="text-sm mt-1">
                                                Try clearing filters, or{" "}
                                                <Link to="/projects/new"
                                                      className="underline decoration-dotted text-slate-900"
                                                      data-testid="empty-state-new-link">
                                                    create a new project
                                                </Link>.
                                            </p>
                                        )}
                                    </td>
                                </tr>
                            )}
                            {data.items.map((p) => (
                                <tr key={p.id}
                                    onClick={() => navigate(`/projects/${p.id}`)}
                                    className="border-b border-slate-200 hover:bg-slate-50/80 cursor-pointer transition-colors"
                                    data-testid={`project-row-${p.id}`}>
                                    <td className="px-4 py-3 mono tabular text-slate-700">{p.project_code}</td>
                                    <td className="px-4 py-3">
                                        <div className="font-medium text-slate-900">{p.name}</div>
                                        <div className="text-xs text-slate-500">{p.site_postcode}</div>
                                    </td>
                                    <td className="px-4 py-3 text-slate-700">{displayEnum(p.project_type)}</td>
                                    <td className="px-4 py-3">
                                        <span className={`text-xs px-2 py-0.5 rounded-full border ${stageBadge(p.current_stage)}`}>
                                            {displayEnum(p.current_stage)}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`text-xs px-2 py-0.5 rounded-full border ${statusBadge(p.status)}`}>
                                            {displayEnum(p.status)}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-slate-700">
                                        <div className="text-xs truncate max-w-[240px]">{p.site_address}</div>
                                    </td>
                                    {canViewSensitive && (
                                        <td className="px-4 py-3 text-right mono tabular text-slate-700">
                                            {p.margin_actual_pct != null && Number(p.margin_actual_pct) !== 0
                                                ? formatPercent(p.margin_actual_pct)
                                                : "—"}
                                        </td>
                                    )}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                <div className="px-6 py-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
                    <div data-testid="pagination-summary">
                        Page <span className="mono tabular">{page}</span> of{" "}
                        <span className="mono tabular">{totalPages}</span>
                        {" · "}
                        <span className="mono tabular">{pageSize}</span> per page
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm"
                                disabled={page <= 1}
                                onClick={() => setParam("page", String(page - 1))}
                                data-testid="page-prev">Previous</Button>
                        <Button variant="outline" size="sm"
                                disabled={page >= totalPages}
                                onClick={() => setParam("page", String(page + 1))}
                                data-testid="page-next">Next</Button>
                    </div>
                </div>
            </section>
        </div>
    );
}
