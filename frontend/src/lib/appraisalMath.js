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
 * │   • Header KPIs (gdv_total, total_cost, profit, margins)                   │
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


// =========================================================================
// Prompt 2.3 Checkpoint 3 — governance helpers
// =========================================================================

/**
 * Whole-pound currency formatter (Intl.NumberFormat en-GB).
 * Use for KPIs, headers, comparator cells. Accepts Decimal | number | string.
 * `decimals=2` for line-item details only.
 */
export function formatMoney(value, { decimals = 0 } = {}) {
    if (value === null || value === undefined || value === "") return "—";
    const d = D(value);
    return new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: "GBP",
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    }).format(Number(d.toFixed(decimals)));
}

/**
 * Decimal-only delta computation: compare[field] − base[field].
 * Returns a Decimal (zero if either side is null/undefined).
 */
export function computeScenarioDelta(base, compare, field) {
    const b = base?.[field];
    const c = compare?.[field];
    if (b === null || b === undefined) return new Decimal(0);
    if (c === null || c === undefined) return new Decimal(0);
    return D(c).minus(D(b));
}

/**
 * Format a Decimal delta with sign + colour class.
 * @param d Decimal
 * @param opts.currency boolean — render as money (default true)
 * @param opts.percent boolean — render as percent (overrides currency)
 * @param opts.dp number — decimal places (defaults: 0 for currency, 2 for percent)
 * @param opts.favourable "positive" | "negative" — direction in which +Δ is good
 */
export function formatDelta(d, opts = {}) {
    const {
        currency = true,
        percent = false,
        dp = percent ? 2 : 0,
        favourable = "positive",
    } = opts;
    const dec = d instanceof Decimal ? d : D(d);
    const isZero = dec.eq(0);
    const isPositive = dec.gt(0);
    const sign = isZero ? "" : (isPositive ? "+" : "−");
    const abs = dec.abs();

    let body;
    if (percent) {
        body = `${new Intl.NumberFormat("en-GB", {
            minimumFractionDigits: dp, maximumFractionDigits: dp,
        }).format(Number(abs.toFixed(dp)))}%`;
    } else if (currency) {
        body = new Intl.NumberFormat("en-GB", {
            style: "currency", currency: "GBP",
            minimumFractionDigits: dp, maximumFractionDigits: dp,
        }).format(Number(abs.toFixed(dp)));
    } else {
        body = new Intl.NumberFormat("en-GB", {
            minimumFractionDigits: dp, maximumFractionDigits: dp,
        }).format(Number(abs.toFixed(dp)));
    }

    let className = "text-slate-400";
    if (!isZero) {
        const isFavourable =
            favourable === "positive" ? isPositive : !isPositive;
        className = isFavourable
            ? "text-emerald-700"
            : "text-rose-700";
    }
    return { text: `${sign}${body}`, className, isZero };
}
