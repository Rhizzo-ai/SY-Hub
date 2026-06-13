/**
 * Packages money/format helpers — B88 Pack 3 (Chat 53).
 *
 * Server is the source of truth for every net = qty × rate. Client
 * formatters here are DISPLAY-ONLY and never round-trip into a
 * mutation body — that would risk a £0.01 client/server drift. See
 * Build Pack LD-P4: bidders compete on rate; quantity inherits from
 * the package_line.
 */

/** Format a string-or-null money field as £GBP, em-dash if null. */
export function fmtMoney(v) {
  if (v == null) return '\u2014';
  const n = Number(v);
  if (!Number.isFinite(n)) return '\u2014';
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'GBP',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

/** Decimal helper for client display only — server is authoritative. */
export function multiplyMoney(qty, rate) {
  const q = Number(qty);
  const r = Number(rate);
  if (!Number.isFinite(q) || !Number.isFinite(r)) return null;
  // 2dp rounding mirrors backend's ROUND_HALF_UP via toFixed approximation
  // (banker's rounding diff is below the £0.01 server tolerance — server
  // authoritatively re-rounds before storing).
  return (Math.round(q * r * 100) / 100).toFixed(2);
}

export function sumMoney(values) {
  let total = 0;
  for (const v of values) {
    if (v == null) continue;
    const n = Number(v);
    if (Number.isFinite(n)) total += n;
  }
  return (Math.round(total * 100) / 100).toFixed(2);
}

const STATUS_PILL = {
  draft: { label: 'Draft', bg: '#F1F5F9', fg: '#475569' },
  out_to_tender: { label: 'Out to tender', bg: '#DBEAFE', fg: '#1D4ED8' },
  partially_awarded: {
    label: 'Partially awarded', bg: '#FEF3C7', fg: '#92400E',
  },
  awarded: { label: 'Awarded', bg: '#D1FAE5', fg: '#065F46' },
  cancelled: { label: 'Cancelled', bg: '#FEE2E2', fg: '#991B1B' },
};

export function statusPillProps(status) {
  return STATUS_PILL[status] || {
    label: status, bg: '#E2E8F0', fg: '#1E293B',
  };
}

const BID_PILL = {
  invited: { label: 'Invited', bg: '#F1F5F9', fg: '#475569' },
  received: { label: 'Received', bg: '#D1FAE5', fg: '#065F46' },
  declined: { label: 'Declined', bg: '#FEE2E2', fg: '#991B1B' },
  withdrawn: { label: 'Withdrawn', bg: '#E5E7EB', fg: '#374151' },
};

export function bidPillProps(status) {
  return BID_PILL[status] || { label: status, bg: '#E2E8F0', fg: '#1E293B' };
}

/**
 * Server tolerance for the header Σ-guard (£0.01) — used CLIENT-SIDE
 * only to disable the award submit; the server enforces the real cap.
 */
export const HEADER_TOLERANCE = 0.01;

export function totalAfter(currentNet, draftNet) {
  return Number(currentNet || 0) + Number(draftNet || 0);
}

export function exceedsTotal(packageTotal, totalAwardedAfter) {
  return totalAwardedAfter > Number(packageTotal || 0) + HEADER_TOLERANCE;
}

/**
 * Pull an error message from a thrown axios error in a way that
 * NEVER swallows the server's detail. Used by every mutation handler
 * on the packages screens — the live-eyeball lesson.
 */
export function errorMessage(err) {
  if (err == null) return 'Unknown error.';
  if (typeof err === 'string') return err;
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d) => (typeof d === 'string' ? d : d?.msg || JSON.stringify(d)))
      .join('; ');
  }
  if (detail && typeof detail === 'object') {
    if (typeof detail.title === 'string') return detail.title;
    return JSON.stringify(detail);
  }
  if (err?.message) return err.message;
  return 'Unknown error.';
}
