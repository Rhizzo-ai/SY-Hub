import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import EntityForm from "@/components/entity/EntityForm";

function toInitial(e) {
    return {
        name: e.name ?? "",
        legal_name: e.legal_name ?? "",
        entity_type: e.entity_type ?? "SPV",
        parent_entity_id: e.parent_entity_id ?? "",
        companies_house_number: e.companies_house_number ?? "",
        vat_number: e.vat_number ?? "",
        vat_scheme: e.vat_scheme ?? "Standard_Quarterly",
        vat_return_period: e.vat_return_period ?? "Mar_Jun_Sep_Dec",
        utr: e.utr ?? "",
        cis_status: e.cis_status ?? "None",
        registered_address: e.registered_address ?? "",
        trading_address: e.trading_address ?? "",
        default_currency: e.default_currency ?? "GBP",
        incorporation_date: e.incorporation_date ?? "",
        year_end: e.year_end ?? "",
        el_insurance_expires: e.el_insurance_expires ?? "",
        pl_insurance_expires: e.pl_insurance_expires ?? "",
        pi_insurance_expires: e.pi_insurance_expires ?? "",
        all_risks_insurance_expires: e.all_risks_insurance_expires ?? "",
        bank_name: e.bank_name ?? "",
        bank_account_name: e.bank_account_name ?? "",
        bank_account_number: "", // never round-trip the full number
        status: e.status ?? "Active",
        notes: e.notes ?? "",
    };
}

export default function EntityEdit() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [entity, setEntity] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api
            .get(`/entities/${id}`)
            .then((r) => setEntity(r.data))
            .catch((e) => {
                toast.error(e.friendlyMessage);
                navigate("/entities");
            })
            .finally(() => setLoading(false));
    }, [id]);

    const submit = async (payload) => {
        // Only send bank_account_number if user typed a new full one
        if (!payload.bank_account_number) {
            delete payload.bank_account_number;
        }
        const res = await api.put(`/entities/${id}`, payload);
        toast.success("Entity updated");
        navigate(`/entities/${res.data.id}`);
    };

    if (loading || !entity) {
        return (
            <div className="flex items-center gap-2 text-slate-500" data-testid="entity-edit-loading">
                <Loader2 size={14} className="animate-spin" />
                Loading entity…
            </div>
        );
    }

    return (
        <div className="space-y-6" data-testid="entity-edit-page">
            <header>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">
                    Entities · Edit
                </div>
                <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-1">
                    Edit {entity.name}
                </h1>
            </header>
            <EntityForm
                initial={toInitial(entity)}
                submitLabel="Save changes"
                onCancel={() => navigate(`/entities/${id}`)}
                onSubmit={submit}
                disableParentId={id}
            />
        </div>
    );
}
