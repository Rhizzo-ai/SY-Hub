/**
 * RevisionTimeline — vertical lineage of versions for one (group, scenario).
 *
 * Mounted inside SummaryTab right column below the RLV panel (per Build Pack §3.1).
 * Click any node → navigate to that appraisal id (G6).
 * Hover non-v1 node → HoverCard with delta chips + reason + summary (S8).
 *
 * Empty state (S7): only v1 exists, no revisions.
 *
 * Keyboard nav (S9): j/k walk down/up the lineage. Component must be focused.
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { Clock } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import { fetchRevisions } from "@/lib/api";
import { formatMoney, formatDelta, D } from "@/lib/appraisalMath";
import { STATE_BADGE } from "@/components/appraisal/atoms";
import {
    HoverCard, HoverCardContent, HoverCardTrigger,
} from "@/components/ui/hover-card";

const READ_ONLY_STATES = new Set(["Superseded", "Withdrawn", "Rejected"]);

function Skeleton() {
    return (
        <div className="space-y-3" data-testid="revision-timeline-skeleton">
            {[0, 1, 2].map((i) => (
                <div key={i} className="flex gap-3 items-start">
                    <div className="w-3 h-3 mt-1.5 rounded-full bg-slate-200 animate-pulse" />
                    <div className="flex-1 h-12 rounded bg-slate-100 animate-pulse" />
                </div>
            ))}
        </div>
    );
}

function Empty() {
    return (
        <div className="text-center py-6 px-4 border border-dashed border-slate-200 rounded"
             data-testid="revision-timeline-empty">
            <Clock className="w-12 h-12 mx-auto text-slate-300 mb-2" />
            <div className="text-sm font-medium text-slate-700">
                No revisions yet
            </div>
            <div className="text-xs text-slate-500 mt-1">
                This is the initial draft. New versions appear here when created.
            </div>
        </div>
    );
}

function DeltaChip({ value, label, favourable = "positive" }) {
    const d = formatDelta(D(value), { currency: true, dp: 0, favourable });
    return (
        <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500">{label}</span>
            <span className={`font-mono ${d.className}`}>{d.text}</span>
        </div>
    );
}

function NodeContent({ a, rev, isCurrent }) {
    const ts = a.created_at || a.updated_at;
    return (
        <div className={`flex-1 border rounded p-2 cursor-pointer transition-colors hover:bg-slate-50 ${
            isCurrent ? "border-emerald-300 ring-1 ring-emerald-200 bg-emerald-50/30" : "border-slate-200"
        }`}>
            <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-slate-700">v{a.version_number}</span>
                <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium border rounded ${STATE_BADGE[a.status]}`}>
                    {a.status}
                </span>
                {isCurrent && (
                    <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-semibold bg-emerald-600 text-white rounded">
                        Current
                    </span>
                )}
            </div>
            {ts && (
                <div className="text-[10px] text-slate-500 mt-1">
                    {formatDistanceToNow(new Date(ts), { addSuffix: true })}
                </div>
            )}
            {rev && (
                <div className="text-[10px] text-slate-500 mt-0.5 italic line-clamp-1">
                    {rev.revision_reason.replace(/_/g, " ")}
                </div>
            )}
        </div>
    );
}

export default function RevisionTimeline({ appraisalId }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);
    const navigate = useNavigate();
    const reduceMotion = useReducedMotion();
    const containerRef = useRef(null);

    useEffect(() => {
        let active = true;
        setData(null);
        setErr(null);
        fetchRevisions(appraisalId)
            .then((d) => active && setData(d))
            .catch((e) => active && setErr(e.friendlyMessage || "Failed to load revisions"));
        return () => { active = false; };
    }, [appraisalId]);

    const revsByTo = useMemo(() => {
        const m = new Map();
        (data?.revisions || []).forEach((r) => m.set(r.appraisal_id_to, r));
        return m;
    }, [data]);

    // S9 — j/k walk through nodes.
    useEffect(() => {
        const onKey = (e) => {
            if (!containerRef.current?.contains(document.activeElement)) return;
            if (e.key !== "j" && e.key !== "k") return;
            const items = data?.appraisals || [];
            if (items.length === 0) return;
            const currentIdx = items.findIndex((x) => x.id === appraisalId);
            const next = e.key === "j"
                ? Math.min(items.length - 1, currentIdx + 1)
                : Math.max(0, currentIdx - 1);
            if (next !== currentIdx && items[next]) {
                e.preventDefault();
                navigate(`/appraisals/${items[next].id}`);
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [data, appraisalId, navigate]);

    if (err) {
        return (
            <div className="text-xs text-rose-700 border border-rose-200 bg-rose-50 p-2 rounded"
                 data-testid="revision-timeline-error">{err}</div>
        );
    }
    if (!data) return <Skeleton />;

    const apps = data.appraisals || [];
    if (apps.length <= 1 && (data.revisions || []).length === 0) {
        return (
            <div>
                <div className="text-xs uppercase tracking-wide font-semibold text-slate-500 mb-2">
                    Version timeline
                </div>
                <Empty />
            </div>
        );
    }

    return (
        <div data-testid="revision-timeline" ref={containerRef} tabIndex={0}
             className="focus:outline-none focus:ring-1 focus:ring-slate-300 rounded p-1 -m-1">
            <div className="text-xs uppercase tracking-wide font-semibold text-slate-500 mb-2">
                Version timeline
            </div>
            <ol className="relative border-l-2 border-slate-200 pl-4 space-y-3">
                {apps.map((a, idx) => {
                    const rev = revsByTo.get(a.id);
                    const isCurrent = a.is_current;
                    const isReadOnly = !isCurrent || READ_ONLY_STATES.has(a.status);
                    const node = (
                        <motion.li
                            key={a.id}
                            initial={reduceMotion ? false : { opacity: 0, x: -8 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ duration: reduceMotion ? 0 : 0.18, delay: reduceMotion ? 0 : idx * 0.04 }}
                            className="relative"
                            onClick={() => navigate(`/appraisals/${a.id}`)}
                            data-testid={`revision-timeline-node-${a.version_number}${isCurrent ? "-current" : ""}`}
                            data-readonly={isReadOnly ? "true" : "false"}
                        >
                            <span className={`absolute -left-[22px] top-2 w-3 h-3 rounded-full border-2 ${
                                isCurrent ? "bg-emerald-500 border-emerald-600" : "bg-slate-300 border-slate-400"
                            }`} />
                            <NodeContent a={a} rev={rev} isCurrent={isCurrent} />
                        </motion.li>
                    );
                    if (!rev) return node;
                    return (
                        <HoverCard key={a.id} openDelay={150}>
                            <HoverCardTrigger asChild>{node}</HoverCardTrigger>
                            <HoverCardContent className="w-80" data-testid={`revision-timeline-hover-${a.version_number}`}>
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                        <span className="text-xs uppercase tracking-wide font-semibold text-slate-500">
                                            {rev.revision_reason.replace(/_/g, " ")}
                                        </span>
                                    </div>
                                    <div className="space-y-1 border-y border-slate-100 py-2">
                                        <DeltaChip value={rev.delta_gdv} label="Δ GDV" favourable="positive" />
                                        <DeltaChip value={rev.delta_total_cost} label="Δ Cost" favourable="negative" />
                                        <DeltaChip value={rev.delta_profit} label="Δ Profit" favourable="positive" />
                                    </div>
                                    <div className="text-xs text-slate-700 line-clamp-3">
                                        {rev.summary_of_changes}
                                    </div>
                                </div>
                            </HoverCardContent>
                        </HoverCard>
                    );
                })}
            </ol>
        </div>
    );
}
