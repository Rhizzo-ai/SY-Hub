/**
 * Shared submitter-identity helper — Chat 26 §R7 Batch 1.
 *
 * The backend persists a self-approval guard (`SelfApprovalForbidden`)
 * that 403s when the user who submitted a PO tries to approve or reject
 * it. This helper mirrors that guard on the UI so the buttons hide /
 * disable before the request fires.
 *
 * Centralised here so R7.2 <POActionButtons/> and R7.3
 * <POApprovalPanel/> never drift apart.
 *
 * NB: Send-back is NOT subject to this rule — it IS the correction
 * path. The submitter MAY send back their own approved PO. Callers must
 * not use this helper to gate send-back.
 */

/**
 * @param {object} po — purchase order payload (must include `submitted_by`).
 * @param {object} me — current user object (must include `id`).
 * @returns {boolean} true when `me` submitted the PO.
 */
export function isSubmitter(po, me) {
  if (!po || !me) return false;
  if (!po.submitted_by || !me.id) return false;
  return String(po.submitted_by) === String(me.id);
}
