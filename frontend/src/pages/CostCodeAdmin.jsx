import React, { useEffect, useMemo, useState, useCallback } from "react";
import {
    ChevronDown, ChevronRight, Plus, Pencil, Trash2,
    Archive, RotateCcw, Loader2, AlertCircle, ShieldOff,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle,
    DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem,
    SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

// Brand palette — Build Pack §6 lock.
const BRAND = {
    primary: "#0F6A7A",
    primarySoft: "#0F6A7A14",   // 8% tint
    accent: "#FC7827",
    accentSoft: "#FC782714",    // 8% tint
    neutral: "#CECECE",
    neutralSoft: "#F4F4F4",
};

// ---------- Permission helpers ----------------------------------------------
// All gates read off the LIVE permission set (me.permissions), never
// hardcoded role checks. Director gets create + edit but NOT delete —
// the seed_rbac.py exclusion set drops cost_codes.delete from director.
// Source: backend/app/seed_rbac.py ROLE_PERMISSIONS.

function useGates() {
    const { me, hasPerm } = useAuth();
    return useMemo(() => {
        const ga = (perm) => hasPerm(perm) || !!me?.is_super_admin;
        return {
            canView:   ga("cost_codes.view"),
            canCreate: ga("cost_codes.create"),
            canEdit:   ga("cost_codes.edit"),
            canDelete: ga("cost_codes.delete"),
            roleHint:  me?.role || "?",
        };
    }, [me, hasPerm]);
}


// ---------- 409 detail extractor --------------------------------------------
// Backend returns 409 with body shape:
//   { detail: { message: str, blockers: [str, str, ...] } }
// (See backend/app/routers/cost_codes.py lines 510-516 + 784-790.)
// The axios interceptor leaves error.response.data intact, so we read
// detail.blockers directly and render each line — no raw toast.

function extract409(err) {
    const detail = err?.response?.data?.detail;
    if (
        err?.response?.status === 409 &&
        detail &&
        typeof detail === "object" &&
        Array.isArray(detail.blockers)
    ) {
        return {
            message: detail.message || "Cannot delete: in use.",
            blockers: detail.blockers,
        };
    }
    return null;
}


// ---------- Reusable: inline block-reasons panel ----------------------------
function BlockReasonsPanel({ data, onClose, onRetire, canRetire }) {
    if (!data) return null;
    return (
        <div
            data-testid="block-reasons-panel"
            className="rounded-lg border p-4 mt-3 space-y-2"
            style={{ borderColor: BRAND.accent, background: BRAND.accentSoft }}
        >
            <div className="flex items-start gap-2">
                <AlertCircle size={18} style={{ color: BRAND.accent }} className="mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                    <div className="font-medium text-sm" style={{ color: BRAND.accent }}>
                        {data.message}
                    </div>
                    <ul className="mt-2 space-y-1 text-sm text-slate-700" data-testid="block-reasons-list">
                        {data.blockers.map((b, i) => (
                            <li key={i} className="flex items-start gap-2">
                                <span className="text-slate-400 mt-0.5">·</span>
                                <span>{b}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
                {canRetire && onRetire && (
                    <Button
                        size="sm"
                        variant="outline"
                        onClick={onRetire}
                        data-testid="block-reasons-retire-instead-btn"
                    >
                        <Archive size={14} className="mr-1" />
                        Retire instead
                    </Button>
                )}
                <Button size="sm" variant="ghost" onClick={onClose} data-testid="block-reasons-dismiss-btn">
                    Dismiss
                </Button>
            </div>
        </div>
    );
}


// ---------- Sections / codes loader -----------------------------------------
function useCostCodeTree() {
    const [sections, setSections] = useState([]);
    const [codes, setCodes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const refresh = useCallback(async () => {
        setLoading(true);
        try {
            const [secR, codeR] = await Promise.all([
                api.get("/cost-code-sections?tree=true"),
                api.get("/cost-codes?status=All"),
            ]);
            setSections(secR.data);
            setCodes(codeR.data);
            setError(null);
        } catch (e) {
            setError(e?.friendlyMessage || "Failed to load");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { refresh(); }, [refresh]);

    return { sections, codes, loading, error, refresh };
}


// ---------- Section modals --------------------------------------------------
function SectionFormModal({ open, onClose, initial, parentOptions, onSaved }) {
    const isEdit = !!initial?.id;
    const [code, setCode] = useState(initial?.code || "");
    const [name, setName] = useState(initial?.name || "");
    const [displayOrder, setDisplayOrder] = useState(initial?.display_order ?? 1);
    const [allowsSubgroups, setAllowsSubgroups] = useState(initial?.allows_subgroups || false);
    const [parentSectionId, setParentSectionId] = useState(initial?.parent_section_id || "");
    const [defaultPL, setDefaultPL] = useState(initial?.default_p_and_l_category || "COS");
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        if (!open) return;
        setCode(initial?.code || "");
        setName(initial?.name || "");
        setDisplayOrder(initial?.display_order ?? 1);
        setAllowsSubgroups(initial?.allows_subgroups || false);
        setParentSectionId(initial?.parent_section_id || "");
        setDefaultPL(initial?.default_p_and_l_category || "COS");
    }, [open, initial]);

    async function submit() {
        setSubmitting(true);
        try {
            const payload = {
                code, name,
                display_order: Number(displayOrder),
                default_p_and_l_category: defaultPL,
                allows_subgroups: allowsSubgroups,
                parent_section_id: parentSectionId || null,
            };
            if (isEdit) {
                await api.patch(`/cost-code-sections/${initial.id}`, payload);
                toast.success(`Group ${code} updated.`);
            } else {
                await api.post("/cost-code-sections", payload);
                toast.success(`Group ${code} created.`);
            }
            onSaved();
            onClose();
        } catch (e) {
            toast.error(e?.friendlyMessage || "Save failed");
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="section-form-modal" className="max-w-md">
                <DialogHeader>
                    <DialogTitle>{isEdit ? `Edit group ${initial.code}` : "New group"}</DialogTitle>
                    <DialogDescription>
                        Parent groups use numeric codes (1–9); subgroups under Construction use 4.00–4.09.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <div>
                        <Label htmlFor="sf-code">Code</Label>
                        <Input id="sf-code" data-testid="sf-code" value={code}
                               onChange={(e) => setCode(e.target.value)} />
                    </div>
                    <div>
                        <Label htmlFor="sf-name">Name</Label>
                        <Input id="sf-name" data-testid="sf-name" value={name}
                               onChange={(e) => setName(e.target.value)} />
                    </div>
                    <div>
                        <Label htmlFor="sf-order">Display order</Label>
                        <Input id="sf-order" data-testid="sf-order" type="number" value={displayOrder}
                               onChange={(e) => setDisplayOrder(e.target.value)} />
                    </div>
                    <div>
                        <Label htmlFor="sf-parent">Parent group (subgroups only)</Label>
                        <Select
                            value={parentSectionId || "__none__"}
                            onValueChange={(v) => setParentSectionId(v === "__none__" ? "" : v)}
                        >
                            <SelectTrigger id="sf-parent" data-testid="sf-parent">
                                <SelectValue placeholder="(none — top-level group)" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__none__">(none — top-level group)</SelectItem>
                                {parentOptions.map((p) => (
                                    <SelectItem key={p.id} value={p.id}>
                                        {p.code} {p.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label htmlFor="sf-pl">P&amp;L category</Label>
                        <Select value={defaultPL} onValueChange={setDefaultPL}>
                            <SelectTrigger id="sf-pl" data-testid="sf-pl"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {["COS", "Overhead", "Finance", "Tax"].map((c) =>
                                    <SelectItem key={c} value={c}>{c}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                        <Checkbox
                            data-testid="sf-allows-subgroups"
                            checked={allowsSubgroups}
                            onCheckedChange={setAllowsSubgroups}
                            disabled={!!parentSectionId}
                        />
                        Allows subgroups (Construction-style)
                    </label>
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button
                        onClick={submit}
                        disabled={submitting || !code || !name}
                        data-testid="sf-submit"
                        style={{ background: BRAND.primary, color: "white" }}
                    >
                        {submitting ? <Loader2 size={14} className="animate-spin mr-1" /> : null}
                        Save
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


// ---------- Code modals -----------------------------------------------------
function CodeFormModal({ open, onClose, initial, sectionOptions, onSaved }) {
    const isEdit = !!initial?.id;
    const [code, setCode] = useState(initial?.code || "");
    const [name, setName] = useState(initial?.name || "");
    const [sectionId, setSectionId] = useState(initial?.section_id || "");
    const [btCategory, setBtCategory] = useState(initial?.buildertrend_category || "");
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        if (!open) return;
        setCode(initial?.code || "");
        setName(initial?.name || "");
        setSectionId(initial?.section_id || "");
        setBtCategory(initial?.buildertrend_category || "");
    }, [open, initial]);

    async function submit() {
        setSubmitting(true);
        try {
            if (isEdit) {
                await api.patch(`/cost-codes/${initial.id}`, {
                    name, buildertrend_category: btCategory,
                });
                toast.success(`${initial.code} updated.`);
            } else {
                await api.post(`/cost-codes`, {
                    code, name, section_id: sectionId,
                    buildertrend_category: btCategory || null,
                });
                toast.success(`${code} created.`);
            }
            onSaved();
            onClose();
        } catch (e) {
            toast.error(e?.friendlyMessage || "Save failed");
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="code-form-modal" className="max-w-md">
                <DialogHeader>
                    <DialogTitle>{isEdit ? `Edit ${initial.code}` : "New cost code"}</DialogTitle>
                    <DialogDescription>
                        Cost codes follow the strict 3-letter prefix + 2-digit
                        sequence format (e.g. <code>FAC-06</code>).
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <div>
                        <Label htmlFor="cf-code">Code</Label>
                        <Input
                            id="cf-code" data-testid="cf-code" value={code}
                            onChange={(e) => setCode(e.target.value.toUpperCase())}
                            disabled={isEdit}
                            placeholder="ABC-12"
                        />
                    </div>
                    <div>
                        <Label htmlFor="cf-name">Name</Label>
                        <Input id="cf-name" data-testid="cf-name" value={name}
                               onChange={(e) => setName(e.target.value)} />
                    </div>
                    <div>
                        <Label htmlFor="cf-section">Group / subgroup</Label>
                        <Select value={sectionId} onValueChange={setSectionId} disabled={isEdit}>
                            <SelectTrigger id="cf-section" data-testid="cf-section">
                                <SelectValue placeholder="Select a group" />
                            </SelectTrigger>
                            <SelectContent>
                                {sectionOptions.map((s) => (
                                    <SelectItem key={s.id} value={s.id}>
                                        {s.code} {s.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label htmlFor="cf-bt">Buildertrend category</Label>
                        <Input id="cf-bt" data-testid="cf-bt" value={btCategory}
                               onChange={(e) => setBtCategory(e.target.value)} />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button
                        onClick={submit}
                        disabled={submitting || !code || !name || (!isEdit && !sectionId)}
                        data-testid="cf-submit"
                        style={{ background: BRAND.primary, color: "white" }}
                    >
                        {submitting ? <Loader2 size={14} className="animate-spin mr-1" /> : null}
                        Save
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


// ---------- Retire modal ----------------------------------------------------
function RetireModal({ open, onClose, target, onSaved }) {
    const [reason, setReason] = useState("");
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => { if (open) setReason(""); }, [open]);

    async function submit() {
        if (!target) return;
        setSubmitting(true);
        try {
            await api.post(`/cost-codes/${target.id}/retire`, { retired_reason: reason });
            toast.success(`${target.code} retired.`);
            onSaved();
            onClose();
        } catch (e) {
            toast.error(e?.friendlyMessage || "Retire failed");
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="retire-modal" className="max-w-md">
                <DialogHeader>
                    <DialogTitle>Retire {target?.code}</DialogTitle>
                    <DialogDescription>
                        Retiring keeps the code in the DB (with historical references intact) but
                        prevents new selections. Provide a short reason for audit.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                    <div>
                        <Label htmlFor="rm-reason">Reason (min 3 chars)</Label>
                        <Input id="rm-reason" data-testid="rm-reason" value={reason}
                               onChange={(e) => setReason(e.target.value)} autoFocus />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button
                        onClick={submit}
                        disabled={submitting || reason.trim().length < 3}
                        data-testid="rm-submit"
                        style={{ background: BRAND.accent, color: "white" }}
                    >
                        {submitting ? <Loader2 size={14} className="animate-spin mr-1" /> : null}
                        Retire
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


// ---------- Delete-confirm modal --------------------------------------------
function DeleteModal({ open, onClose, target, kind, onConfirmed, onBlocked }) {
    const [submitting, setSubmitting] = useState(false);
    const [block, setBlock] = useState(null);

    useEffect(() => { if (open) setBlock(null); }, [open]);

    async function confirm() {
        if (!target) return;
        setSubmitting(true);
        try {
            const url = kind === "section"
                ? `/cost-code-sections/${target.id}`
                : `/cost-codes/${target.id}`;
            await api.delete(url);
            toast.success(`${target.code || target.name} deleted.`);
            onConfirmed();
            onClose();
        } catch (e) {
            const detail = extract409(e);
            if (detail) {
                setBlock(detail);
                onBlocked?.(detail);
            } else {
                toast.error(e?.friendlyMessage || "Delete failed");
            }
        } finally {
            setSubmitting(false);
        }
    }

    function offerRetire() {
        onClose();
        onBlocked?.({ ...block, askRetire: true, target });
    }

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="delete-modal" className="max-w-md">
                <DialogHeader>
                    <DialogTitle>
                        Delete {target?.code || target?.name}?
                    </DialogTitle>
                    <DialogDescription>
                        Hard delete is permanent and only succeeds if nothing references this row.
                        If anything does, you&apos;ll see the blockers below — use{" "}
                        <em>Retire instead</em> in that case.
                    </DialogDescription>
                </DialogHeader>

                <BlockReasonsPanel
                    data={block}
                    onClose={() => setBlock(null)}
                    onRetire={kind === "code" ? offerRetire : null}
                    canRetire={kind === "code"}
                />

                <DialogFooter>
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button
                        onClick={confirm}
                        disabled={submitting}
                        data-testid="delete-confirm-btn"
                        variant="destructive"
                    >
                        {submitting ? <Loader2 size={14} className="animate-spin mr-1" /> : null}
                        Delete
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


// ---------- Tree node renderers ---------------------------------------------
function CodeRow({ code, gates, onEdit, onRetire, onReactivate, onDelete }) {
    const retired = code.status === "Retired";
    return (
        <div
            data-testid={`code-row-${code.code}`}
            className="grid grid-cols-[140px_1fr_auto] gap-3 items-center pl-12 pr-2 py-1.5 hover:bg-slate-50 group rounded"
        >
            <span className="font-mono text-sm" style={{ color: retired ? "#94a3b8" : BRAND.primary }}>
                {code.code}
            </span>
            <span className={`text-sm ${retired ? "text-slate-400 line-through" : "text-slate-700"}`}>
                {code.name}
                {retired && (
                    <Badge variant="outline" className="ml-2" style={{ borderColor: BRAND.neutral, color: "#94a3b8" }}>
                        Retired
                    </Badge>
                )}
            </span>
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                {gates.canEdit && !retired && (
                    <Button size="sm" variant="ghost" onClick={() => onEdit(code)}
                            data-testid={`code-edit-${code.code}`}>
                        <Pencil size={14} />
                    </Button>
                )}
                {gates.canEdit && !retired && (
                    <Button size="sm" variant="ghost" onClick={() => onRetire(code)}
                            data-testid={`code-retire-${code.code}`}>
                        <Archive size={14} />
                    </Button>
                )}
                {gates.canEdit && retired && (
                    <Button size="sm" variant="ghost" onClick={() => onReactivate(code)}
                            data-testid={`code-reactivate-${code.code}`}>
                        <RotateCcw size={14} style={{ color: BRAND.accent }} />
                    </Button>
                )}
                {gates.canDelete && (
                    <Button size="sm" variant="ghost" onClick={() => onDelete(code)}
                            data-testid={`code-delete-${code.code}`}>
                        <Trash2 size={14} className="text-red-600" />
                    </Button>
                )}
                {!gates.canDelete && (
                    <span
                        data-testid={`code-delete-disabled-${code.code}`}
                        title="Delete requires super_admin (cost_codes.delete)"
                        className="text-slate-300 px-2"
                    >
                        <ShieldOff size={14} />
                    </span>
                )}
            </div>
        </div>
    );
}

function SubgroupNode({
    section, isExpanded, onToggle, childCodes,
    gates, onEditSection, onDeleteSection, onAddCodeIn,
    onEditCode, onRetireCode, onReactivateCode, onDeleteCode,
}) {
    const codeCount = childCodes?.length ?? 0;
    return (
        <div data-testid={`section-node-${section.code}`}>
            <div
                className="flex items-center gap-2 px-2 py-2 hover:bg-slate-50 group rounded cursor-pointer"
                style={{
                    paddingLeft: "32px",
                    borderLeft: `3px solid ${BRAND.neutral}`,
                    background: BRAND.neutralSoft,
                }}
                onClick={onToggle}
            >
                {isExpanded
                    ? <ChevronDown size={16} style={{ color: BRAND.primary }} />
                    : <ChevronRight size={16} style={{ color: BRAND.primary }} />}
                <span className="font-semibold text-sm" style={{ color: BRAND.primary }}>
                    {section.code} {section.name}
                </span>
                <Badge variant="outline" className="ml-1 text-xs"
                       style={{ borderColor: BRAND.neutral, color: "#475569" }}>
                    {codeCount} code{codeCount === 1 ? "" : "s"}
                </Badge>
                <div className="flex-1" />
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100"
                     onClick={(e) => e.stopPropagation()}>
                    {gates.canCreate && (
                        <Button size="sm" variant="ghost"
                                onClick={() => onAddCodeIn(section)}
                                data-testid={`section-add-code-${section.code}`}>
                            <Plus size={14} />
                            <span className="ml-1 text-xs">Code</span>
                        </Button>
                    )}
                    {gates.canEdit && (
                        <Button size="sm" variant="ghost"
                                onClick={() => onEditSection(section)}
                                data-testid={`section-edit-${section.code}`}>
                            <Pencil size={14} />
                        </Button>
                    )}
                    {gates.canDelete && (
                        <Button size="sm" variant="ghost"
                                onClick={() => onDeleteSection(section)}
                                data-testid={`section-delete-${section.code}`}>
                            <Trash2 size={14} className="text-red-600" />
                        </Button>
                    )}
                </div>
            </div>
            {isExpanded && (
                <div>
                    {childCodes?.map((c) => (
                        <CodeRow
                            key={c.id} code={c} gates={gates}
                            onEdit={onEditCode} onRetire={onRetireCode}
                            onReactivate={onReactivateCode} onDelete={onDeleteCode}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}


function ParentSectionNode({
    section, isExpanded, onToggle, childCodes, childSubgroups,
    gates, onEditSection, onDeleteSection, onAddCodeIn,
    onEditCode, onRetireCode, onReactivateCode, onDeleteCode,
    expanded, onToggleSub,
}) {
    const isConstruction = section.code === "4";
    const codeCount = childCodes?.length ?? 0;
    const subCount = childSubgroups?.length ?? 0;

    return (
        <div data-testid={`section-node-${section.code}`}>
            <div
                className="flex items-center gap-2 px-2 py-2 hover:bg-slate-50 group rounded cursor-pointer"
                style={{ paddingLeft: "8px" }}
                onClick={onToggle}
            >
                {isExpanded
                    ? <ChevronDown size={16} style={{ color: BRAND.primary }} />
                    : <ChevronRight size={16} style={{ color: BRAND.primary }} />}
                <span className="font-semibold text-base" style={{ color: BRAND.primary }}>
                    {section.code} {section.name}
                </span>
                <Badge variant="outline" className="ml-1 text-xs"
                       style={{ borderColor: BRAND.neutral, color: "#475569" }}>
                    {section.allows_subgroups
                        ? `${subCount} subgroup${subCount === 1 ? "" : "s"}`
                        : `${codeCount} code${codeCount === 1 ? "" : "s"}`}
                </Badge>
                <div className="flex-1" />
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100"
                     onClick={(e) => e.stopPropagation()}>
                    {gates.canCreate && !section.allows_subgroups && (
                        <Button size="sm" variant="ghost"
                                onClick={() => onAddCodeIn(section)}
                                data-testid={`section-add-code-${section.code}`}>
                            <Plus size={14} />
                            <span className="ml-1 text-xs">Code</span>
                        </Button>
                    )}
                    {gates.canEdit && (
                        <Button size="sm" variant="ghost"
                                onClick={() => onEditSection(section)}
                                data-testid={`section-edit-${section.code}`}>
                            <Pencil size={14} />
                        </Button>
                    )}
                    {gates.canDelete && (
                        <Button size="sm" variant="ghost"
                                onClick={() => onDeleteSection(section)}
                                data-testid={`section-delete-${section.code}`}>
                            <Trash2 size={14} className="text-red-600" />
                        </Button>
                    )}
                </div>
            </div>
            {isExpanded && (
                <div>
                    {childSubgroups?.map((sub) => (
                        <SubgroupNode
                            key={sub.id}
                            section={sub}
                            isExpanded={expanded[sub.id] ?? true}
                            onToggle={() => onToggleSub(sub.id)}
                            childCodes={sub._codes || []}
                            gates={gates}
                            onEditSection={onEditSection}
                            onDeleteSection={onDeleteSection}
                            onAddCodeIn={onAddCodeIn}
                            onEditCode={onEditCode}
                            onRetireCode={onRetireCode}
                            onReactivateCode={onReactivateCode}
                            onDeleteCode={onDeleteCode}
                        />
                    ))}
                    {childCodes?.map((c) => (
                        <CodeRow
                            key={c.id} code={c} gates={gates}
                            onEdit={onEditCode} onRetire={onRetireCode}
                            onReactivate={onReactivateCode} onDelete={onDeleteCode}
                        />
                    ))}
                    {isConstruction && childCodes && childCodes.length > 0 && (
                        <div className="pl-8 py-1 text-xs text-amber-700">
                            Note: codes attached directly to Construction &quot;4&quot; should live under
                            a subgroup (4.00–4.09).
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}


// ============================================================================
// B88 Pack 2 §7.3 / D8 — CSV export helper
// ============================================================================
function csvCell(v) {
    if (v == null) return "";
    const s = String(v);
    if (/[",\n\r]/.test(s)) {
        return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
}

export function exportCostCodesCsv(tree, codes) {
    // Build a code-id → (group_code, group_name, subgroup_code, subgroup_name)
    // map by walking the tree.
    const sectionLookup = new Map();
    for (const sec of tree) {
        for (const sub of sec.subgroups || []) {
            sectionLookup.set(sub.id, {
                group_code: sec.code, group_name: sec.name,
                subgroup_code: sub.code, subgroup_name: sub.name,
            });
        }
        sectionLookup.set(sec.id, {
            group_code: sec.code, group_name: sec.name,
            subgroup_code: "", subgroup_name: "",
        });
    }

    const header = [
        "group_code", "group_name", "subgroup_code", "subgroup_name",
        "code", "name", "status", "nrm_reference", "xero_nominal_code",
    ];
    const rows = [header.join(",")];
    // Sort codes by group/subgroup/code for a deterministic file.
    const sortedCodes = [...codes].sort((a, b) => {
        const sa = sectionLookup.get(a.section_id) || {};
        const sb = sectionLookup.get(b.section_id) || {};
        return (
            String(sa.group_code || "").localeCompare(String(sb.group_code || ""))
            || String(sa.subgroup_code || "").localeCompare(String(sb.subgroup_code || ""))
            || String(a.code).localeCompare(String(b.code))
        );
    });
    for (const c of sortedCodes) {
        const s = sectionLookup.get(c.section_id) || {};
        rows.push([
            s.group_code, s.group_name, s.subgroup_code, s.subgroup_name,
            c.code, c.name, c.status,
            c.nrm_reference, c.xero_nominal_code,
        ].map(csvCell).join(","));
    }
    const csv = "\uFEFF" + rows.join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const yyyymmdd = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    a.href = url;
    a.download = `SY_cost_codes_${yyyymmdd}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}


// ============================================================================
// MAIN PAGE
// ============================================================================
export default function CostCodeAdmin() {
    const gates = useGates();
    const { sections, codes, loading, error, refresh } = useCostCodeTree();
    const [expanded, setExpanded] = useState({});
    const [sectionModal, setSectionModal] = useState({ open: false, initial: null });
    const [codeModal, setCodeModal] = useState({ open: false, initial: null, defaultSectionId: null });
    const [deleteModal, setDeleteModal] = useState({ open: false, target: null, kind: null });
    const [retireModal, setRetireModal] = useState({ open: false, target: null });

    const sectionById = useMemo(() => {
        const m = new Map();
        for (const s of sections) {
            m.set(s.id, s);
            for (const sub of s.subgroups || []) m.set(sub.id, sub);
        }
        return m;
    }, [sections]);

    // Group codes by section_id, attach to the tree.
    const tree = useMemo(() => {
        const codesBySection = new Map();
        for (const c of codes) {
            if (!codesBySection.has(c.section_id)) codesBySection.set(c.section_id, []);
            codesBySection.get(c.section_id).push(c);
        }
        return sections.map((s) => ({
            ...s,
            _codes: codesBySection.get(s.id) || [],
            subgroups: (s.subgroups || []).map((sub) => ({
                ...sub,
                _codes: codesBySection.get(sub.id) || [],
            })),
        }));
    }, [sections, codes]);

    const allSectionsFlat = useMemo(() => {
        const out = [];
        for (const s of sections) {
            out.push(s);
            for (const sub of s.subgroups || []) out.push(sub);
        }
        return out;
    }, [sections]);

    const parentOptionsForSectionForm = useMemo(
        () => sections.filter((s) => s.allows_subgroups),
        [sections],
    );

    function toggle(sectionId) {
        setExpanded((e) => ({ ...e, [sectionId]: !(e[sectionId] ?? false) }));
    }

    useEffect(() => {
        if (!loading && sections.length && Object.keys(expanded).length === 0) {
            const init = {};
            for (const s of sections) init[s.id] = true;
            setExpanded(init);
        }
    }, [loading, sections, expanded]);

    async function handleReactivate(c) {
        try {
            await api.post(`/cost-codes/${c.id}/reactivate`);
            toast.success(`${c.code} reactivated.`);
            refresh();
        } catch (e) {
            toast.error(e?.friendlyMessage || "Reactivate failed");
        }
    }

    function offerRetireAfterDeleteBlock(payload) {
        if (payload?.askRetire && payload?.target) {
            setRetireModal({ open: true, target: payload.target });
        }
    }

    if (!gates.canView) {
        return (
            <div className="p-8" data-testid="cost-code-admin-no-perm">
                <div className="text-slate-700">
                    You do not have permission to view cost codes.
                </div>
            </div>
        );
    }

    return (
        <div className="p-6 max-w-5xl mx-auto" data-testid="cost-code-admin">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold" style={{ color: BRAND.primary }}>
                        Cost-Code Admin
                    </h1>
                    <p className="text-sm text-slate-600 mt-1 max-w-2xl">
                        Master classification — 9 parent groups, 10 Construction subgroups, 130 codes.
                        Used by appraisals, budgets, actuals and Xero mapping.
                    </p>
                    <div className="mt-2 flex items-center gap-2 text-xs text-slate-500" data-testid="perm-summary">
                        <Badge variant="outline" style={{ borderColor: BRAND.neutral }}>
                            role: {gates.roleHint}
                        </Badge>
                        <Badge variant="outline" style={{
                            borderColor: gates.canCreate ? BRAND.primary : BRAND.neutral,
                            color: gates.canCreate ? BRAND.primary : "#94a3b8",
                        }}>create: {gates.canCreate ? "yes" : "no"}</Badge>
                        <Badge variant="outline" style={{
                            borderColor: gates.canEdit ? BRAND.primary : BRAND.neutral,
                            color: gates.canEdit ? BRAND.primary : "#94a3b8",
                        }}>edit: {gates.canEdit ? "yes" : "no"}</Badge>
                        <Badge variant="outline" style={{
                            borderColor: gates.canDelete ? BRAND.accent : BRAND.neutral,
                            color: gates.canDelete ? BRAND.accent : "#94a3b8",
                        }}>delete: {gates.canDelete ? "yes" : "no (super_admin only)"}</Badge>
                    </div>
                </div>
                {gates.canCreate && (
                    <Button
                        onClick={() => setSectionModal({ open: true, initial: null })}
                        data-testid="add-group-btn"
                        style={{ background: BRAND.primary, color: "white" }}
                    >
                        <Plus size={16} className="mr-1" />
                        New group
                    </Button>
                )}
                {/* B88 Pack 2 §7.3 / D8 — client-side CSV export.
                    No new backend endpoint; builds from the already-
                    fetched tree. UTF-8 BOM so Excel opens it cleanly. */}
                <Button
                    type="button"
                    variant="outline"
                    onClick={() => exportCostCodesCsv(tree, codes)}
                    data-testid="export-csv-btn"
                    className="ml-2"
                    style={{ borderColor: BRAND.primary, color: BRAND.primary }}
                >
                    Export CSV
                </Button>
            </div>

            {/* Tree */}
            <div
                className="rounded-lg border bg-white shadow-sm"
                style={{ borderColor: BRAND.neutral }}
                data-testid="cost-code-tree"
            >
                {loading && (
                    <div className="flex items-center justify-center p-12 text-slate-500">
                        <Loader2 size={20} className="animate-spin mr-2" />
                        Loading cost-code tree…
                    </div>
                )}
                {error && (
                    <div className="p-4 text-sm text-red-600">{error}</div>
                )}
                {!loading && !error && tree.map((sec) => (
                    <ParentSectionNode
                        key={sec.id}
                        section={sec}
                        isExpanded={expanded[sec.id] ?? false}
                        onToggle={() => toggle(sec.id)}
                        childCodes={sec._codes}
                        childSubgroups={sec.subgroups}
                        gates={gates}
                        onEditSection={(s) => setSectionModal({ open: true, initial: s })}
                        onDeleteSection={(s) => setDeleteModal({ open: true, target: s, kind: "section" })}
                        onAddCodeIn={(s) => setCodeModal({ open: true, initial: null, defaultSectionId: s.id })}
                        onEditCode={(c) => setCodeModal({ open: true, initial: c })}
                        onRetireCode={(c) => setRetireModal({ open: true, target: c })}
                        onReactivateCode={handleReactivate}
                        onDeleteCode={(c) => setDeleteModal({ open: true, target: c, kind: "code" })}
                        expanded={expanded}
                        onToggleSub={toggle}
                    />
                ))}
            </div>

            {/* Modals */}
            <SectionFormModal
                open={sectionModal.open}
                onClose={() => setSectionModal({ open: false, initial: null })}
                initial={sectionModal.initial}
                parentOptions={parentOptionsForSectionForm}
                onSaved={refresh}
            />
            <CodeFormModal
                open={codeModal.open}
                onClose={() => setCodeModal({ open: false, initial: null, defaultSectionId: null })}
                initial={codeModal.initial || (codeModal.defaultSectionId
                    ? { section_id: codeModal.defaultSectionId }
                    : null)}
                sectionOptions={allSectionsFlat.filter((s) => !s.allows_subgroups)}
                onSaved={refresh}
            />
            <DeleteModal
                open={deleteModal.open}
                onClose={() => setDeleteModal({ open: false, target: null, kind: null })}
                target={deleteModal.target}
                kind={deleteModal.kind}
                onConfirmed={refresh}
                onBlocked={offerRetireAfterDeleteBlock}
            />
            <RetireModal
                open={retireModal.open}
                onClose={() => setRetireModal({ open: false, target: null })}
                target={retireModal.target}
                onSaved={refresh}
            />
        </div>
    );
}
