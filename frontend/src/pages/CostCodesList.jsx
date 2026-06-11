import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronDown, ChevronRight, Loader2, Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { displayEnum } from "@/lib/format";

const SECTION_HEADER_ORDER = [
    "1", "2", "3", "4", "5", "6", "7", "8", "9",
];

// Inside Construction section, group by these prefixes for visual nesting.
const CONSTRUCTION_PREFIX_ORDER = [
    "FAC", "SUB", "SUP", "INT", "FIT", "SER",
    "PRE", "EXB", "EXT", "PRL",
];

const PREFIX_LABELS = {
    FAC: "Facilitating Works", SUB: "Substructure", SUP: "Superstructure",
    INT: "Internal Finishes", FIT: "Fittings & Equipment", SER: "Services",
    PRE: "Prefab / MMC", EXB: "Existing Buildings", EXT: "External Works",
    PRL: "Preliminaries",
};

export default function CostCodesList() {
    const { me } = useAuth();
    const isAdmin = (me?.permissions || []).includes("cost_codes.admin")
                    || me?.is_super_admin;

    const [searchParams, setSearchParams] = useSearchParams();
    const initialQ = searchParams.get("q") ?? "";
    const initialStatus = searchParams.get("status") ?? "";
    const initialPrefix = searchParams.get("prefix") ?? "";

    const [q, setQ] = useState(initialQ);
    const [status, setStatus] = useState(initialStatus);
    const [prefix, setPrefix] = useState(initialPrefix);

    const [sections, setSections] = useState([]);
    const [codes, setCodes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [collapsed, setCollapsed] = useState({});

    useEffect(() => {
        let alive = true;
        setLoading(true);
        Promise.all([
            api.get("/cost-code-sections"),
            api.get("/cost-codes", { params: {
                q: q || undefined,
                status: status || undefined,
                prefix: prefix || undefined,
            } }),
        ]).then(([s, c]) => {
            if (!alive) return;
            setSections(s.data);
            setCodes(c.data);
        }).finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, [q, status, prefix]);

    const grouped = useMemo(() => {
        const bySection = {};
        // Initialise only parent groups (parent_section_id == null);
        // codes under Construction subgroups roll UP to "4" for the
        // visual nesting (see CONSTRUCTION_PREFIX_ORDER below).
        for (const s of sections) {
            if (!s.parent_section_id) {
                bySection[s.code] = { ...s, codes: [] };
            }
        }
        const sectionById = Object.fromEntries(sections.map((s) => [s.id, s]));
        for (const c of codes) {
            const sec = sectionById[c.section_id];
            if (!sec) continue;
            // If the code hangs off a subgroup, walk up to its parent.
            const parent = sec.parent_section_id
                ? sectionById[sec.parent_section_id]
                : sec;
            if (parent) bySection[parent.code]?.codes.push(c);
        }
        return bySection;
    }, [sections, codes]);

    const toggle = (key) => setCollapsed((s) => ({ ...s, [key]: !s[key] }));
    const updateFilter = (k, v) => {
        const next = new URLSearchParams(searchParams);
        if (v) next.set(k, v); else next.delete(k);
        setSearchParams(next);
    };

    return (
        <div className="space-y-6" data-testid="cost-codes-page">
            <header className="flex items-start justify-between gap-4">
                <div>
                    <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">
                        Module 06 — Reference Data
                    </div>
                    <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-1">
                        Cost Codes
                    </h1>
                    <p className="text-sm text-slate-600 mt-1 max-w-2xl">
                        Global classification for every cost line in the business. 9
                        parent groups · 10 Construction subgroups · 18 prefixes ·
                        130 codes. Used by appraisals, budgets, actuals, and Xero
                        mapping.
                    </p>
                </div>
                <div className="flex flex-col items-end gap-2">
                    <Link to="/cost-codes/admin"
                          className="inline-flex items-center gap-1 text-sm font-medium px-3 py-1.5 rounded-md text-white"
                          style={{ background: "#0F6A7A" }}
                          data-testid="open-cost-code-admin-link">
                        Open Cost-Code Admin →
                    </Link>
                    <Link to="/cost-codes/sections"
                          className="text-xs text-slate-600 hover:text-slate-900 underline decoration-dotted"
                          data-testid="cost-codes-sections-link">
                        Sections (read-only)
                    </Link>
                </div>
            </header>

            <section className="bg-white border border-slate-200 rounded-lg shadow-sm">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/60 flex flex-wrap items-center gap-3">
                    <div className="relative flex-1 min-w-[240px] max-w-md">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input value={q}
                               onChange={(e) => { setQ(e.target.value); updateFilter("q", e.target.value); }}
                               placeholder="Search code, name, description…"
                               className="pl-9 h-9 bg-white"
                               data-testid="cost-codes-search" />
                    </div>
                    <select value={status}
                            onChange={(e) => { setStatus(e.target.value); updateFilter("status", e.target.value); }}
                            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                            data-testid="filter-cc-status">
                        <option value="">All statuses</option>
                        <option>Active</option><option>Retired</option>
                    </select>
                    <select value={prefix}
                            onChange={(e) => { setPrefix(e.target.value); updateFilter("prefix", e.target.value); }}
                            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                            data-testid="filter-cc-prefix">
                        <option value="">All prefixes</option>
                        {["ACQ","PLN","DES","FAC","SUB","SUP","INT","FIT","SER",
                          "PRE","EXB","EXT","PRL","SAL","FIN","OHD","ACC","CTG"]
                          .map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                    <div className="ml-auto text-xs text-slate-500 font-mono">
                        {loading
                            ? <span className="flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" />Loading…</span>
                            : `${codes.length} codes`}
                    </div>
                </div>

                <div className="divide-y divide-slate-200">
                    {SECTION_HEADER_ORDER.map((sCode) => {
                        const sec = grouped[sCode];
                        if (!sec) return null;
                        const isOpen = !collapsed[sCode];
                        const showSubgroups = sec.code === "4";
                        return (
                            <div key={sec.code} data-testid={`section-${sec.code}`}>
                                <button onClick={() => toggle(sCode)}
                                        className="w-full px-6 py-3 flex items-center justify-between text-left hover:bg-slate-50">
                                    <div className="flex items-center gap-3">
                                        {isOpen
                                            ? <ChevronDown size={16} className="text-slate-400" />
                                            : <ChevronRight size={16} className="text-slate-400" />}
                                        <div>
                                            <div className="text-sm font-semibold text-slate-900">
                                                {sec.name}
                                            </div>
                                            <div className="text-xs text-slate-500 mt-0.5">
                                                {displayEnum(sec.default_p_and_l_category)}
                                                {" · "}
                                                {sec.is_direct_cost ? "Direct cost" : "Overhead"}
                                                {" · "}{sec.codes.length} codes
                                            </div>
                                        </div>
                                    </div>
                                    <span className="text-xs font-mono text-slate-400">
                                        order {sec.display_order}
                                    </span>
                                </button>

                                {isOpen && (
                                    <div>
                                        {showSubgroups
                                            ? CONSTRUCTION_PREFIX_ORDER.map((p) => {
                                                const subset = sec.codes.filter((c) => c.prefix === p);
                                                if (subset.length === 0) return null;
                                                return (
                                                    <div key={p} className="bg-slate-50/40">
                                                        <div className="px-12 py-2 text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                                                            {p} — {PREFIX_LABELS[p]}
                                                        </div>
                                                        <CodeRows codes={subset} indent={true} />
                                                    </div>
                                                );
                                            })
                                            : <CodeRows codes={sec.codes} indent={false} />}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </section>

            {!isAdmin && (
                <p className="text-xs text-slate-500">
                    You have read-only access to cost codes. Ask a Director or Finance
                    user to mutate.
                </p>
            )}
        </div>
    );
}


function CodeRows({ codes, indent }) {
    return (
        <div>
            {codes.map((c) => (
                <Link key={c.id} to={`/cost-codes/${c.id}`}
                      className="block border-t border-slate-200 hover:bg-slate-50/80 transition-colors"
                      data-testid={`cost-code-row-${c.code}`}>
                    <div className={`flex items-center gap-3 ${indent ? "pl-16 pr-6" : "px-12"} py-2.5`}>
                        <code className="text-xs tabular bg-slate-100 px-2 py-0.5 rounded text-slate-700 min-w-[68px]">
                            {c.code}
                        </code>
                        <div className="flex-1 min-w-0">
                            <div className={`text-sm ${c.status === "Retired" ? "line-through text-slate-400" : "text-slate-800"}`}>
                                {c.name}
                            </div>
                        </div>
                        <span className="text-[10px] uppercase tracking-wider text-slate-500 px-1.5 py-0.5 rounded border border-slate-200 bg-white">
                            {displayEnum(c.default_entity)}
                        </span>
                        <span className="text-[10px] uppercase tracking-wider text-slate-500 px-1.5 py-0.5 rounded border border-slate-200 bg-white">
                            {displayEnum(c.vat_treatment)}
                        </span>
                        {c.status === "Retired" && (
                            <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border border-rose-200 bg-rose-50 text-rose-700">
                                Retired
                            </span>
                        )}
                    </div>
                </Link>
            ))}
        </div>
    );
}
