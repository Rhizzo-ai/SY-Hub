/**
 * Appraisal live-math helpers.
 *
 * The Prompt 2.2 spec distinguishes TWO layers of derived values on the
 * Appraisal page:
 *
 * ┌──────────────────────── LIVE (instant, decimal.js) ────────────────────────┐
 * │ Unit-row transforms:                                                       │
 * │   • gia_sqm                        — entered directly                      │
 * │   • gdv_per_sqft                   = price_per_unit / gia_sqft(gia_sqm)    │
 * │   • gdv_total_for_type             = price_per_unit * quantity             │
 * │   • build_cost_per_unit            — entered directly                      │
 * │   • build_cost_total_for_type      = build_cost_per_unit * quantity        │
 * │                                                                            │
 * │ These update on every keystroke. No round-trip required.                   │
 * └────────────────────────────────────────────────────────────────────────────┘
 *
 * ┌─────────────────────── STALE-UNTIL-SAVE (server owns) ─────────────────────┐
 * │ Everything else:                                                           │
 * │   • cost line effective_value (Percentage_Of_* lines)                      │
 * │   • SDLT_Engine / Finance_Engine / RLV_Engine auto lines                   │
 * │   • Header KPIs (total_gdv, total_cost, profit, margins)                   │
 * │   • RLV outputs                                                            │
 * │                                                                            │
 * │ These show a "STALE" pill while the user has unsaved edits. On save, the   │
 * │ server runs the canonical 8-step recompute pipeline and the pill clears.   │
 * └────────────────────────────────────────────────────────────────────────────┘
 *
 * Any money arithmetic must go through decimal.js — no native JS floats.
 */
import Decimal from "decimal.js";

// Configure once: 34-digit precision, ROUND_HALF_UP like the backend.
Decimal.set({ precision: 34, rounding: Decimal.ROUND_HALF_UP });

export const D = (x) => {
    if (x === null || x === undefined || x === "") return new Decimal(0);
    try { return new Decimal(x); } catch { return new Decimal(0); }
};

// 1 sqm = 10.7639 sqft (standard conversion).
const SQFT_PER_SQM = new Decimal("10.7639");

export function sqmToSqft(sqm) {
    return D(sqm).mul(SQFT_PER_SQM);
}

export function pricePerSqft(pricePerUnit, giaSqm) {
    const gia = D(giaSqm);
    if (gia.lte(0)) return null;
    const sqft = sqmToSqft(gia);
    if (sqft.lte(0)) return null;
    return D(pricePerUnit).div(sqft);
}

export function totalGdvForType(pricePerUnit, quantity) {
    return D(pricePerUnit).mul(D(quantity || 0));
}

export function totalBuildForType(buildCostPerUnit, quantity) {
    return D(buildCostPerUnit).mul(D(quantity || 0));
}

// Sum the LIVE per-row GDV across all unit rows in memory.
export function liveTotalGdv(rows) {
    return (rows || []).reduce(
        (acc, r) => acc.add(totalGdvForType(r.price_per_unit, r.quantity)),
        new Decimal(0),
    );
}

export function liveTotalBuild(rows) {
    return (rows || []).reduce(
        (acc, r) => acc.add(totalBuildForType(r.build_cost_per_unit, r.quantity)),
        new Decimal(0),
    );
}

// Money formatter — 2dp, thousands separators.
export function fmtGBP(x, { showSymbol = true } = {}) {
    if (x === null || x === undefined || x === "") return "—";
    const d = D(x);
    const formatted = new Intl.NumberFormat("en-GB", {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(Number(d.toFixed(2)));
    return showSymbol ? `£${formatted}` : formatted;
}

// Percent formatter with configurable precision.
export function fmtPct(x, { dp = 2 } = {}) {
    if (x === null || x === undefined || x === "") return "—";
    const d = D(x);
    return `${new Intl.NumberFormat("en-GB", {
        minimumFractionDigits: dp, maximumFractionDigits: dp,
    }).format(Number(d.toFixed(dp)))}%`;
}
