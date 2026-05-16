import { format as tzFormat, toZonedTime } from "date-fns-tz";
import { parseISO, differenceInCalendarDays, isValid } from "date-fns";

export const LONDON_TZ = "Europe/London";

// ---- Date/time ----

/** Parse an ISO string or Date to a London-zoned Date, or null. */
function toLondon(value) {
    if (value == null || value === "") return null;
    const d = value instanceof Date ? value : parseISO(String(value));
    if (!isValid(d)) return null;
    return toZonedTime(d, LONDON_TZ);
}

/** "19 Apr 2026" */
export function formatDate(value) {
    const d = toLondon(value);
    if (!d) return "—";
    return tzFormat(d, "dd MMM yyyy", { timeZone: LONDON_TZ });
}

/** "19/04/26" — short form for tables */
export function formatDateShort(value) {
    const d = toLondon(value);
    if (!d) return "—";
    return tzFormat(d, "dd/MM/yy", { timeZone: LONDON_TZ });
}

/** "19 Apr 2026, 14:30" — 24h */
export function formatDateTime(value) {
    const d = toLondon(value);
    if (!d) return "—";
    return tzFormat(d, "dd MMM yyyy, HH:mm", { timeZone: LONDON_TZ });
}

/** Days until the given ISO date (civil date, no tz math). Negative = past. */
export function daysUntil(value) {
    if (!value) return null;
    const d = value instanceof Date ? value : parseISO(String(value));
    if (!isValid(d)) return null;
    const today = toZonedTime(new Date(), LONDON_TZ);
    today.setHours(0, 0, 0, 0);
    const target = toZonedTime(d, LONDON_TZ);
    target.setHours(0, 0, 0, 0);
    return differenceInCalendarDays(target, today);
}

// ---- Money & percentages ----

const _gbp = new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency: "GBP",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
});

export function formatMoney(value, currency = "GBP") {
    if (value == null || value === "") return "—";
    const n = typeof value === "number" ? value : parseFloat(value);
    if (!Number.isFinite(n)) return "—";
    if (currency === "GBP") return _gbp.format(n);
    return new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(n);
}

// Chat 19B §R2 — Actuals UI alias. Equivalent to `formatMoney(v, "GBP")`.
// Returns "—" for null / undefined / empty string (D26 sensitive-field
// pattern: a single render path covers both gated and ungated responses).
export const fmtGBP = (value) => formatMoney(value, "GBP");

export function formatPercent(value) {
    if (value == null || value === "") return "—";
    const n = typeof value === "number" ? value : parseFloat(value);
    if (!Number.isFinite(n)) return "—";
    return `${n.toFixed(1)}%`;
}

// ---- Domain-specific ----

export function formatCompaniesHouse(value) {
    if (!value) return "—";
    return String(value).toUpperCase();
}

export function formatVATNumber(value) {
    if (!value) return "—";
    const digits = String(value).replace(/\D/g, "");
    // UK VAT: GB + 9 or 12 digits; format as GB 123 4567 89 when 9 digits.
    if (digits.length === 9) {
        return `GB ${digits.slice(0, 3)} ${digits.slice(3, 7)} ${digits.slice(7)}`;
    }
    return `GB ${digits}`;
}

export function formatYearEnd(value) {
    if (!value) return "—";
    // Input: MM-DD → "31 Mar"
    const [m, d] = String(value).split("-");
    const months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    const mi = parseInt(m, 10) - 1;
    if (mi < 0 || mi > 11 || !d) return value;
    return `${parseInt(d, 10)} ${months[mi]}`;
}

export function displayEnum(value) {
    if (!value) return "—";
    return String(value).replace(/_/g, " ");
}
