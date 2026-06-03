/**
 * CIS / supplier-document label maps + date helpers — Chat 40 §R3 #16.
 *
 * Pure functions. No React, no fetches. Imported by SupplierForm,
 * SupplierList, CISTab, DocumentsTab, badges and tests.
 *
 * Why a separate module: the same label maps are needed in 5 callers;
 * inlining would drift. Backend enums are frozen (§R1), so these maps
 * are stable.
 */

// Backend enum (lowercase) → human label. `null`/'' renders as "—".
export const CIS_STATUS_LABEL = {
  gross: 'Gross',
  net_20: 'Net 20%',
  net_30: 'Net 30%',
  not_registered: 'Not registered',
};

export function labelCisStatus(value) {
  if (value === null || value === undefined || value === '') return '—';
  return CIS_STATUS_LABEL[value] ?? value;
}

// Subcontractor sub-type enum → human label.
export const CIS_SUBTYPE_LABEL = {
  Labour_Only: 'Labour only',
  Labour_And_Plant: 'Labour and plant',
  Supply_And_Fix: 'Supply and fix',
};

export function labelCisSubtype(value) {
  if (value === null || value === undefined || value === '') return '—';
  return CIS_SUBTYPE_LABEL[value] ?? value;
}

// CIS verification match_status (3 real values; backend frozen at §R1).
export const MATCH_STATUS_LABEL = {
  Gross: 'Gross',
  Net: 'Net',
  Unmatched: 'Unmatched',
};

// supplier.current_cis_status — same 3 + 'Unverified' + null.
export const CURRENT_CIS_STATUS_LABEL = {
  Gross: 'Gross',
  Net: 'Net',
  Unmatched: 'Unmatched',
  Unverified: 'Unverified',
};

export function labelCurrentCisStatus(value) {
  if (value === null || value === undefined) return 'Unverified';
  return CURRENT_CIS_STATUS_LABEL[value] ?? value;
}

// Supplier-document types — frozen at §R1.
export const DOC_TYPE_LABEL = {
  Public_Liability: 'Public liability',
  Employers_Liability: 'Employers liability',
  Professional_Indemnity: 'Professional indemnity',
  CIS_Certificate: 'CIS certificate',
  Accreditation: 'Accreditation',
  Insurance_Other: 'Insurance (other)',
  Other: 'Other',
};

export const DOC_TYPE_OPTIONS = [
  'Public_Liability', 'Employers_Liability', 'Professional_Indemnity',
  'CIS_Certificate', 'Accreditation', 'Insurance_Other', 'Other',
];

export function labelDocType(value) {
  if (value === null || value === undefined || value === '') return '—';
  return DOC_TYPE_LABEL[value] ?? value;
}

// ISO date (`2026-02-15`) → en-GB "15 Feb 2026". Returns "—" for nullish.
const DATE_FMT = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: 'short', year: 'numeric',
});

export function formatDate(iso) {
  if (!iso) return '—';
  // Backend stores ISO date strings. `new Date('2026-02-15')` parses as UTC,
  // which is what we want (no timezone slippage for date-only fields).
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return DATE_FMT.format(d);
}
