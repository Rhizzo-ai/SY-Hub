// frontend/src/lib/aiCaptureCapability.js — Chat 19C §R1.4
//
// Single source of truth for AI capture UI gating. All checks read from
// `me` (current user) + the job status. No client-side hidden state;
// the backend RBAC + status-machine is the same shape mirrored here.
//
// Confidence warning threshold matches the §R4 ConfidencePill render rule.

const CONFIDENCE_WARN_THRESHOLD = 0.80;

function _hasAdmin(me) {
  if (!me) return false;
  return me.is_super_admin === true
    || (me.permissions || []).includes('actuals.admin');
}

export function canViewCaptures(me) {
  return _hasAdmin(me);
}

export function canPromote(me, job) {
  return _hasAdmin(me) && job?.status === 'Awaiting_Review';
}

export function canDiscard(me, job) {
  if (!_hasAdmin(me)) return false;
  // Backend allows discard from any non-terminal status (D46)
  return ['Queued', 'Extracting', 'Awaiting_Review'].includes(job?.status);
}

export function canRetry(me, job) {
  return _hasAdmin(me) && job?.status === 'Failed';
}

export function isLowConfidence(value) {
  if (value == null) return false; // null/undefined = no warning, em-dash render
  return value < CONFIDENCE_WARN_THRESHOLD;
}

// Chat 20 §R2.4 (B38) — cost dashboard gate. Separate from canViewCaptures;
// reveals operational pricing data and so is treated as finance-sensitive.
// Granted to super_admin, director, finance via seed_rbac (D3).
export function canViewCaptureCosts(me) {
  if (!me) return false;
  if (me.is_super_admin === true) return true;
  const perms = me.permissions || [];
  return perms.includes('ai_capture.view_costs');
}

export { CONFIDENCE_WARN_THRESHOLD };
