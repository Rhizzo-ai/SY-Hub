/**
 * <ValuationStatusPill/> — Chat 48 (Build Pack 2.8-FE-ii §R4.2).
 *
 * Mirrors <SubcontractStatusPill/> (Chat 47) — same shape, same brand
 * tokens, same data-testid convention. Layout-stable: identical
 * padding/height for every status so list tables don't shift.
 *
 * Backend serialises status as the capitalised enum string
 * ('Draft' | 'Submitted' | 'Certified' | 'Rejected' — verified
 * backend/app/models/sc_valuations.py).
 *
 * Palette intent (matches Build Pack §R4.2 — Draft grey, Submitted
 * amber, Certified green, Rejected red):
 *   - Draft       → grey   (inert, pre-commit)
 *   - Submitted   → amber  (awaiting decision)
 *   - Certified   → green  (positive terminal)
 *   - Rejected    → red    (negative terminal)
 */
import React from 'react';

const STATUS_CLASSES = {
  Draft:     'bg-sy-grey-100 text-sy-grey-800',
  Submitted: 'bg-amber-100 text-amber-800',
  Certified: 'bg-green-100 text-green-800',
  Rejected:  'bg-red-100 text-red-800',
};

const STATUS_LABEL = {
  Draft: 'Draft',
  Submitted: 'Submitted',
  Certified: 'Certified',
  Rejected: 'Rejected',
};

export function ValuationStatusPill({ status, testid }) {
  const cls = STATUS_CLASSES[status] ?? 'bg-sy-grey-100 text-sy-grey-800';
  const label = STATUS_LABEL[status] ?? status ?? '\u2014';
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}
      data-testid={testid ?? `valuation-status-${status}`}
    >
      {label}
    </span>
  );
}

export default ValuationStatusPill;
