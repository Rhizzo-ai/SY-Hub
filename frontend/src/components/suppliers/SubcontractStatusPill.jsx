/**
 * <SubcontractStatusPill/> — Chat 47 (Build Pack 2.8-FE-i §R4.2).
 *
 * Mirrors <POStatusPill/> (chat 24 §R5) — same shape, same brand-token
 * palette, same data-testid convention. Layout-stable: identical
 * padding/height for every status so list tables don't shift.
 *
 * Backend serialises status as the capitalised enum string
 * ('Draft' | 'Active' | 'Completed' | 'Terminated' — see
 * backend/app/models/subcontracts.py).
 *
 * Palette intent (matches build-pack §R4.2 colour-by-status):
 *   - Draft       → grey   (inert, pre-commit)
 *   - Active      → teal   (live + committed — the SY teal accent)
 *   - Completed   → green  (positive terminal)
 *   - Terminated  → red    (negative terminal)
 */
import React from 'react';

const STATUS_CLASSES = {
  Draft:      'bg-sy-grey-100 text-sy-grey-800',
  Active:     'bg-sy-teal-100 text-sy-teal-800',
  Completed:  'bg-green-100 text-green-800',
  Terminated: 'bg-red-100 text-red-800',
};

const STATUS_LABEL = {
  Draft: 'Draft',
  Active: 'Active',
  Completed: 'Completed',
  Terminated: 'Terminated',
};

export function SubcontractStatusPill({ status, testid }) {
  const cls = STATUS_CLASSES[status] ?? 'bg-sy-grey-100 text-sy-grey-800';
  const label = STATUS_LABEL[status] ?? status ?? '—';
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}
      data-testid={testid ?? `subcontract-status-${status}`}
    >
      {label}
    </span>
  );
}

export default SubcontractStatusPill;
