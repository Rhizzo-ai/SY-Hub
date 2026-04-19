import React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import EntityForm from "@/components/entity/EntityForm";

export default function EntityNew() {
    const navigate = useNavigate();

    const submit = async (payload) => {
        const res = await api.post("/entities", payload);
        toast.success("Entity created");
        navigate(`/entities/${res.data.id}`);
    };

    return (
        <div className="space-y-6" data-testid="entity-new-page">
            <header>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">
                    Entities · New
                </div>
                <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-1">
                    Create entity
                </h1>
                <p className="text-sm text-slate-600 mt-1">
                    Add a new legal entity to the SY Homes group.
                </p>
            </header>
            <EntityForm
                onSubmit={submit}
                submitLabel="Create entity"
                onCancel={() => navigate("/entities")}
            />
        </div>
    );
}
