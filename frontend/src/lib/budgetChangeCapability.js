/**
 * BCR capability helpers — Prompt 2.6-FE §R1.
 *
 * Mirrors lib/poCapability.js. The 6 budget_changes.* permissions
 * (from app/seed_rbac.py PERMISSION_CATALOGUE):
 *   - budget_changes.view
 *   - budget_changes.create   (also gates withdraw on backend)
 *   - budget_changes.edit     (PATCH on Draft only)
 *   - budget_changes.submit
 *   - budget_changes.approve  (also gates reject on backend)
 *   - budget_changes.apply
 */
import { hasPerm } from '@/lib/perms';

export function canViewBCR(me)     { return hasPerm(me, 'budget_changes.view'); }
export function canCreateBCR(me)   { return hasPerm(me, 'budget_changes.create'); }
export function canEditBCR(me)     { return hasPerm(me, 'budget_changes.edit'); }
export function canSubmitBCR(me)   { return hasPerm(me, 'budget_changes.submit'); }
export function canApproveBCR(me)  { return hasPerm(me, 'budget_changes.approve'); }
export function canRejectBCR(me)   { return hasPerm(me, 'budget_changes.approve'); }
// Withdraw is the creator's abort path; backend gates it on
// budget_changes.create + creator-only at the service layer.
export function canWithdrawBCR(me) { return hasPerm(me, 'budget_changes.create'); }
export function canApplyBCR(me)    { return hasPerm(me, 'budget_changes.apply'); }

/**
 * Creator-only check. The backend uses `bcr.created_by` for both
 * withdraw eligibility and the self-approval threshold guard.
 */
export function isBCRCreator(bcr, me) {
  if (!bcr?.created_by || !me?.id) return false;
  return String(bcr.created_by) === String(me.id);
}
