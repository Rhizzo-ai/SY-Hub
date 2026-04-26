import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Loader2, AlertTriangle, Lock, X } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { displayEnum, formatDateTime } from "@/lib/format";
import { toast } from "sonner";

const LOCKED = new Set([
    "code", "prefix", "sequence", "section_id",
    "vat_treatment", "is_vattable",
    "is_cis_applicable", "is_retention_applicable", "is_capitalisable",
]);

const VAT_TREATMENTS = ["Standard", "Reduced", "Zero_New_Build",
                        "Exempt", "Reverse_Charge", "Mixed"];
const DEFAULT_ENTITIES = ["Parent", "SPV", "ConstructionCo", "Context_Dependent"];

export default function CostCodeDetail() {
    const { id } = useParams();
    const nav = useNavigate();
    const { me } = useAuth();
    const isAdmin = (me?.permissions || []).includes("cost_codes.admin")
                    || me?.is_super_admin;

    const [code, setCode] = useState(null);
    const [sections, setSections] = useState([]);
    const [tab, setTab] = useState("identity");
    const [saving, setSaving] = useState(false);
    const [retireOpen, setRetireOpen] = useState(false);
    const [editing, setEditing] = useState({});

    const load = useCallback(async () => {
        const [c, s] = await Promise.all([
            api.get(`/cost-codes/${id}`),
            api.get("/cost-code-sections"),
        ]);
        setCode(c.data); setSections(s.data); setEditing({});
    }, [id]);

    useEffect(() => { load(); }, [load]);

    const onChange = (k, v) => setEditing((e) => ({ ...e, [k]: v }));

    const save = async () => {
        if (Object.keys(editing).length === 0) return;
        setSaving(true);
        try {
            const r = await api.patch(`/cost-codes/${id}`, editing);
            toast.success("Cost code updated");
            setCode(r.data); setEditing({});
        } catch (err) {
            toast.error(err.friendlyMessage || "Update failed");
        } finally { setSaving(false); }
    };

    if (!code) {
        return (
            <div className="flex items-center justify-center py-16" data-testid="cost-code-loading">
                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            </div>
        );
    }

    const displayValue = (k) => editing[k] !== undefined ? editing[k] : code[k];
    const isRetired = code.status === "Retired";

    return (
        <div className="space-y-6 max-w-4xl" data-testid="cost-code-detail">
            <button onClick={() => nav("/cost-codes")}
                    className="text-sm text-slate-600 hover:text-slate-900 inline-flex items-center gap-1">
                <ArrowLeft size={14} /> Back to cost codes
            </button>

            <header className="flex items-start justify-between gap-6">
                <div>
                    <code className="text-sm tabular bg-slate-100 px-2 py-0.5 rounded text-slate-700">
                        {code.code}
                    </code>
                    <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-2">
                        {code.name}
                    </h1>
                    {isRetired && (
                        <div className="mt-3 p-3 rounded-md bg-rose-50 border border-rose-200 text-rose-900 text-sm flex gap-2 max-w-xl"
                             data-testid="retired-banner">
                            <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
                            <div>
                                <b>Retired</b> on {formatDateTime(code.retired_at)}.
                                {code.retired_reason && <> Reason: {code.retired_reason}.</>}
                            </div>
                        </div>
                    )}
                </div>
                {isAdmin && !isRetired && (
                    <div className="flex gap-2">
                        <Button onClick={() => setRetireOpen(true)} variant="outline"
                                className="text-rose-700 border-rose-200 hover:bg-rose-50"
                                data-testid="retire-button">
                            Retire
                        </Button>
                        <Button onClick={save} disabled={Object.keys(editing).length === 0 || saving}
                                className="bg-slate-900 hover:bg-slate-800 text-white"
                                data-testid="save-button">
                            {saving && <Loader2 size={14} className="animate-spin mr-2" />}
                            Save changes
                        </Button>
                    </div>
                )}
            </header>

            <nav className="border-b border-slate-200 flex gap-6" data-testid="cc-tabs">
                {["identity", "tax", "entity", "lifecycle"].map((t) => (
                    <button key={t} onClick={() => setTab(t)}
                            className={`pb-2 text-sm font-medium ${
                                tab === t
                                    ? "text-slate-900 border-b-2 border-slate-900"
                                    : "text-slate-500 hover:text-slate-700"
                            }`}
                            data-testid={`cc-tab-${t}`}>
                        {{ identity: "Identity",
                           tax: "Tax & Treatment",
                           entity: "Entity Routing",
                           lifecycle: "Lifecycle" }[t]}
                    </button>
                ))}
            </nav>

            {tab === "identity" && (
                <Section title="Identity">
                    <Field label="Code" locked>
                        <code className="block text-sm bg-slate-100 px-3 py-1.5 rounded">{code.code}</code>
                    </Field>
                    <Field label="Name" editable={isAdmin}>
                        <Input value={displayValue("name") || ""}
                               onChange={(e) => onChange("name", e.target.value)}
                               disabled={!isAdmin}
                               data-testid="field-name" />
                    </Field>
                    <Field label="Description" editable={isAdmin}>
                        <textarea value={displayValue("description") || ""}
                                  onChange={(e) => onChange("description", e.target.value)}
                                  disabled={!isAdmin} rows={3}
                                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
                    </Field>
                    <Field label="Section" locked>
                        <span>{sections.find((s) => s.id === code.section_id)?.name || "—"}</span>
                    </Field>
                    <Field label="Buildertrend Category" editable={isAdmin}>
                        <Input value={displayValue("buildertrend_category") || ""}
                               onChange={(e) => onChange("buildertrend_category", e.target.value)}
                               disabled={!isAdmin} />
                    </Field>
                    <Field label="NRM Reference" editable={isAdmin}>
                        <Input value={displayValue("nrm_reference") || ""}
                               onChange={(e) => onChange("nrm_reference", e.target.value)}
                               disabled={!isAdmin} />
                    </Field>
                </Section>
            )}

            {tab === "tax" && (
                <Section title="Tax & Treatment">
                    <Field label="VAT treatment" locked>
                        <span className="text-sm">{displayEnum(code.vat_treatment)}</span>
                        <Lock size={12} className="inline ml-2 text-slate-400" />
                    </Field>
                    <Field label="VATable" locked>
                        <span>{code.is_vattable ? "Yes" : "No"}</span>
                    </Field>
                    <Field label="CIS applicable" locked>
                        <span>{code.is_cis_applicable ? "Yes" : "No"}</span>
                    </Field>
                    <Field label="Retention applicable" locked>
                        <span>{code.is_retention_applicable ? "Yes" : "No"}</span>
                    </Field>
                    <Field label="Capitalisable" locked>
                        <span>{code.is_capitalisable ? "Yes" : "No"}</span>
                    </Field>
                    <p className="text-xs text-slate-500 italic">
                        Tax flags are locked once any project, appraisal, budget or
                        actual references the code. Edit only on fresh codes; otherwise
                        retire and replace.
                    </p>
                </Section>
            )}

            {tab === "entity" && (
                <Section title="Entity Routing (defaults — overrides per project / mapping)">
                    <Field label="Default entity" editable={isAdmin}>
                        <select value={displayValue("default_entity")}
                                onChange={(e) => onChange("default_entity", e.target.value)}
                                disabled={!isAdmin}
                                className="w-full h-9 rounded-md border border-slate-300 px-3 text-sm">
                            {DEFAULT_ENTITIES.map((d) => (
                                <option key={d} value={d}>{displayEnum(d)}</option>
                            ))}
                        </select>
                    </Field>
                    <Field label="Applies to Parent" editable={isAdmin}>
                        <input type="checkbox" checked={!!displayValue("applies_to_parent")}
                               onChange={(e) => onChange("applies_to_parent", e.target.checked)}
                               disabled={!isAdmin} />
                    </Field>
                    <Field label="Applies to SPV" editable={isAdmin}>
                        <input type="checkbox" checked={!!displayValue("applies_to_spv")}
                               onChange={(e) => onChange("applies_to_spv", e.target.checked)}
                               disabled={!isAdmin} />
                    </Field>
                    <Field label="Applies to ConstructionCo" editable={isAdmin}>
                        <input type="checkbox" checked={!!displayValue("applies_to_construction_co")}
                               onChange={(e) => onChange("applies_to_construction_co", e.target.checked)}
                               disabled={!isAdmin} />
                    </Field>
                </Section>
            )}

            {tab === "lifecycle" && (
                <Section title="Lifecycle">
                    <Field label="Status"><span>{code.status}</span></Field>
                    <Field label="Retired at">
                        <span>{formatDateTime(code.retired_at) || "—"}</span>
                    </Field>
                    <Field label="Retired reason">
                        <span className="text-sm text-slate-700">{code.retired_reason || "—"}</span>
                    </Field>
                    <Field label="Replaced by">
                        {code.replaced_by_code_id
                            ? <Link to={`/cost-codes/${code.replaced_by_code_id}`}
                                    className="text-sm underline decoration-dotted">
                                view replacement →
                              </Link>
                            : "—"}
                    </Field>
                </Section>
            )}

            {retireOpen && (
                <RetireModal id={id} sections={sections}
                             onClose={() => setRetireOpen(false)}
                             onDone={() => { setRetireOpen(false); load(); }} />
            )}
        </div>
    );
}


function Section({ title, children }) {
    return (
        <section className="bg-white border border-slate-200 rounded-md">
            <h2 className="px-5 py-3 border-b border-slate-200 text-sm font-semibold uppercase tracking-widest text-slate-500">
                {title}
            </h2>
            <div className="p-5 space-y-4">{children}</div>
        </section>
    );
}


function Field({ label, locked, editable, children }) {
    return (
        <div className="grid grid-cols-[180px_1fr] gap-4 items-start">
            <div className="text-xs font-medium text-slate-700 pt-2 flex items-center gap-1">
                {label}
                {locked && <Lock size={11} className="text-slate-400" />}
            </div>
            <div>{children}</div>
        </div>
    );
}


function RetireModal({ id, sections, onClose, onDone }) {
    const [reason, setReason] = useState("");
    const [replaceWith, setReplaceWith] = useState("");
    const [saving, setSaving] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
            await api.post(`/cost-codes/${id}/retire`, {
                retired_reason: reason,
                replaced_by_code_id: replaceWith || undefined,
            });
            toast.success("Cost code retired");
            onDone();
        } catch (err) {
            toast.error(err.friendlyMessage || "Retire failed");
        } finally { setSaving(false); }
    };

    return (
        <div className="fixed inset-0 bg-slate-900/40 flex items-start justify-center p-6 z-50 overflow-y-auto"
             onClick={onClose} data-testid="retire-modal">
            <div className="bg-white rounded-lg shadow-xl max-w-lg w-full p-6 my-8"
                 onClick={(e) => e.stopPropagation()}>
                <div className="flex justify-between items-start mb-4">
                    <h2 className="text-lg font-semibold">Retire cost code</h2>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
                        <X size={18} />
                    </button>
                </div>
                <form onSubmit={submit} className="space-y-4">
                    <div>
                        <label className="text-xs font-medium text-slate-700 mb-1 block">
                            Reason (≥ 3 chars)
                        </label>
                        <textarea value={reason} onChange={(e) => setReason(e.target.value)}
                                  rows={3} required minLength={3}
                                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                                  data-testid="retire-reason" />
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-700 mb-1 block">
                            Replaced by (optional)
                        </label>
                        <Input value={replaceWith}
                               onChange={(e) => setReplaceWith(e.target.value)}
                               placeholder="UUID of replacement code"
                               data-testid="retire-replacement" />
                        <p className="text-xs text-slate-500 mt-1">
                            Leave blank if the code is being retired without replacement.
                            Cycle prevention enforced server-side.
                        </p>
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                        <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
                        <Button type="submit" disabled={saving || reason.length < 3}
                                className="bg-rose-700 hover:bg-rose-800 text-white"
                                data-testid="retire-submit">
                            {saving && <Loader2 size={14} className="animate-spin mr-2" />}
                            Retire
                        </Button>
                    </div>
                </form>
            </div>
        </div>
    );
}
