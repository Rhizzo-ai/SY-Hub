import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import {
    ArrowLeft,
    Pencil,
    Trash2,
    Building2,
    Receipt,
    MapPin,
    ShieldAlert,
    Landmark,
    Link2,
    StickyNote,
    Loader2,
    ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api";
import {
    formatDate,
    formatDateTime,
    formatCompaniesHouse,
    formatVATNumber,
    formatYearEnd,
    displayEnum,
} from "@/lib/format";
import EntityStatusBadge from "@/components/entity/EntityStatusBadge";
import InsuranceBadge from "@/components/entity/InsuranceBadge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

function Section({ icon: Icon, title, children, testid }) {
    return (
        <section
            className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden"
            data-testid={testid}
        >
            <header className="px-6 py-3.5 border-b border-slate-200 bg-slate-50/50 flex items-center gap-2">
                <Icon size={15} strokeWidth={1.75} className="text-slate-500" />
                <h2 className="font-heading text-sm font-semibold text-slate-900 uppercase tracking-widest">
                    {title}
                </h2>
            </header>
            <div className="p-6">{children}</div>
        </section>
    );
}

function Field({ label, children, testid, mono = false }) {
    return (
        <div data-testid={testid}>
            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">
                {label}
            </div>
            <div
                className={`mt-1 text-sm text-slate-900 ${mono ? "mono tabular" : ""}`}
            >
                {children ?? "—"}
            </div>
        </div>
    );
}

export default function EntityDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [entity, setEntity] = useState(null);
    const [loading, setLoading] = useState(true);
    const [deleting, setDeleting] = useState(false);

    const load = () => {
        setLoading(true);
        api
            .get(`/entities/${id}`)
            .then((r) => setEntity(r.data))
            .catch((e) => {
                toast.error(e.friendlyMessage);
                navigate("/entities");
            })
            .finally(() => setLoading(false));
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(load, [id]);

    const onDelete = async () => {
        setDeleting(true);
        try {
            await api.delete(`/entities/${id}`);
            toast.success("Entity deleted");
            navigate("/entities");
        } catch (e) {
            toast.error(e.friendlyMessage);
        } finally {
            setDeleting(false);
        }
    };

    if (loading || !entity) {
        return (
            <div
                className="flex items-center gap-2 text-slate-500"
                data-testid="entity-detail-loading"
            >
                <Loader2 size={14} className="animate-spin" />
                Loading entity…
            </div>
        );
    }

    return (
        <div className="space-y-6" data-testid="entity-detail-page">
            {/* Breadcrumb */}
            <div className="flex items-center gap-2 text-xs text-slate-500">
                <Link
                    to="/entities"
                    className="hover:text-slate-900 inline-flex items-center gap-1"
                    data-testid="breadcrumb-entities"
                >
                    <ArrowLeft size={12} /> Entities
                </Link>
                <ChevronRight size={12} />
                <span className="font-mono text-slate-700">{entity.name}</span>
            </div>

            {/* Header */}
            <header className="flex items-start justify-between gap-6">
                <div>
                    {entity.parent && (
                        <Link
                            to={`/entities/${entity.parent.id}`}
                            className="text-[11px] uppercase tracking-widest text-slate-500 hover:text-slate-900 font-semibold"
                            data-testid="parent-link"
                        >
                            Parent · {entity.parent.name}
                        </Link>
                    )}
                    <h1
                        className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-1"
                        data-testid="entity-detail-name"
                    >
                        {entity.name}
                    </h1>
                    <div className="mt-1 text-sm text-slate-600">
                        {entity.legal_name}
                    </div>
                    <div className="mt-3 flex items-center gap-3 text-xs text-slate-500">
                        <EntityStatusBadge status={entity.status} />
                        <span className="mono tabular">
                            {displayEnum(entity.entity_type)}
                        </span>
                        <span>·</span>
                        <span>
                            Updated{" "}
                            <span className="mono tabular">
                                {formatDateTime(entity.updated_at)}
                            </span>
                        </span>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <Button
                        variant="outline"
                        onClick={() => navigate(`/entities/${id}/edit`)}
                        data-testid="edit-entity-button"
                    >
                        <Pencil size={14} strokeWidth={1.75} className="mr-1.5" />
                        Edit
                    </Button>
                    <AlertDialog>
                        <AlertDialogTrigger asChild>
                            <Button
                                variant="outline"
                                className="text-rose-700 border-rose-200 hover:bg-rose-50 hover:text-rose-800"
                                data-testid="delete-entity-button"
                            >
                                <Trash2 size={14} strokeWidth={1.75} className="mr-1.5" />
                                Delete
                            </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent data-testid="delete-entity-dialog">
                            <AlertDialogHeader>
                                <AlertDialogTitle>Delete this entity?</AlertDialogTitle>
                                <AlertDialogDescription>
                                    This will permanently remove{" "}
                                    <span className="font-medium">{entity.name}</span>.
                                    If the entity has financial history or
                                    linked records, the delete will be blocked —
                                    set status to <span className="font-medium">Struck_off</span>{" "}
                                    instead.
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel data-testid="delete-cancel">
                                    Cancel
                                </AlertDialogCancel>
                                <AlertDialogAction
                                    onClick={onDelete}
                                    disabled={deleting}
                                    className="bg-rose-600 hover:bg-rose-700"
                                    data-testid="delete-confirm"
                                >
                                    {deleting ? "Deleting…" : "Delete entity"}
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>
                </div>
            </header>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Section icon={Building2} title="Identity" testid="section-identity">
                    <div className="grid grid-cols-2 gap-6">
                        <Field label="Name" testid="field-name">
                            {entity.name}
                        </Field>
                        <Field label="Legal name" testid="field-legal-name">
                            {entity.legal_name}
                        </Field>
                        <Field label="Type" testid="field-entity-type">
                            {displayEnum(entity.entity_type)}
                        </Field>
                        <Field label="Status" testid="field-status">
                            <EntityStatusBadge status={entity.status} />
                        </Field>
                        <Field
                            label="Companies House"
                            testid="field-companies-house"
                            mono
                        >
                            {formatCompaniesHouse(entity.companies_house_number)}
                        </Field>
                        <Field
                            label="Incorporation"
                            testid="field-incorporation-date"
                            mono
                        >
                            {entity.incorporation_date
                                ? formatDate(entity.incorporation_date)
                                : "—"}
                        </Field>
                        <Field label="Year end" testid="field-year-end" mono>
                            {formatYearEnd(entity.year_end)}
                        </Field>
                        <Field label="Entity ID" testid="field-id" mono>
                            <span className="text-[11px] text-slate-500">
                                {entity.id}
                            </span>
                        </Field>
                    </div>
                </Section>

                <Section icon={Receipt} title="Tax" testid="section-tax">
                    <div className="grid grid-cols-2 gap-6">
                        <Field label="VAT number" testid="field-vat-number" mono>
                            {entity.vat_number ? formatVATNumber(entity.vat_number) : "—"}
                        </Field>
                        <Field label="VAT scheme" testid="field-vat-scheme">
                            {displayEnum(entity.vat_scheme)}
                        </Field>
                        <Field label="VAT return period" testid="field-vat-return-period">
                            {displayEnum(entity.vat_return_period)}
                        </Field>
                        <Field label="UTR" testid="field-utr" mono>
                            {entity.utr || "—"}
                        </Field>
                        <Field label="CIS status" testid="field-cis-status">
                            {displayEnum(entity.cis_status)}
                        </Field>
                        <Field label="Default currency" testid="field-currency" mono>
                            {entity.default_currency}
                        </Field>
                    </div>
                </Section>

                <Section icon={MapPin} title="Addresses" testid="section-addresses">
                    <div className="space-y-5">
                        <Field label="Registered address" testid="field-registered-address">
                            <pre className="whitespace-pre-wrap font-sans text-sm">
                                {entity.registered_address || "—"}
                            </pre>
                        </Field>
                        <Field label="Trading address" testid="field-trading-address">
                            <pre className="whitespace-pre-wrap font-sans text-sm">
                                {entity.trading_address || "—"}
                            </pre>
                        </Field>
                    </div>
                </Section>

                <Section
                    icon={ShieldAlert}
                    title="Insurance"
                    testid="section-insurance"
                >
                    <div className="grid grid-cols-2 gap-3">
                        <InsuranceBadge
                            label="Employers' Liability"
                            value={entity.el_insurance_expires}
                            testid="insurance-el"
                        />
                        <InsuranceBadge
                            label="Public Liability"
                            value={entity.pl_insurance_expires}
                            testid="insurance-pl"
                        />
                        <InsuranceBadge
                            label="Professional Indemnity"
                            value={entity.pi_insurance_expires}
                            testid="insurance-pi"
                        />
                        <InsuranceBadge
                            label="All Risks"
                            value={entity.all_risks_insurance_expires}
                            testid="insurance-all-risks"
                        />
                    </div>
                    <p className="mt-4 text-xs text-slate-500">
                        Alerts are emitted at 60, 30, 14, 7 and 0 days before expiry.
                    </p>
                </Section>

                <Section icon={Landmark} title="Banking" testid="section-banking">
                    <div className="grid grid-cols-2 gap-6">
                        <Field label="Bank" testid="field-bank-name">
                            {entity.bank_name || "—"}
                        </Field>
                        <Field label="Account name" testid="field-bank-account-name">
                            {entity.bank_account_name || "—"}
                        </Field>
                        <Field
                            label="Account number"
                            testid="field-bank-account-masked"
                            mono
                        >
                            {entity.bank_account_number_masked || "—"}
                        </Field>
                    </div>
                    <p className="mt-4 text-xs text-slate-500">
                        Only the last 4 digits are stored. Full numbers are never retained.
                    </p>
                </Section>

                <Section icon={Link2} title="Xero" testid="section-xero">
                    <div className="grid grid-cols-2 gap-6">
                        <Field label="Xero organisation" testid="field-xero-org-name">
                            {entity.xero_org_name || "Not connected"}
                        </Field>
                        <Field label="Xero org ID" testid="field-xero-org-id" mono>
                            {entity.xero_org_id || "—"}
                        </Field>
                    </div>
                    <p className="mt-4 text-xs text-slate-500">
                        Xero OAuth connection is handled in Prompt 5.1 — these
                        values are populated by the integration and are
                        read-only here.
                    </p>
                </Section>

                <Section
                    icon={StickyNote}
                    title="Hierarchy"
                    testid="section-hierarchy"
                >
                    <div className="space-y-4">
                        <Field label="Parent entity" testid="field-parent">
                            {entity.parent ? (
                                <Link
                                    to={`/entities/${entity.parent.id}`}
                                    className="underline decoration-dotted"
                                    data-testid="hierarchy-parent-link"
                                >
                                    {entity.parent.name} ·{" "}
                                    <span className="text-slate-500">
                                        {displayEnum(entity.parent.entity_type)}
                                    </span>
                                </Link>
                            ) : (
                                "Top-level"
                            )}
                        </Field>
                        <div>
                            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold mb-2">
                                Children ({entity.children.length})
                            </div>
                            {entity.children.length === 0 ? (
                                <div className="text-sm text-slate-500">
                                    No child entities.
                                </div>
                            ) : (
                                <ul
                                    className="divide-y divide-slate-100 border border-slate-200 rounded-md"
                                    data-testid="hierarchy-children-list"
                                >
                                    {entity.children.map((c) => (
                                        <li key={c.id}>
                                            <Link
                                                to={`/entities/${c.id}`}
                                                className="flex items-center justify-between px-3 py-2 hover:bg-slate-50"
                                                data-testid={`hierarchy-child-${c.id}`}
                                            >
                                                <span className="text-sm font-medium text-slate-900">
                                                    {c.name}
                                                </span>
                                                <span className="text-xs text-slate-500 mono tabular">
                                                    {displayEnum(c.entity_type)}
                                                </span>
                                            </Link>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                    </div>
                </Section>

                <Section
                    icon={StickyNote}
                    title="Notes"
                    testid="section-notes"
                >
                    {entity.notes ? (
                        <pre className="whitespace-pre-wrap font-sans text-sm text-slate-800">
                            {entity.notes}
                        </pre>
                    ) : (
                        <div className="text-sm text-slate-500">No notes.</div>
                    )}
                </Section>
            </div>
        </div>
    );
}
