/**
 * ScenarioComparator — side-by-side metrics across scenarios in a group.
 *
 * Mounted inside ScenariosPanel below the 2×2 slot grid.
 * Conditional render:
 *   - skeleton on pending,
 *   - empty (G4 copy) when fewer than 2 scenarios,
 *   - table otherwise.
 *
 * SOTA (S4): hover-highlight row+column, sortable headers (Base pinned),
 * delta column-slide-in animation. F4 — decimal.js everywhere.
 */
import React, { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowDown, ArrowUp, Check, GitBranch, X } from "lucide-react";

import { fetchComparator } from "@/lib/api";
import { computeScenarioDelta, formatDelta, formatMoney, fmtPct, D } from "@/lib/appraisalMath";

const METRICS = [
    { key: "gdv_total", label: "GDV", kind: "money", favourable: "positive" },
    { key: "total_cost", label: "Total cost", kind: "money", favourable: "negative" },
    { key: "profit_total", label: "Profit", kind: "money", favourable: "positive" },
    { key: "profit_on_cost_pct", label: "Profit on cost", kind: "percent", favourable: "positive" },
    { key: "profit_on_gdv_pct", label: "Profit on GDV", kind: "percent", favourable: "positive" },
    { key: "residual_land_value", label: "RLV", kind: "money", favourable: "positive" },
    { key: "total_units", label: "Total units", kind: "int", favourable: "positive" },
    { key: "passes_hurdle", label: "Passes hurdle", kind: "bool" },
];


function Skeleton() {
    return (
        <div className="border border-slate-200 rounded p-4 space-y-2"
             data-testid="scenario-comparator-skeleton">
            {[0, 1, 2, 3, 4].map((i) => (
                <div key={i} className="h-6 bg-slate-100 animate-pulse rounded" />
            ))}
        </div>
    );
}


function Empty() {
    return (
        <div className="border border-dashed border-slate-200 rounded p-8 text-center"
             data-testid="scenario-comparator-empty">
            <GitBranch className="w-12 h-12 mx-auto text-slate-300 mb-2" />
            <div className="text-sm font-medium text-slate-700">
                No scenarios to compare
            </div>
            <div className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                Create an Upside, Downside, or Sensitivity scenario to enable side-by-side comparison.
            </div>
        </div>
    );
}


function fmtCellValue(value, kind) {
    if (value === null || value === undefined) return "—";
    if (kind === "money") return formatMoney(value);
    if (kind === "percent") return fmtPct(value);
    if (kind === "int") return String(value);
    if (kind === "bool") return value ? "✓" : "✗";
    return String(value);
}


export default function ScenarioComparator({ groupId }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);
    const [sortKey, setSortKey] = useState(null);
    const [sortDir, setSortDir] = useState("asc");
    const [hoverCol, setHoverCol] = useState(null);
    const [hoverRow, setHoverRow] = useState(null);
    const reduceMotion = useReducedMotion();

    useEffect(() => {
        let active = true;
        setData(null);
        setErr(null);
        fetchComparator(groupId)
            .then((d) => active && setData(d))
            .catch((e) => active && setErr(e.friendlyMessage || "Failed to load comparator"));
        return () => { active = false; };
    }, [groupId]);

    const baseScenario = data?.scenarios?.find((s) => s.scenario_label === "Base");
    const orderedScenarios = useMemo(() => {
        if (!data?.scenarios) return [];
        const all = [...data.scenarios];
        if (!sortKey) return all;
        const base = all.find((s) => s.scenario_label === "Base");
        const rest = all.filter((s) => s.scenario_label !== "Base");
        rest.sort((a, b) => {
            const av = a[sortKey];
            const bv = b[sortKey];
            // Use Decimal for numeric ordering when applicable.
            const metric = METRICS.find((m) => m.key === sortKey);
            if (metric && (metric.kind === "money" || metric.kind === "percent" || metric.kind === "int")) {
                const aD = D(av ?? 0);
                const bD = D(bv ?? 0);
                if (aD.eq(bD)) return 0;
                const out = aD.gt(bD) ? 1 : -1;
                return sortDir === "asc" ? out : -out;
            }
            // Bool / null fallback.
            const al = av ? 1 : 0;
            const bl = bv ? 1 : 0;
            const out = al - bl;
            return sortDir === "asc" ? out : -out;
        });
        return base ? [base, ...rest] : rest;
    }, [data, sortKey, sortDir]);

    if (err) {
        return (
            <div className="text-xs text-rose-700 border border-rose-200 bg-rose-50 p-2 rounded"
                 data-testid="scenario-comparator-error">{err}</div>
        );
    }
    if (!data) return <Skeleton />;
    if (!data.scenarios || data.scenarios.length < 2) return <Empty />;

    const toggleSort = (key) => {
        if (sortKey === key) {
            setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        } else {
            setSortKey(key);
            setSortDir("desc");
        }
    };

    return (
        <div className="border border-slate-200 rounded overflow-hidden"
             data-testid="scenario-comparator">
            <div className="px-4 py-2 border-b border-slate-200 bg-slate-50">
                <h3 className="text-sm font-bold text-slate-900">Scenario comparator</h3>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="scenario-comparator-table">
                    <thead>
                        <tr className="border-b border-slate-200">
                            <th className="sticky left-0 bg-white text-left text-xs uppercase tracking-wide text-slate-500 font-semibold py-2 px-3">
                                Metric
                            </th>
                            {orderedScenarios.map((s, colIdx) => (
                                <motion.th key={s.scenario_label}
                                           initial={reduceMotion ? false : { opacity: 0, x: 30 }}
                                           animate={{ opacity: 1, x: 0 }}
                                           transition={{ duration: reduceMotion ? 0 : 0.25, delay: reduceMotion ? 0 : colIdx * 0.06 }}
                                           onMouseEnter={() => setHoverCol(s.scenario_label)}
                                           onMouseLeave={() => setHoverCol(null)}
                                           className={`text-left text-xs uppercase tracking-wide font-semibold py-2 px-3 ${
                                               hoverCol === s.scenario_label ? "bg-slate-100" : ""
                                           }`}
                                           data-testid={`comparator-header-${s.scenario_label}`}>
                                    <div className="flex items-center gap-1">
                                        <span>{s.scenario_label}</span>
                                        {s.scenario_label !== "Base" && s.version_number && (
                                            <span className="text-slate-400 font-normal">v{s.version_number}</span>
                                        )}
                                    </div>
                                </motion.th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {METRICS.map((metric) => (
                            <tr key={metric.key}
                                onMouseEnter={() => setHoverRow(metric.key)}
                                onMouseLeave={() => setHoverRow(null)}
                                className={`border-b border-slate-100 ${hoverRow === metric.key ? "bg-slate-50" : ""}`}
                                data-testid={`comparator-row-${metric.key}`}>
                                <th className="sticky left-0 bg-inherit text-left text-xs font-medium text-slate-700 py-2 px-3 cursor-pointer hover:text-slate-900"
                                    onClick={() => metric.kind !== "bool" && toggleSort(metric.key)}>
                                    <div className="flex items-center gap-1">
                                        <span>{metric.label}</span>
                                        {sortKey === metric.key && (
                                            sortDir === "asc"
                                                ? <ArrowUp className="w-3 h-3" />
                                                : <ArrowDown className="w-3 h-3" />
                                        )}
                                    </div>
                                </th>
                                {orderedScenarios.map((s, colIdx) => {
                                    const val = s[metric.key];
                                    const isBaseCol = s.scenario_label === "Base";
                                    const cellClass = `${hoverCol === s.scenario_label ? "bg-slate-100" : ""}`;
                                    if (metric.kind === "bool") {
                                        return (
                                            <td key={s.scenario_label}
                                                className={`py-2 px-3 ${cellClass}`}
                                                data-testid={`comparator-cell-${metric.key}-${s.scenario_label}`}>
                                                {val ? (
                                                    <Check className="w-4 h-4 text-emerald-600" />
                                                ) : (
                                                    <X className="w-4 h-4 text-rose-600" />
                                                )}
                                            </td>
                                        );
                                    }
                                    return (
                                        <td key={s.scenario_label}
                                            className={`py-2 px-3 font-mono text-xs ${cellClass}`}
                                            data-testid={`comparator-cell-${metric.key}-${s.scenario_label}`}>
                                            <div>{fmtCellValue(val, metric.kind)}</div>
                                            {!isBaseCol && baseScenario && val !== null && val !== undefined && baseScenario[metric.key] !== null && (
                                                (() => {
                                                    const delta = computeScenarioDelta(baseScenario, s, metric.key);
                                                    const fmt = formatDelta(delta, {
                                                        currency: metric.kind === "money",
                                                        percent: metric.kind === "percent",
                                                        favourable: metric.favourable,
                                                        dp: metric.kind === "int" ? 0 : (metric.kind === "percent" ? 2 : 0),
                                                    });
                                                    return (
                                                        <div className={`text-[10px] ${fmt.className}`}
                                                             data-testid={`comparator-delta-${metric.key}-${s.scenario_label}`}>
                                                            {fmt.text}
                                                        </div>
                                                    );
                                                })()
                                            )}
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
