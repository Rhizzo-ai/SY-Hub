/**
 * UnbudgetedPill — B107 §3.1.
 *
 * Display-ONLY mirror of the server unbudgeted-floor gate
 * (`evaluate_unbudgeted_floor_gate`, budget_lines.py:856). The backend is
 * the single arbiter (B107 §0.3); this pill never blocks or decides — it
 * renders the same rule for the operator's eyes.
 *
 * Rule (all must hold for an un-cleared unbudgeted line):
 *   is_unbudgeted === true
 *   unbudgeted_cleared_at === null
 * then:
 *   committed_not_invoiced >= floor  → RED  "Sign-off required" (blocking)
 *   committed_not_invoiced <  floor  → AMBER "Unbudgeted"       (flagged)
 *
 * Cleared lines (unbudgeted_cleared_at != null) and budgeted lines render
 * nothing — they fall back to the normal variance heat-map.
 */
import React from 'react';

function isUnclearedUnbudgeted(row) {
  return !!row?.is_unbudgeted && !row?.unbudgeted_cleared_at;
}

export function isBlockingUnbudgeted(row, floor) {
  if (!isUnclearedUnbudgeted(row)) return false;
  const cni = Number(row.committed_not_invoiced ?? 0);
  const f = Number(floor ?? 0);
  return Number.isFinite(cni) && cni >= f;
}

export function isFlaggedUnbudgeted(row, floor) {
  if (!isUnclearedUnbudgeted(row)) return false;
  return !isBlockingUnbudgeted(row, floor);
}

const RED_CLS = 'bg-rose-50 text-rose-700 border-rose-200';
const AMBER_CLS = 'bg-amber-50 text-amber-700 border-amber-200';
const BASE =
  'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium';

export function UnbudgetedPill({ row, floor }) {
  if (!isUnclearedUnbudgeted(row)) return null;
  if (isBlockingUnbudgeted(row, floor)) {
    return (
      <span
        data-testid="unbudgeted-pill-blocking"
        className={`${BASE} ${RED_CLS}`}
        title="Unbudgeted line — committed spend has reached the sign-off floor; a director must clear it before a PO against it can be submitted."
      >
        <span aria-hidden>●</span>
        Sign-off required
      </span>
    );
  }
  return (
    <span
      data-testid="unbudgeted-pill-flagged"
      className={`${BASE} ${AMBER_CLS}`}
      title="Unbudgeted line — below the sign-off floor. Informational; does not block submit."
    >
      <span aria-hidden>●</span>
      Unbudgeted
    </span>
  );
}

export default UnbudgetedPill;
