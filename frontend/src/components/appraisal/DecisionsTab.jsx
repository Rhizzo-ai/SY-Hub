/**
 * DecisionsTab — chronological decision list (left 2/3) + Log Decision form (right 1/3).
 *
 * Server gate (R0 confirmed): POST /decisions enforces is_current=true AND
 * version_number match. NO status check on the server side. UI form gate
 * therefore: user.appraisals.approve AND appraisal.is_current === true.
 *
 * SOTA:
 *   S2 — optimistic UI on submit.
 *   S6 — framer-motion: card slide-in.
 *   S7 — empty state with Gavel icon.
 *   S9 — Esc closes modal (n/a here, no modal); Cmd+Enter submits.
 *   S10 — useReducedMotion gates animations.
 *
 * Decision E — date picker uses date-fns-tz Europe/London for default + max.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Gavel, Loader2 } from "lucide-react";
import { format } from "date-fns";
import { formatInTimeZone } from "date-fns-tz";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

import { fetchDecisions, logDecision } from "@/lib/api";
import { api } from "@/lib/api";

const DECISION_TYPES = [
    { value: "Go", label: "Go", tone: "bg-emerald-100 text-emerald-800 border-emerald-200" },
    { value: "No_Go", label: "No-Go", tone: "bg-rose-100 text-rose-800 border-rose-200" },
    { value: "Defer", label: "Defer", tone: "bg-amber-100 text-amber-800 border-amber-200" },
    { value: "Conditional_Go", label: "Conditional Go", tone: "bg-blue-100 text-blue-800 border-blue-200" },
    { value: "Request_Revision", label: "Request revision", tone: "bg-purple-100 text-purple-800 border-purple-200" },
    { value: "Correction", label: "Correction", tone: "bg-slate-100 text-slate-700 border-slate-300" },
];


function todayLondonISO() {
    return formatInTimeZone(new Date(), "Europe/London", "yyyy-MM-dd");
}


function ListSkeleton() {
    return (
        <div className="space-y-3" data-testid="decisions-skeleton">
            {[0, 1, 2].map((i) => (
                <div key={i} className="h-24 bg-slate-100 rounded animate-pulse" />
            ))}
        </div>
    );
}


function DecisionTypePill({ type }) {
    const meta = DECISION_TYPES.find((t) => t.value === type) || DECISION_TYPES[5];
    return (
        <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded ${meta.tone}`}>
            {meta.label}
        </span>
    );
}


function DecisionCard({ decision, getName, pending, allDecisionsById, scrollToId }) {
    const [showRationale, setShowRationale] = useState(false);
    const [showCond, setShowCond] = useState(false);
    const [showAssumps, setShowAssumps] = useState(false);
    const name = getName(decision.decision_maker_user_id);

    return (
        <motion.div
            layout
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: pending ? 0.55 : 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.22 }}
            aria-busy={pending ? "true" : "false"}
            id={`decision-card-${decision.id}`}
            className={`border border-slate-200 rounded p-3 space-y-1.5 bg-white ${pending ? "border-dashed" : ""}`}
            data-testid={pending ? "decision-row-pending" : `decision-row-${decision.id}`}
        >
            <div className="flex items-center justify-between">
                <DecisionTypePill type={decision.decision_type} />
                <span className="text-xs text-slate-500 font-mono">
                    {format(new Date(decision.decision_date), "dd MMM yyyy")}
                </span>
            </div>
            <div className="text-xs text-slate-600">
                <span className="font-medium text-slate-900">{name}</span>
                {decision.appraisal_version != null && (
                    <span className="text-slate-400"> · on v{decision.appraisal_version}</span>
                )}
            </div>
            <div className={`text-sm text-slate-700 ${showRationale ? "" : "line-clamp-3"}`}>
                {decision.decision_rationale}
            </div>
            {decision.decision_rationale && decision.decision_rationale.length > 180 && (
                <button onClick={() => setShowRationale((s) => !s)}
                        className="text-xs text-slate-500 hover:text-slate-900 underline">
                    {showRationale ? "Show less" : "Read more"}
                </button>
            )}
            {decision.decision_type === "Conditional_Go" && decision.conditions && (
                <div className="border-t border-slate-100 pt-1.5">
                    <button onClick={() => setShowCond((s) => !s)}
                            className="text-xs text-blue-700 hover:underline">
                        {showCond ? "Hide" : "Show"} conditions
                    </button>
                    {showCond && (
                        <div className="text-xs text-slate-600 mt-1 whitespace-pre-wrap">
                            {decision.conditions}
                        </div>
                    )}
                </div>
            )}
            {decision.key_assumptions_challenged && (
                <div className="border-t border-slate-100 pt-1.5">
                    <button onClick={() => setShowAssumps((s) => !s)}
                            className="text-xs text-purple-700 hover:underline">
                        {showAssumps ? "Hide" : "Show"} assumptions challenged
                    </button>
                    {showAssumps && (
                        <div className="text-xs text-slate-600 mt-1 whitespace-pre-wrap">
                            {decision.key_assumptions_challenged}
                        </div>
                    )}
                </div>
            )}
            {decision.correction_of_decision_id && (
                <button onClick={() => scrollToId(decision.correction_of_decision_id)}
                        className="text-xs italic text-slate-500 hover:text-slate-900 underline"
                        data-testid={`decision-correction-link-${decision.id}`}>
                    Correction of earlier decision
                </button>
            )}
        </motion.div>
    );
}


function LogDecisionForm({ appraisal, existingDecisions, onPosted, onError }) {
    const [type, setType] = useState("Go");
    const [date, setDate] = useState(todayLondonISO());
    const [rationale, setRationale] = useState("");
    const [conditions, setConditions] = useState("");
    const [assumps, setAssumps] = useState("");
    const [correctionOf, setCorrectionOf] = useState("");
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState(null);

    const todayMax = useMemo(() => todayLondonISO(), []);
    const trimmedRationale = rationale.trim();
    const trimmedConditions = conditions.trim();

    const valid = useMemo(() => {
        if (trimmedRationale.length < 10) return false;
        if (type === "Conditional_Go" && trimmedConditions.length === 0) return false;
        if (type === "Correction" && !correctionOf) return false;
        return Boolean(date);
    }, [type, date, trimmedRationale, trimmedConditions, correctionOf]);

    const reset = () => {
        setType("Go");
        setDate(todayLondonISO());
        setRationale("");
        setConditions("");
        setAssumps("");
        setCorrectionOf("");
        setErr(null);
    };

    const submit = async (e) => {
        e?.preventDefault?.();
        if (!valid || busy) return;
        setBusy(true);
        setErr(null);
        const payload = {
            appraisal_version: appraisal.version_number,
            decision_type: type,
            decision_date: date,
            decision_rationale: trimmedRationale,
            conditions: type === "Conditional_Go" ? trimmedConditions : null,
            key_assumptions_challenged: assumps.trim() || null,
            correction_of_decision_id: type === "Correction" ? correctionOf : null,
            supporting_documents: [],
        };
        const tempId = `tmp-${Date.now()}`;
        const optimistic = {
            id: tempId,
            ...payload,
            decision_maker_user_id: "self",
            created_at: new Date().toISOString(),
        };
        onPosted(optimistic, tempId);
        try {
            const row = await logDecision(appraisal.id, payload);
            onPosted(row, tempId, true);
            reset();
            window.dispatchEvent(new CustomEvent("nudge-refresh", {
                detail: { projectId: appraisal.project_id },
            }));
            toast.success("Decision logged.");
        } catch (e2) {
            setErr(e2.friendlyMessage || "Failed to log decision");
            onError(tempId);
        } finally {
            setBusy(false);
        }
    };

    const onKeyDown = (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit(e);
    };

    return (
        <form onSubmit={submit} onKeyDown={onKeyDown}
              data-testid="log-decision-form"
              className="border border-slate-200 rounded p-3 space-y-3 bg-white">
            <h3 className="text-sm font-bold text-slate-900">Log decision</h3>

            <div>
                <label className="text-[11px] uppercase tracking-wide font-semibold text-slate-600">
                    Type
                </label>
                <Select value={type} onValueChange={setType}>
                    <SelectTrigger data-testid="decision-type-select" className="mt-1">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        {DECISION_TYPES.map((t) => (
                            <SelectItem key={t.value} value={t.value}>
                                {t.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>

            <div>
                <label className="text-[11px] uppercase tracking-wide font-semibold text-slate-600">
                    Decision date (Europe/London)
                </label>
                <Input type="date" value={date} max={todayMax}
                       onChange={(e) => setDate(e.target.value)}
                       data-testid="decision-date-input" className="mt-1" />
            </div>

            <div>
                <label className="text-[11px] uppercase tracking-wide font-semibold text-slate-600">
                    Rationale (min 10 chars)
                </label>
                <Textarea value={rationale} onChange={(e) => setRationale(e.target.value)}
                          rows={3} data-testid="decision-rationale-textarea"
                          placeholder="What's the basis for this decision?"
                          className="mt-1" />
                <div className="text-[10px] text-slate-500 text-right">
                    {trimmedRationale.length}/10 chars
                </div>
            </div>

            {type === "Conditional_Go" && (
                <div>
                    <label className="text-[11px] uppercase tracking-wide font-semibold text-slate-600">
                        Conditions (required)
                    </label>
                    <Textarea value={conditions}
                              onChange={(e) => setConditions(e.target.value)}
                              rows={2} data-testid="decision-conditions-textarea"
                              placeholder="What must be satisfied for the Go to land?"
                              className="mt-1" />
                </div>
            )}

            <div>
                <label className="text-[11px] uppercase tracking-wide font-semibold text-slate-600">
                    Assumptions challenged (optional)
                </label>
                <Textarea value={assumps} onChange={(e) => setAssumps(e.target.value)}
                          rows={2} data-testid="decision-assumptions-textarea"
                          className="mt-1" />
            </div>

            {type === "Correction" && (
                <div>
                    <label className="text-[11px] uppercase tracking-wide font-semibold text-slate-600">
                        Correcting which decision? (required)
                    </label>
                    <Select value={correctionOf} onValueChange={setCorrectionOf}>
                        <SelectTrigger data-testid="decision-correction-of-select" className="mt-1">
                            <SelectValue placeholder="Pick a decision to correct" />
                        </SelectTrigger>
                        <SelectContent>
                            {existingDecisions.filter((d) => d.decision_type !== "Correction").map((d) => (
                                <SelectItem key={d.id} value={d.id}>
                                    {format(new Date(d.decision_date), "dd MMM yyyy")} — {d.decision_type}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            )}

            {err && (
                <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 p-2 rounded"
                     data-testid="decision-error">{err}</div>
            )}

            <div className="flex gap-2">
                <Button type="submit" disabled={!valid || busy}
                        data-testid="log-decision-button">
                    {busy ? <><Loader2 className="w-3 h-3 animate-spin mr-1" />Logging…</> : "Log decision"}
                </Button>
                <Button type="button" variant="outline" disabled={busy}
                        onClick={reset}>
                    Reset
                </Button>
            </div>
        </form>
    );
}


export default function DecisionsTab({ appraisal, canApprove }) {
    const [items, setItems] = useState(null);
    const [pendingItems, setPendingItems] = useState([]);
    const [err, setErr] = useState(null);
    const nameCacheRef = useRef(new Map());
    const reduceMotion = useReducedMotion();

    const showForm = canApprove && appraisal.is_current === true;

    const load = useCallback(async () => {
        setErr(null);
        try {
            const d = await fetchDecisions(appraisal.id);
            setItems(d.items || []);
        } catch (e) {
            setErr(e.friendlyMessage || "Failed to load decisions");
        }
    }, [appraisal.id]);

    useEffect(() => { load(); }, [load]);

    // Resolve user names lazily.
    const getName = useCallback((uid) => {
        if (uid === "self") return "You";
        if (!uid) return "—";
        const cache = nameCacheRef.current;
        if (cache.has(uid)) return cache.get(uid);
        cache.set(uid, `${uid.slice(0, 8)}…`);
        api.get(`/users/${uid}`)
            .then((r) => {
                const fn = r.data?.full_name || r.data?.email || `${uid.slice(0, 8)}…`;
                cache.set(uid, fn);
                setItems((prev) => (prev ? [...prev] : prev));
            })
            .catch(() => {});
        return cache.get(uid);
    }, []);

    const handlePosted = useCallback((row, tempId, reconciled) => {
        if (!reconciled) {
            // First call: append optimistic.
            setPendingItems((prev) => [{ ...row, _tmp: tempId }, ...prev]);
        } else {
            // Reconciliation.
            setPendingItems((prev) => prev.filter((p) => p._tmp !== tempId));
            setItems((prev) => [row, ...(prev || [])]);
        }
    }, []);

    const handleError = useCallback((tempId) => {
        setPendingItems((prev) => prev.filter((p) => p._tmp !== tempId));
    }, []);

    const scrollToId = (id) => {
        const el = document.getElementById(`decision-card-${id}`);
        if (el) {
            el.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
            el.classList.add("ring-2", "ring-amber-400");
            setTimeout(() => el.classList.remove("ring-2", "ring-amber-400"), 1500);
        }
    };

    const allItems = useMemo(() => [...pendingItems, ...(items || [])], [pendingItems, items]);

    if (err) {
        return (
            <div className="text-xs text-rose-700 border border-rose-200 bg-rose-50 p-3 rounded"
                 data-testid="decisions-tab-error">{err}</div>
        );
    }

    return (
        <div className={`grid ${showForm ? "grid-cols-3" : "grid-cols-1"} gap-4`}
             data-testid="decisions-tab">
            <div className={showForm ? "col-span-2" : ""} data-testid="decision-list">
                {!items ? (
                    <ListSkeleton />
                ) : allItems.length === 0 ? (
                    <div className="border border-dashed border-slate-200 rounded p-8 text-center"
                         data-testid="decisions-empty">
                        <Gavel className="w-12 h-12 mx-auto text-slate-300 mb-2" />
                        <div className="text-sm font-medium text-slate-700">
                            No decisions logged
                        </div>
                        <div className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                            {showForm
                                ? "Log the first Go/No-Go to start tracking sentiment."
                                : "Decisions will appear here once a director logs a Go/No-Go."}
                        </div>
                    </div>
                ) : (
                    <div className="space-y-3">
                        <AnimatePresence>
                            {allItems.map((d) => (
                                <DecisionCard key={d._tmp || d.id}
                                              decision={d}
                                              pending={Boolean(d._tmp)}
                                              getName={getName}
                                              allDecisionsById={items}
                                              scrollToId={scrollToId} />
                            ))}
                        </AnimatePresence>
                    </div>
                )}
            </div>
            {showForm && (
                <div className="col-span-1">
                    <LogDecisionForm appraisal={appraisal}
                                     existingDecisions={items || []}
                                     onPosted={handlePosted}
                                     onError={handleError} />
                </div>
            )}
        </div>
    );
}
