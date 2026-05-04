/**
 * Appraisal atoms + enum constants shared across the 5 tab components.
 * Kept together so tab files can import exactly what they need without
 * each one redefining UI primitives.
 */
import React from "react";
import { AlertTriangle, Lock } from "lucide-react";


// ----- enum constants (parity with backend app/models/appraisals.py) ----

export const STATE_BADGE = {
    Draft: "bg-slate-100 text-slate-700 border-slate-300",
    Submitted: "bg-amber-50 text-amber-800 border-amber-200",
    Approved: "bg-emerald-50 text-emerald-800 border-emerald-200",
    Rejected: "bg-rose-50 text-rose-700 border-rose-200",
    Superseded: "bg-slate-50 text-slate-500 border-slate-200",
    Withdrawn: "bg-slate-100 text-slate-500 border-slate-200 italic",
    Reopened: "bg-amber-100 text-amber-900 border-amber-300",
};

export const SDLT_CATEGORIES = [
    "Residential_Standard", "Residential_Surcharge",
    "Non_Residential", "Corporate_Flat_Rate",
];
export const UNIT_TYPES = [
    "Detached", "Semi_Detached", "Terraced", "Flat", "Bungalow",
    "Commercial", "Other",
];
export const TENURES = [
    "Open_Market", "Affordable_Rent", "Shared_Ownership",
    "Social_Rent", "Build_To_Rent", "Private_Rent",
];
export const COST_CATEGORIES = [
    "Acquisition", "Construction", "Professional_Fees", "Statutory",
    "Finance", "Contingency", "Sales", "Other",
];
export const AUTO_SOURCES = [
    "Manual", "Percentage_Of_GDV", "Percentage_Of_Build_Cost",
    "Percentage_Of_Land", "SDLT_Engine", "Finance_Engine", "RLV_Engine",
];
export const FINANCE_TYPES = ["Debt", "Equity", "Mezzanine", "Grant"];
export const INTEREST_MODES = [
    "Simple_Monthly", "Compound_Monthly", "Rolled_Up", "Serviced",
];


// ----- primitive atoms -----------------------------------------------

export function StalePill({ stale }) {
    if (!stale) return null;
    return (
        <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 bg-amber-100 text-amber-800 border border-amber-200 rounded"
              data-testid="stale-pill">
            <AlertTriangle className="w-3 h-3" /> Stale
        </span>
    );
}

export function Kpi({ label, value, stale, testId }) {
    return (
        <div className="border border-slate-200 rounded p-4 bg-white"
             data-testid={testId}>
            <div className="text-xs text-slate-500 uppercase tracking-wide flex items-center gap-2">
                {label}
                <StalePill stale={stale} />
            </div>
            <div className="mt-1 text-2xl font-mono font-semibold text-slate-900">
                {value}
            </div>
        </div>
    );
}

export function SectionHeader({ title, right }) {
    return (
        <div className="flex items-center justify-between mb-3">
            <h2 className="font-heading text-lg font-bold text-slate-900">{title}</h2>
            <div>{right}</div>
        </div>
    );
}

export function Field({ label, disabled, children }) {
    return (
        <label className={`block text-sm ${disabled ? "opacity-70" : ""}`}>
            <span className="text-slate-600 text-xs uppercase tracking-wide flex items-center gap-1">
                {label} {disabled && <Lock className="w-3 h-3" />}
            </span>
            <div className="mt-1">{children}</div>
        </label>
    );
}
