import React from "react";
import { formatDate, daysUntil } from "@/lib/format";

/**
 * Insurance expiry highlight system, per spec:
 *   - >60 days  → neutral
 *   - <60 days  → amber warning
 *   - <14 days  → red critical
 *   - past      → red "EXPIRED"
 */
export default function InsuranceBadge({ label, value, testid }) {
    const days = daysUntil(value);
    let tone;
    let suffix = null;

    if (value == null || value === "") {
        tone = "empty";
    } else if (days == null) {
        tone = "empty";
    } else if (days < 0) {
        tone = "expired";
        suffix = "EXPIRED";
    } else if (days <= 14) {
        tone = "critical";
        suffix = `${days}d left`;
    } else if (days <= 60) {
        tone = "warning";
        suffix = `${days}d left`;
    } else {
        tone = "ok";
        suffix = `${days}d`;
    }

    const wrapCls =
        {
            empty: "bg-slate-50 border-slate-200 text-slate-400",
            ok: "bg-slate-50 border-slate-200 text-slate-700",
            warning: "bg-amber-50 border-amber-200 text-amber-900",
            critical: "bg-rose-50 border-rose-200 text-rose-900",
            expired: "bg-rose-600 border-rose-700 text-white",
        }[tone] || "bg-slate-50";

    const suffixCls =
        {
            ok: "text-slate-500",
            warning: "text-amber-700 font-medium",
            critical: "text-rose-700 font-semibold",
            expired: "text-white font-bold tracking-wider",
        }[tone] || "text-slate-400";

    return (
        <div
            className={`rounded-md border p-3 ${wrapCls}`}
            data-testid={testid}
            data-urgency={tone}
        >
            <div className="text-[10px] uppercase tracking-widest opacity-80">
                {label}
            </div>
            <div className="mt-1 font-mono text-sm tabular">
                {value ? formatDate(value) : "Not set"}
            </div>
            {suffix && (
                <div className={`mt-1 text-xs ${suffixCls}`}>{suffix}</div>
            )}
        </div>
    );
}
