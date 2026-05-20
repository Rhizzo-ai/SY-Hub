/**
 * <POStatusPill/> — Chat 24 §R5 (Build Pack §5.4 — first brand-token use).
 *
 * Renders the canonical PO status with a colour that reflects lifecycle
 * stage. Uses the SY brand tokens (teal / orange / grey) plus standard
 * red for rejected/voided. Layout-stable — same padding/height for every
 * status so the list table doesn't shift.
 */
import React from 'react';

const STATUS_CLASSES = {
  draft:                 'bg-sy-grey-100 text-sy-grey-800',
  submitted:             'bg-sy-orange-100 text-sy-orange-800',
  approved:              'bg-sy-teal-100 text-sy-teal-800',
  issued:                'bg-sy-teal-100 text-sy-teal-800',
  partially_receipted:   'bg-sy-orange-100 text-sy-orange-800',
  receipted:             'bg-sy-teal-100 text-sy-teal-800',
  closed:                'bg-sy-grey-200 text-sy-grey-700',
  voided:                'bg-red-100 text-red-800',
  rejected:              'bg-red-100 text-red-800',
};

const STATUS_LABEL = {
  draft: 'Draft',
  submitted: 'Submitted',
  approved: 'Approved',
  issued: 'Issued',
  partially_receipted: 'Partially receipted',
  receipted: 'Receipted',
  closed: 'Closed',
  voided: 'Voided',
  rejected: 'Rejected',
};

export function POStatusPill({ status, testid }) {
  const cls = STATUS_CLASSES[status] ?? 'bg-sy-grey-100 text-sy-grey-800';
  const label = STATUS_LABEL[status] ?? status;
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}
      data-testid={testid ?? `po-status-${status}`}
    >
      {label}
    </span>
  );
}

export default POStatusPill;
