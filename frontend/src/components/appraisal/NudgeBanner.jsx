/**
 * NudgeBanner — gentle pressure on directors to log Go/No_Go/Defer on the
 * current Approved Base appraisal.
 *
 * Locked decisions:
 *   G1 — NOT dismissible.
 *   G2 — mounts on ProjectDetail.jsx ONLY.
 *
 * SOTA:
 *   S3 — avatar stack assembled client-side from /decisions endpoint.
 *   S6 — framer-motion enter/exit slide-down/up.
 *   S10 — useReducedMotion gates animation.
 *
 * Listens for window event `nudge-refresh` to re-fetch (F3).
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { AlertCircle } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import {
    Tooltip, TooltipContent, TooltipProvider, TooltipTrigger,
} from "@/components/ui/tooltip";

import { fetchNudge, fetchDecisions, api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const CORE_TYPES = new Set(["Go", "No_Go", "Defer"]);


function initials(name) {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0][0].toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}


function avatarColour(uid) {
    const palette = [
        "bg-rose-500", "bg-amber-500", "bg-emerald-500", "bg-teal-500",
        "bg-sky-500", "bg-indigo-500", "bg-purple-500", "bg-fuchsia-500",
    ];
    let h = 0;
    for (const c of String(uid)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    return palette[h % palette.length];
}


function DeciderAvatar({ decision, name }) {
    const colour = avatarColour(decision.decision_maker_user_id);
    const tone = decision.decision_type === "Go"
        ? "ring-emerald-400"
        : decision.decision_type === "No_Go"
            ? "ring-rose-400"
            : "ring-amber-400";
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <div className={`w-6 h-6 rounded-full ${colour} text-white text-[10px] font-bold flex items-center justify-center ring-2 ${tone} ring-offset-2 ring-offset-amber-50 cursor-default`}
                     data-testid={`nudge-avatar-${decision.decision_maker_user_id}`}>
                    {initials(name)}
                </div>
            </TooltipTrigger>
            <TooltipContent>
                <div className="text-xs">
                    <div className="font-semibold">{name}</div>
                    <div className="text-slate-500">
                        {decision.decision_type.replace("_", " ")}
                        {" · "}
                        {formatDistanceToNow(new Date(decision.decision_date), { addSuffix: true })}
                    </div>
                </div>
            </TooltipContent>
        </Tooltip>
    );
}


function GhostSlot({ idx }) {
    return (
        <div className="w-6 h-6 rounded-full border-2 border-dashed border-amber-400/70"
             data-testid={`nudge-avatar-empty-${idx}`} />
    );
}


export default function NudgeBanner({ projectId }) {
    const [nudge, setNudge] = useState(null);
    const [decisions, setDecisions] = useState([]);
    const [names, setNames] = useState({});
    const reduceMotion = useReducedMotion();
    const { me } = useAuth();
    const lastDecisionsForRef = useRef(null);

    const canApprove = me?.is_super_admin || (me?.permissions || []).includes("appraisals.approve");

    const load = useCallback(async () => {
        try {
            const n = await fetchNudge(projectId);
            setNudge(n);
            if (n.current_appraisal_id) {
                const d = await fetchDecisions(n.current_appraisal_id);
                const corePerUser = new Map();
                (d.items || []).forEach((row) => {
                    if (!CORE_TYPES.has(row.decision_type)) return;
                    if (!corePerUser.has(row.decision_maker_user_id)) {
                        corePerUser.set(row.decision_maker_user_id, row);
                    }
                });
                setDecisions(Array.from(corePerUser.values()));
                lastDecisionsForRef.current = n.current_appraisal_id;
            } else {
                setDecisions([]);
            }
        } catch (_) {
            setNudge(null);
        }
    }, [projectId]);

    useEffect(() => { load(); }, [load]);

    // F3 — listen for nudge-refresh dispatched after a decision is logged.
    useEffect(() => {
        const onRefresh = (ev) => {
            if (!ev.detail?.projectId || ev.detail.projectId === projectId) {
                load();
            }
        };
        window.addEventListener("nudge-refresh", onRefresh);
        return () => window.removeEventListener("nudge-refresh", onRefresh);
    }, [load, projectId]);

    // Resolve user names for the avatar tooltips.
    useEffect(() => {
        decisions.forEach((d) => {
            const uid = d.decision_maker_user_id;
            if (names[uid]) return;
            api.get(`/users/${uid}`)
                .then((r) => setNames((p) => ({ ...p, [uid]: r.data?.full_name || r.data?.email || uid })))
                .catch(() => setNames((p) => ({ ...p, [uid]: `${uid.slice(0, 8)}…` })));
        });
    }, [decisions, names]);

    const visible = Boolean(nudge?.should_show);
    const ghostCount = Math.max(0, (nudge?.threshold || 0) - decisions.length);

    return (
        <AnimatePresence>
            {visible && (
                <motion.div
                    initial={reduceMotion ? false : { opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -10 }}
                    transition={{ duration: reduceMotion ? 0 : 0.2 }}
                    className="border border-amber-300 bg-amber-50 text-amber-900 rounded p-4 flex items-start gap-3"
                    data-testid="nudge-banner"
                >
                    <AlertCircle className="w-7 h-7 flex-shrink-0 text-amber-600 mt-0.5" />
                    <div className="flex-1">
                        <div className="font-semibold text-sm">
                            Decision threshold not yet met
                        </div>
                        <div className="text-xs mt-0.5">{nudge.message}</div>

                        <TooltipProvider delayDuration={150}>
                            <div className="flex items-center gap-2 mt-2">
                                {decisions.map((d) => (
                                    <DeciderAvatar key={d.decision_maker_user_id}
                                                   decision={d}
                                                   name={names[d.decision_maker_user_id] || `${d.decision_maker_user_id.slice(0, 8)}…`} />
                                ))}
                                {Array.from({ length: ghostCount }).map((_, i) => (
                                    <GhostSlot key={`ghost-${i}`} idx={i} />
                                ))}
                            </div>
                        </TooltipProvider>

                        <div className="mt-2">
                            {nudge.actor_has_decided ? (
                                <span className="text-xs text-emerald-700 font-medium"
                                      data-testid="nudge-thanks">
                                    Thanks — your decision is recorded. Waiting on {Math.max(0, nudge.threshold - nudge.distinct_decision_makers)} more.
                                </span>
                            ) : canApprove ? (
                                <Link to={`/appraisals/${nudge.current_appraisal_id}?tab=decisions`}
                                      className="inline-flex items-center text-xs font-semibold text-amber-900 hover:underline"
                                      data-testid="nudge-cta-log-decision">
                                    Log your decision →
                                </Link>
                            ) : (
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <span className="text-xs text-slate-500 italic cursor-help"
                                              data-testid="nudge-no-perm">
                                            Awaiting director sign-off
                                        </span>
                                    </TooltipTrigger>
                                    <TooltipContent>
                                        Contact a director to log decisions.
                                    </TooltipContent>
                                </Tooltip>
                            )}
                        </div>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
