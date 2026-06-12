/**
 * Sensitive-permission consequence lines — B83 §R4 (D8/D10).
 *
 * Bespoke plain-English consequence lines for the highest-impact
 * permissions; every other `is_sensitive` permission falls back to the
 * generic line. Shown in row tooltips and highlighted in the review
 * modal before a batch save commits.
 */

export const GENERIC_SENSITIVE_LINE =
  'This is a sensitive permission — grant deliberately.';

export const CONSEQUENCE_LINES = {
  'budgets.view_sensitive':
    'Grants full-budget money visibility (Tier 1).',
  'actuals.view_sensitive':
    'Grants full visibility of actual cost values across projects.',
  'roles.admin':
    'Grants control of this permission matrix — holders can change any role\u2019s powers.',
  'users.admin':
    'Grants full user administration, including account lifecycle and role assignment.',
  'system_config.admin':
    'Grants control of platform-wide system configuration.',
  'cost_codes.delete':
    'Allows permanent deletion of cost codes (super_admin-only by operator default).',
  'suppliers.delete':
    'Allows permanent deletion of supplier records and their history.',
  'budget_changes.approve':
    'Allows approving budget change requests — a money-authorising act.',
  'budget_changes.apply':
    'Allows applying approved budget changes to live budget lines.',
  'payment_notices.release':
    'Allows releasing subcontract retention payments — a money-authorising act.',
  'subcontract_valuations.certify':
    'Allows certifying subcontractor valuations — posts real-money actuals.',
};

export function consequenceFor(permission) {
  if (!permission?.is_sensitive) return null;
  return CONSEQUENCE_LINES[permission.code] || GENERIC_SENSITIVE_LINE;
}
