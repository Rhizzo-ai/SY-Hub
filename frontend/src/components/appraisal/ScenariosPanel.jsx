/**
 * ScenariosPanel — top-level tab on AppraisalPage.
 *
 * Conditional render: appraisal.scenario === 'Base' AND user has appraisals.view.
 * Mount: between Finance and Summary tabs.
 *
 * Layout:
 *   - 2×2 grid of slot cards: Base, Upside, Downside, Sensitivity.
 *   - Below grid: ScenarioComparator (if ≥2 scenarios exist).
 *
 * Create CTA visibility (F1): user has appraisals.edit AND current appraisal IS
 * the Base v1 anchor (anchor.scenario_appraisal_id === appraisal.id).
 *
 * On non-anchor Base (v2+): show banner "Scenarios can only be created from
 * the Base v1 appraisal" with link to v1.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { GitBranch, Plus } from "lucide-react";
import { toast } from "sonner";
import { formatDistanceToNow } from "date-fns";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";

import {
    fetchGroupScenarios, createScenario as apiCreateScenario,
} from "@/lib/api";
import { formatMoney, fmtPct } from "@/lib/appraisalMath";
import { STATE_BADGE } from "@/components/appraisal/atoms";
import ScenarioComparator from "@/components/appraisal/ScenarioComparator";

const SLOT_LABELS = ["Base", "Upside", "Downside", "Sensitivity"];

const SLOT_TONE = {
    Base: "border-slate-300 bg-slate-50",
    Upside: "border-emerald-200 bg-emerald-50/30",
    Downside: "border-rose-200 bg-rose-50/30",
    Sensitivity: "border-blue-200 bg-blue-50/30",
};


function PanelSkeleton() {
    return (
        <div className="grid grid-cols-2 gap-4" data-testid="scenarios-panel-skeleton">
            {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-44 rounded border border-slate-200 bg-slate-50 animate-pulse" />
            ))}
        </div>
    );
}


function ScenarioCard({ slot, scenario, currentApp, currentAppraisalId }) {
    if (!scenario) return null;
    const isMe = scenario.current_appraisal_id === currentAppraisalId;
    return (
        <div className={`border rounded p-4 space-y-2 ${SLOT_TONE[slot]}`}
             data-testid={`scenario-card-${slot}`}>
            <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-slate-900">{slot}</span>
                {currentApp?.status && (
                    <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium border rounded ${STATE_BADGE[currentApp.status]}`}>
                        {currentApp.status}
                    </span>
                )}
            </div>
            <p className="text-xs text-slate-600 line-clamp-2" title={scenario.scenario_description}>
                {scenario.scenario_description}
            </p>
            {currentApp && (
                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-200/60">
                    <div>
                        <div className="text-[10px] uppercase text-slate-500">GDV</div>
                        <div className="text-xs font-mono">{formatMoney(currentApp.gdv_total)}</div>
                    </div>
                    <div>
                        <div className="text-[10px] uppercase text-slate-500">Profit</div>
                        <div className="text-xs font-mono">{formatMoney(currentApp.profit_total)}</div>
                    </div>
                    <div>
                        <div className="text-[10px] uppercase text-slate-500">Margin</div>
                        <div className="text-xs font-mono">{fmtPct(currentApp.profit_on_cost_pct)}</div>
                    </div>
                </div>
            )}
            <div className="flex items-center justify-between pt-2 text-[10px] text-slate-500">
                <Link to={`/appraisals/${scenario.current_appraisal_id}`}
                      className="text-slate-700 hover:text-slate-900 underline"
                      data-testid={`scenario-card-${slot}-open`}>
                    Open v{currentApp?.version_number ?? "?"}
                </Link>
                <span>
                    {formatDistanceToNow(new Date(scenario.created_at), { addSuffix: true })}
                </span>
            </div>
            {isMe && (
                <div className="text-[10px] font-semibold text-emerald-700">
                    You're viewing this scenario
                </div>
            )}
        </div>
    );
}


function EmptySlot({ slot, onCreate, canCreate }) {
    if (slot === "Base") {
        return (
            <div className={`border-2 border-dashed rounded p-4 ${SLOT_TONE.Base} opacity-60`}
                 data-testid={`scenario-card-${slot}-empty`}>
                <span className="text-sm font-bold text-slate-900">{slot}</span>
                <p className="text-xs text-slate-500 mt-2">Base anchor missing — contact support.</p>
            </div>
        );
    }
    return (
        <div className={`border-2 border-dashed border-slate-300 rounded p-4 flex flex-col items-center justify-center text-center min-h-[176px] ${canCreate ? "hover:bg-slate-50 transition-colors" : "opacity-60"}`}
             data-testid={`scenario-card-${slot}-empty`}>
            <span className="text-xs uppercase tracking-wide text-slate-500 mb-2">{slot}</span>
            {canCreate ? (
                <Button variant="outline" size="sm" onClick={() => onCreate(slot)}
                        data-testid={`create-scenario-button-${slot}`}>
                    <Plus className="w-3 h-3 mr-1" /> Create {slot} scenario
                </Button>
            ) : (
                <span className="text-xs text-slate-400">No {slot.toLowerCase()} yet</span>
            )}
        </div>
    );
}


function CreateScenarioModal({ open, onClose, slot, baseId, onCreated }) {
    const [desc, setDesc] = useState("");
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState(null);
    const reduceMotion = useReducedMotion();

    useEffect(() => {
        if (open) { setDesc(""); setErr(null); setBusy(false); }
    }, [open]);

    const trimmed = desc.trim();
    const valid = trimmed.length >= 10;

    const onSubmit = async (e) => {
        e?.preventDefault?.();
        if (!valid || busy) return;
        setBusy(true);
        setErr(null);
        try {
            await apiCreateScenario(baseId, {
                scenario_label: slot,
                scenario_description: trimmed,
            });
            toast.success(`${slot} scenario created.`);
            onCreated();
            onClose();
        } catch (e) {
            setErr(e.friendlyMessage || "Failed to create scenario");
        } finally { setBusy(false); }
    };

    // Cmd/Ctrl+Enter submit (S9).
    const onKey = (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") onSubmit(e);
    };

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="create-scenario-modal"
                           className={reduceMotion ? "" : ""}>
                <form onSubmit={onSubmit} onKeyDown={onKey}>
                    <DialogHeader>
                        <DialogTitle>Create {slot} scenario</DialogTitle>
                        <DialogDescription>
                            Spawned from the Base v1 anchor. Forks all units, costs, and finance lines.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2 py-3">
                        <label className="text-xs uppercase tracking-wide font-semibold text-slate-600">
                            Description (min 10 chars)
                        </label>
                        <Textarea value={desc} onChange={(e) => setDesc(e.target.value)}
                                  placeholder="What does this scenario explore? E.g. '+5% GDV, -2% build cost vs base.'"
                                  data-testid="scenario-description-input" rows={4} />
                        <div className="text-[10px] text-slate-500 text-right">
                            {trimmed.length}/10 chars
                        </div>
                        {err && (
                            <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 p-2 rounded"
                                 data-testid="create-scenario-error">{err}</div>
                        )}
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
                            Cancel
                        </Button>
                        <Button type="submit" disabled={!valid || busy}
                                data-testid="create-scenario-submit">
                            {busy ? "Creating…" : "Create scenario"}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}


export default function ScenariosPanel({ appraisal, canEdit }) {
    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);
    const [modalSlot, setModalSlot] = useState(null);
    const [comparatorTick, setComparatorTick] = useState(0);
    const reduceMotion = useReducedMotion();

    const groupId = appraisal.appraisal_group_id;

    const load = useCallback(async () => {
        setErr(null);
        try {
            const d = await fetchGroupScenarios(groupId);
            setData(d);
        } catch (e) {
            setErr(e.friendlyMessage || "Failed to load scenarios");
        }
    }, [groupId]);

    useEffect(() => { load(); }, [load]);

    const byLabel = useMemo(() => {
        const m = {};
        (data?.scenarios || []).forEach((s) => { m[s.scenario_label] = s; });
        return m;
    }, [data]);

    // Anchor detection (F1): is this appraisal id the Base anchor's scenario_appraisal_id?
    const baseRow = byLabel.Base;
    const isAnchor = baseRow && baseRow.scenario_appraisal_id === appraisal.id;
    const showCreateCtas = canEdit && isAnchor;

    const slotApprArr = data?.scenarios || [];

    if (err) {
        return (
            <div className="text-xs text-rose-700 border border-rose-200 bg-rose-50 p-2 rounded"
                 data-testid="scenarios-panel-error">{err}</div>
        );
    }
    if (!data) return <PanelSkeleton />;

    return (
        <div className="space-y-6" data-testid="scenarios-panel">
            {!isAnchor && baseRow && (
                <div className="border border-amber-200 bg-amber-50 text-amber-900 p-3 rounded text-sm flex items-start gap-2"
                     data-testid="scenarios-non-anchor-banner">
                    <GitBranch className="w-4 h-4 mt-0.5 flex-shrink-0" />
                    <div>
                        Scenarios can only be created from the Base v1 appraisal.
                        {" "}
                        <Link to={`/appraisals/${baseRow.scenario_appraisal_id}`}
                              className="underline font-medium"
                              data-testid="scenarios-go-to-anchor">
                            Open Base v1 →
                        </Link>
                    </div>
                </div>
            )}

            <div className="grid grid-cols-2 gap-4">
                {SLOT_LABELS.map((slot, idx) => {
                    const scenario = byLabel[slot];
                    const currentApp = scenario && (
                        slotApprArr.find((s) => s.scenario_label === slot) || null
                    );
                    return (
                        <motion.div key={slot}
                                    initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ duration: reduceMotion ? 0 : 0.2, delay: reduceMotion ? 0 : idx * 0.04 }}>
                            {scenario ? (
                                <ScenarioCard slot={slot} scenario={scenario}
                                              currentApp={currentApp}
                                              currentAppraisalId={appraisal.id} />
                            ) : (
                                <EmptySlot slot={slot}
                                           canCreate={showCreateCtas}
                                           onCreate={(s) => setModalSlot(s)} />
                            )}
                        </motion.div>
                    );
                })}
            </div>

            <AnimatePresence>
                {modalSlot && (
                    <CreateScenarioModal open={Boolean(modalSlot)}
                                         onClose={() => setModalSlot(null)}
                                         slot={modalSlot}
                                         baseId={appraisal.id}
                                         onCreated={() => {
                                             load();
                                             setComparatorTick((t) => t + 1);
                                         }} />
                )}
            </AnimatePresence>

            <ScenarioComparator key={`comparator-${comparatorTick}`}
                                groupId={groupId} />
        </div>
    );
}
