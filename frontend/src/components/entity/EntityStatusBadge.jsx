import React from "react";
import { displayEnum } from "@/lib/format";

const STYLES = {
    Active: "bg-emerald-100 text-emerald-800 border-emerald-200",
    Dormant: "bg-amber-100 text-amber-800 border-amber-200",
    Struck_off: "bg-rose-100 text-rose-800 border-rose-200",
};

export default function EntityStatusBadge({ status }) {
    const cls = STYLES[status] || "bg-slate-100 text-slate-700 border-slate-200";
    return (
        <span
            className={`inline-flex items-center rounded-sm border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider ${cls}`}
            data-testid={`status-badge-${status}`}
        >
            {displayEnum(status)}
        </span>
    );
}
