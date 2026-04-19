import React, { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2, Save, X } from "lucide-react";
import { api } from "@/lib/api";
import { useEnums } from "@/hooks/useTenant";
import { displayEnum } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

const CH_RE = /^[A-Z0-9]{8}$/;
const YE_RE = /^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$/;
const BANK_RE = /^\d{8}$/;

const schema = z.object({
    name: z.string().min(1, "Required").max(255),
    legal_name: z.string().min(1, "Required").max(255),
    entity_type: z.string().min(1, "Required"),
    parent_entity_id: z.string().optional().nullable().or(z.literal("")),
    companies_house_number: z
        .string()
        .optional()
        .or(z.literal(""))
        .refine((v) => !v || CH_RE.test(v.toUpperCase()), {
            message: "Must be 8 alphanumeric characters",
        }),
    vat_number: z
        .string()
        .optional()
        .or(z.literal(""))
        .refine((v) => !v || /^\d{9,12}$/.test(v.replace(/\D/g, "")), {
            message: "9–12 digits",
        }),
    vat_scheme: z.string().min(1),
    vat_return_period: z.string().min(1),
    utr: z.string().optional().or(z.literal("")),
    cis_status: z.string().optional(),
    registered_address: z.string().min(1, "Required"),
    trading_address: z.string().optional().or(z.literal("")),
    default_currency: z
        .string()
        .min(3)
        .max(3)
        .transform((v) => v.toUpperCase()),
    incorporation_date: z.string().optional().or(z.literal("")),
    year_end: z
        .string()
        .optional()
        .or(z.literal(""))
        .refine((v) => !v || YE_RE.test(v), {
            message: "Use MM-DD, e.g. 03-31",
        }),
    el_insurance_expires: z.string().optional().or(z.literal("")),
    pl_insurance_expires: z.string().optional().or(z.literal("")),
    pi_insurance_expires: z.string().optional().or(z.literal("")),
    all_risks_insurance_expires: z.string().optional().or(z.literal("")),
    bank_name: z.string().optional().or(z.literal("")),
    bank_account_name: z.string().optional().or(z.literal("")),
    bank_account_number: z
        .string()
        .optional()
        .or(z.literal(""))
        .refine((v) => !v || BANK_RE.test(v.replace(/\D/g, "")), {
            message: "Must be 8 digits",
        }),
    status: z.string().min(1),
    notes: z.string().optional().or(z.literal("")),
});

function emptyToNull(o) {
    const out = {};
    for (const [k, v] of Object.entries(o)) {
        if (v === "" || v === undefined) {
            out[k] = null;
        } else {
            out[k] = v;
        }
    }
    return out;
}

export default function EntityForm({ initial, onSubmit, submitLabel, onCancel, disableParentId }) {
    const enums = useEnums();
    const [entitiesList, setEntitiesList] = useState([]);

    const form = useForm({
        resolver: zodResolver(schema),
        mode: "onBlur",
        defaultValues: {
            name: "",
            legal_name: "",
            entity_type: "SPV",
            parent_entity_id: "",
            companies_house_number: "",
            vat_number: "",
            vat_scheme: "Standard_Quarterly",
            vat_return_period: "Mar_Jun_Sep_Dec",
            utr: "",
            cis_status: "None",
            registered_address: "",
            trading_address: "",
            default_currency: "GBP",
            incorporation_date: "",
            year_end: "",
            el_insurance_expires: "",
            pl_insurance_expires: "",
            pi_insurance_expires: "",
            all_risks_insurance_expires: "",
            bank_name: "",
            bank_account_name: "",
            bank_account_number: "",
            status: "Active",
            notes: "",
            ...initial,
        },
    });

    useEffect(() => {
        // Fetch all entities for parent dropdown (exclude struck_off + self)
        api
            .get("/entities", { params: { page_size: 200, include_struck_off: false } })
            .then((r) => setEntitiesList(r.data.items));
    }, []);

    const onValid = async (values) => {
        const payload = emptyToNull(values);
        // Cast CH to uppercase (validator tolerated lowercase)
        if (payload.companies_house_number) {
            payload.companies_house_number =
                payload.companies_house_number.toUpperCase();
        }
        try {
            await onSubmit(payload);
        } catch (e) {
            toast.error(e.friendlyMessage || "Save failed");
        }
    };

    const parentOptions = entitiesList.filter((e) => e.id !== disableParentId);

    const FieldRow = ({ label, name, required, children, description, testid }) => {
        const err = form.formState.errors[name];
        return (
            <div data-testid={testid}>
                <label className="block text-[11px] uppercase tracking-widest text-slate-500 font-semibold mb-1.5">
                    {label} {required && <span className="text-rose-500">*</span>}
                </label>
                {children}
                {description && !err && (
                    <div className="text-[11px] text-slate-500 mt-1">
                        {description}
                    </div>
                )}
                {err && (
                    <div
                        className="text-[11px] text-rose-600 mt-1"
                        data-testid={`${testid}-error`}
                    >
                        {err.message}
                    </div>
                )}
            </div>
        );
    };

    const InputField = (props) => (
        <Input
            {...props}
            className={`bg-white h-9 ${props.className ?? ""}`}
        />
    );

    const Section = ({ title, children }) => (
        <section className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden">
            <header className="px-6 py-3.5 border-b border-slate-200 bg-slate-50/50">
                <h2 className="font-heading text-sm font-semibold text-slate-900 uppercase tracking-widest">
                    {title}
                </h2>
            </header>
            <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-5">
                {children}
            </div>
        </section>
    );

    return (
        <form
            onSubmit={form.handleSubmit(onValid)}
            className="space-y-6"
            data-testid="entity-form"
            noValidate
        >
            <Section title="Identity">
                <FieldRow label="Name" name="name" required testid="field-name">
                    <InputField
                        {...form.register("name")}
                        data-testid="input-name"
                    />
                </FieldRow>
                <FieldRow label="Legal name" name="legal_name" required testid="field-legal-name">
                    <InputField
                        {...form.register("legal_name")}
                        data-testid="input-legal-name"
                    />
                </FieldRow>
                <FieldRow label="Type" name="entity_type" required testid="field-entity-type">
                    <select
                        {...form.register("entity_type")}
                        className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"
                        data-testid="input-entity-type"
                    >
                        {enums?.entity_types.map((t) => (
                            <option key={t} value={t}>
                                {displayEnum(t)}
                            </option>
                        ))}
                    </select>
                </FieldRow>
                <FieldRow label="Parent entity" name="parent_entity_id" testid="field-parent">
                    <select
                        {...form.register("parent_entity_id")}
                        className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"
                        data-testid="input-parent"
                    >
                        <option value="">None (top-level)</option>
                        {parentOptions.map((e) => (
                            <option key={e.id} value={e.id}>
                                {e.name} · {displayEnum(e.entity_type)}
                            </option>
                        ))}
                    </select>
                </FieldRow>
                <FieldRow
                    label="Companies House number"
                    name="companies_house_number"
                    description="8 alphanumeric chars, e.g. 12345678 or SC123456"
                    testid="field-companies-house"
                >
                    <InputField
                        {...form.register("companies_house_number")}
                        className="mono"
                        maxLength={10}
                        data-testid="input-companies-house"
                    />
                </FieldRow>
                <FieldRow
                    label="Incorporation date"
                    name="incorporation_date"
                    testid="field-incorporation-date"
                >
                    <InputField
                        type="date"
                        {...form.register("incorporation_date")}
                        className="mono"
                        data-testid="input-incorporation-date"
                    />
                </FieldRow>
                <FieldRow
                    label="Year end (MM-DD)"
                    name="year_end"
                    description="e.g. 03-31"
                    testid="field-year-end"
                >
                    <InputField
                        placeholder="03-31"
                        {...form.register("year_end")}
                        className="mono"
                        maxLength={5}
                        data-testid="input-year-end"
                    />
                </FieldRow>
                <FieldRow label="Status" name="status" required testid="field-status">
                    <select
                        {...form.register("status")}
                        className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"
                        data-testid="input-status"
                    >
                        {enums?.entity_statuses.map((s) => (
                            <option key={s} value={s}>
                                {displayEnum(s)}
                            </option>
                        ))}
                    </select>
                </FieldRow>
            </Section>

            <Section title="Tax">
                <FieldRow
                    label="VAT number"
                    name="vat_number"
                    description="9–12 digits; GB prefix added on display"
                    testid="field-vat-number"
                >
                    <InputField
                        {...form.register("vat_number")}
                        className="mono"
                        maxLength={15}
                        data-testid="input-vat-number"
                    />
                </FieldRow>
                <FieldRow label="VAT scheme" name="vat_scheme" required testid="field-vat-scheme">
                    <select
                        {...form.register("vat_scheme")}
                        className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"
                        data-testid="input-vat-scheme"
                    >
                        {enums?.vat_schemes.map((s) => (
                            <option key={s} value={s}>
                                {displayEnum(s)}
                            </option>
                        ))}
                    </select>
                </FieldRow>
                <FieldRow
                    label="VAT return period"
                    name="vat_return_period"
                    required
                    testid="field-vat-return-period"
                >
                    <select
                        {...form.register("vat_return_period")}
                        className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"
                        data-testid="input-vat-return-period"
                    >
                        {enums?.vat_return_periods.map((s) => (
                            <option key={s} value={s}>
                                {displayEnum(s)}
                            </option>
                        ))}
                    </select>
                </FieldRow>
                <FieldRow label="UTR" name="utr" testid="field-utr">
                    <InputField
                        {...form.register("utr")}
                        className="mono"
                        maxLength={13}
                        data-testid="input-utr"
                    />
                </FieldRow>
                <FieldRow label="CIS status" name="cis_status" testid="field-cis-status">
                    <select
                        {...form.register("cis_status")}
                        className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm"
                        data-testid="input-cis-status"
                    >
                        {enums?.cis_statuses.map((s) => (
                            <option key={s} value={s}>
                                {displayEnum(s)}
                            </option>
                        ))}
                    </select>
                </FieldRow>
                <FieldRow
                    label="Default currency (ISO 4217)"
                    name="default_currency"
                    required
                    testid="field-currency"
                >
                    <InputField
                        {...form.register("default_currency")}
                        className="mono uppercase"
                        maxLength={3}
                        data-testid="input-currency"
                    />
                </FieldRow>
            </Section>

            <Section title="Addresses">
                <div className="md:col-span-2">
                    <FieldRow
                        label="Registered address"
                        name="registered_address"
                        required
                        testid="field-registered-address"
                    >
                        <Textarea
                            {...form.register("registered_address")}
                            rows={3}
                            className="bg-white"
                            data-testid="input-registered-address"
                        />
                    </FieldRow>
                </div>
                <div className="md:col-span-2">
                    <FieldRow
                        label="Trading address"
                        name="trading_address"
                        testid="field-trading-address"
                    >
                        <Textarea
                            {...form.register("trading_address")}
                            rows={3}
                            className="bg-white"
                            data-testid="input-trading-address"
                        />
                    </FieldRow>
                </div>
            </Section>

            <Section title="Insurance expiries">
                <FieldRow
                    label="Employers' Liability"
                    name="el_insurance_expires"
                    testid="field-el-insurance"
                >
                    <InputField
                        type="date"
                        {...form.register("el_insurance_expires")}
                        className="mono"
                        data-testid="input-el-insurance"
                    />
                </FieldRow>
                <FieldRow
                    label="Public Liability"
                    name="pl_insurance_expires"
                    testid="field-pl-insurance"
                >
                    <InputField
                        type="date"
                        {...form.register("pl_insurance_expires")}
                        className="mono"
                        data-testid="input-pl-insurance"
                    />
                </FieldRow>
                <FieldRow
                    label="Professional Indemnity"
                    name="pi_insurance_expires"
                    testid="field-pi-insurance"
                >
                    <InputField
                        type="date"
                        {...form.register("pi_insurance_expires")}
                        className="mono"
                        data-testid="input-pi-insurance"
                    />
                </FieldRow>
                <FieldRow
                    label="All Risks"
                    name="all_risks_insurance_expires"
                    testid="field-all-risks"
                >
                    <InputField
                        type="date"
                        {...form.register("all_risks_insurance_expires")}
                        className="mono"
                        data-testid="input-all-risks"
                    />
                </FieldRow>
            </Section>

            <Section title="Banking">
                <FieldRow label="Bank name" name="bank_name" testid="field-bank-name">
                    <InputField
                        {...form.register("bank_name")}
                        data-testid="input-bank-name"
                    />
                </FieldRow>
                <FieldRow
                    label="Account name"
                    name="bank_account_name"
                    testid="field-bank-account-name"
                >
                    <InputField
                        {...form.register("bank_account_name")}
                        data-testid="input-bank-account-name"
                    />
                </FieldRow>
                <div className="md:col-span-2">
                    <FieldRow
                        label="Account number (8 digits — only last 4 stored)"
                        name="bank_account_number"
                        description="Full number is not retained. Masked as ****1234."
                        testid="field-bank-account-number"
                    >
                        <InputField
                            {...form.register("bank_account_number")}
                            className="mono"
                            maxLength={8}
                            inputMode="numeric"
                            data-testid="input-bank-account-number"
                        />
                    </FieldRow>
                </div>
            </Section>

            <Section title="Notes">
                <div className="md:col-span-2">
                    <FieldRow label="Notes" name="notes" testid="field-notes">
                        <Textarea
                            {...form.register("notes")}
                            rows={4}
                            className="bg-white"
                            data-testid="input-notes"
                        />
                    </FieldRow>
                </div>
            </Section>

            <div className="flex items-center justify-end gap-2 sticky bottom-0 bg-slate-50 py-3 -mx-8 px-8 border-t border-slate-200">
                {onCancel && (
                    <Button
                        type="button"
                        variant="outline"
                        onClick={onCancel}
                        data-testid="form-cancel"
                    >
                        <X size={14} strokeWidth={1.75} className="mr-1.5" />
                        Cancel
                    </Button>
                )}
                <Button
                    type="submit"
                    disabled={form.formState.isSubmitting}
                    className="bg-slate-900 hover:bg-slate-800 text-white"
                    data-testid="form-submit"
                >
                    {form.formState.isSubmitting ? (
                        <Loader2 size={14} className="mr-1.5 animate-spin" />
                    ) : (
                        <Save size={14} strokeWidth={1.75} className="mr-1.5" />
                    )}
                    {submitLabel || "Save"}
                </Button>
            </div>
        </form>
    );
}
