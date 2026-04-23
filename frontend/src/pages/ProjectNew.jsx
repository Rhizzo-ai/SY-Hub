import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

const PROJECT_TYPES = ["Pure_Dev", "Dev_Build", "DB_Contract", "JV", "Main_Contract"];
const LAND_OWNERSHIPS = [
    "Direct_Purchase", "Option", "Conditional_Contract",
    "JV_Contribution", "Existing_Holding",
];
const TENURES = ["Freehold", "Leasehold", "Long_Leasehold", "Option", "Conditional", "Other"];
const PLANNING_TYPES = [
    "Full", "Outline", "Reserved_Matters", "Hybrid",
    "Permitted_Dev", "Prior_Approval",
];
const PLANNING_STATUSES = [
    "Pre_App", "Submitted", "Approved", "Refused", "Appeal", "Not_Required",
];

const HA_TO_ACRES = 2.47105;

export default function ProjectNew() {
    const nav = useNavigate();
    const { me } = useAuth();
    const canCreate = (me?.permissions || []).includes("projects.create") || me?.is_super_admin;
    const [saving, setSaving] = useState(false);
    const [entities, setEntities] = useState([]);

    useEffect(() => {
        if (me && !canCreate) {
            toast.error("You don't have permission to create projects.");
            nav("/projects", { replace: true });
        }
    }, [me, canCreate, nav]);

    const [form, setForm] = useState({
        name: "",
        project_code: "",
        project_type: "Dev_Build",
        primary_entity_id: "",
        construction_entity_id: "",
        land_ownership_method: "Direct_Purchase",
        site_address: "",
        site_postcode: "",
        local_authority: "",
        tenure: "Freehold",
        site_area_ha: "",
        site_area_acres: "",
        planning_type: "",
        planning_approval_date: "",
        planning_expiry_date: "",
        units_target: "",
        target_start_date: "",
        target_pc_date: "",
        notes: "",
    });

    useEffect(() => {
        api.get("/entities", { params: { page: 1, page_size: 200 } })
            .then((r) => setEntities(r.data.items || []));
    }, []);

    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

    const onHaChange = (v) => {
        set("site_area_ha", v);
        if (v && !Number.isNaN(parseFloat(v))) {
            const a = (parseFloat(v) * HA_TO_ACRES).toFixed(4);
            set("site_area_acres", a);
        } else {
            set("site_area_acres", "");
        }
    };
    const onAcresChange = (v) => {
        set("site_area_acres", v);
        if (v && !Number.isNaN(parseFloat(v))) {
            const ha = (parseFloat(v) / HA_TO_ACRES).toFixed(4);
            set("site_area_ha", ha);
        } else {
            set("site_area_ha", "");
        }
    };

    const expiryPreview = (() => {
        if (!form.planning_type || !form.planning_approval_date) return null;
        const d = new Date(form.planning_approval_date);
        if (Number.isNaN(d.getTime())) return null;
        const years = form.planning_type === "Reserved_Matters" ? 2 : 3;
        const out = new Date(d);
        out.setFullYear(out.getFullYear() + years);
        return out.toISOString().slice(0, 10);
    })();

    const canSubmit = form.name && form.project_type && form.primary_entity_id
        && form.land_ownership_method && form.site_address && form.site_postcode
        && form.tenure;

    const onSubmit = async (e) => {
        e.preventDefault();
        if (!canSubmit) return;
        setSaving(true);
        try {
            const payload = {};
            Object.entries(form).forEach(([k, v]) => {
                if (v !== "" && v != null) payload[k] = v;
            });
            // Strip optional empty fields
            if (payload.units_target) payload.units_target = parseInt(payload.units_target, 10);
            const r = await api.post("/projects", payload);
            toast.success(`Project ${r.data.project_code} created`);
            nav(`/projects/${r.data.id}`);
        } catch (err) {
            toast.error(err.friendlyMessage || "Failed to create project");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="max-w-4xl" data-testid="project-new-page">
            <button onClick={() => nav("/projects")}
                    className="text-sm text-slate-600 hover:text-slate-900 inline-flex items-center gap-1 mb-4"
                    data-testid="back-to-projects">
                <ArrowLeft size={14} /> Back to projects
            </button>
            <h1 className="font-heading text-3xl font-bold text-slate-900">New Project</h1>
            <p className="text-sm text-slate-600 mt-1">
                Leave <span className="mono">Project code</span> blank for an auto-generated code.
            </p>

            <form onSubmit={onSubmit} className="mt-6 space-y-8" data-testid="project-new-form">
                <Section title="Basics">
                    <Field label="Name" required>
                        <Input value={form.name} onChange={(e) => set("name", e.target.value)}
                               data-testid="field-name" />
                    </Field>
                    <Field label="Project code (optional — auto if blank)">
                        <Input value={form.project_code}
                               onChange={(e) => set("project_code", e.target.value.toUpperCase())}
                               placeholder="ABC-001"
                               className="mono tabular"
                               data-testid="field-project-code" />
                    </Field>
                    <Field label="Type" required>
                        <Select value={form.project_type}
                                onChange={(v) => set("project_type", v)}
                                options={PROJECT_TYPES}
                                testid="field-project-type" />
                    </Field>
                    <Field label="Primary entity" required>
                        <Select value={form.primary_entity_id}
                                onChange={(v) => set("primary_entity_id", v)}
                                options={[{ value: "", label: "— Select —" },
                                          ...entities.map((e) => ({ value: e.id, label: e.name }))]}
                                testid="field-primary-entity" />
                    </Field>
                    <Field label="Construction entity (optional)">
                        <Select value={form.construction_entity_id}
                                onChange={(v) => set("construction_entity_id", v)}
                                options={[{ value: "", label: "— None —" },
                                          ...entities.map((e) => ({ value: e.id, label: e.name }))]}
                                testid="field-construction-entity" />
                    </Field>
                </Section>

                <Section title="Site">
                    <Field label="Address" required>
                        <Input value={form.site_address}
                               onChange={(e) => set("site_address", e.target.value)}
                               data-testid="field-site-address" />
                    </Field>
                    <Field label="Postcode" required>
                        <Input value={form.site_postcode}
                               onChange={(e) => set("site_postcode", e.target.value.toUpperCase())}
                               maxLength={10}
                               data-testid="field-postcode" />
                    </Field>
                    <Field label="Local authority">
                        <Input value={form.local_authority}
                               onChange={(e) => set("local_authority", e.target.value)}
                               data-testid="field-local-authority" />
                    </Field>
                    <Field label="Land ownership method" required>
                        <Select value={form.land_ownership_method}
                                onChange={(v) => set("land_ownership_method", v)}
                                options={LAND_OWNERSHIPS}
                                testid="field-ownership" />
                    </Field>
                    <Field label="Tenure" required>
                        <Select value={form.tenure}
                                onChange={(v) => set("tenure", v)}
                                options={TENURES} testid="field-tenure" />
                    </Field>
                    <div className="grid grid-cols-2 gap-3">
                        <Field label="Area (ha)">
                            <Input type="number" step="0.0001" value={form.site_area_ha}
                                   onChange={(e) => onHaChange(e.target.value)}
                                   data-testid="field-area-ha" />
                        </Field>
                        <Field label="Area (acres)">
                            <Input type="number" step="0.0001" value={form.site_area_acres}
                                   onChange={(e) => onAcresChange(e.target.value)}
                                   data-testid="field-area-acres" />
                        </Field>
                    </div>
                </Section>

                <Section title="Planning (optional)">
                    <Field label="Planning type">
                        <Select value={form.planning_type}
                                onChange={(v) => set("planning_type", v)}
                                options={[{ value: "", label: "—" },
                                          ...PLANNING_TYPES.map((p) => ({ value: p, label: p.replace(/_/g, " ") }))]}
                                testid="field-planning-type" />
                    </Field>
                    <Field label="Approval date">
                        <Input type="date" value={form.planning_approval_date}
                               onChange={(e) => set("planning_approval_date", e.target.value)}
                               data-testid="field-approval-date" />
                    </Field>
                    <Field label={
                        <>
                            Expiry date
                            {expiryPreview && (
                                <span className="ml-2 text-[11px] text-slate-500"
                                      data-testid="expiry-preview">
                                    auto: <span className="mono">{expiryPreview}</span>
                                </span>
                            )}
                        </>
                    }>
                        <Input type="date" value={form.planning_expiry_date}
                               onChange={(e) => set("planning_expiry_date", e.target.value)}
                               placeholder={expiryPreview || ""}
                               data-testid="field-expiry-date" />
                    </Field>
                </Section>

                <Section title="Targets (optional)">
                    <div className="grid grid-cols-3 gap-3">
                        <Field label="Units target">
                            <Input type="number" value={form.units_target}
                                   onChange={(e) => set("units_target", e.target.value)}
                                   data-testid="field-units-target" />
                        </Field>
                        <Field label="Target start">
                            <Input type="date" value={form.target_start_date}
                                   onChange={(e) => set("target_start_date", e.target.value)}
                                   data-testid="field-target-start" />
                        </Field>
                        <Field label="Target PC">
                            <Input type="date" value={form.target_pc_date}
                                   onChange={(e) => set("target_pc_date", e.target.value)}
                                   data-testid="field-target-pc" />
                        </Field>
                    </div>
                    <Field label="Notes">
                        <textarea value={form.notes}
                                  onChange={(e) => set("notes", e.target.value)}
                                  rows={4}
                                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                                  data-testid="field-notes" />
                    </Field>
                </Section>

                <div className="flex items-center gap-3 pt-4 border-t border-slate-200">
                    <Button type="submit" disabled={!canSubmit || saving}
                            className="bg-slate-900 hover:bg-slate-800 text-white"
                            data-testid="submit-project">
                        {saving && <Loader2 size={14} className="animate-spin mr-2" />}
                        Create Project
                    </Button>
                    <Button type="button" variant="outline" onClick={() => nav("/projects")}
                            data-testid="cancel-project">Cancel</Button>
                </div>
            </form>
        </div>
    );
}

function Section({ title, children }) {
    return (
        <div>
            <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-500 pb-2 border-b border-slate-200">
                {title}
            </h2>
            <div className="mt-4 space-y-4">{children}</div>
        </div>
    );
}

function Field({ label, required, children }) {
    return (
        <div>
            <label className="text-xs font-medium text-slate-700 mb-1 block">
                {label} {required && <span className="text-rose-600">*</span>}
            </label>
            {children}
        </div>
    );
}

function Select({ value, onChange, options, testid }) {
    const normalized = options.map((o) =>
        typeof o === "string" ? { value: o, label: o.replace(/_/g, " ") } : o
    );
    return (
        <select value={value}
                onChange={(e) => onChange(e.target.value)}
                className="w-full h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                data-testid={testid}>
            {normalized.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
            ))}
        </select>
    );
}
