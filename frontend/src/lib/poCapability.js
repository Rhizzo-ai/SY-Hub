/**
 * Suppliers / POs / Number Prefixes capability helpers — Chat 24 §R5.
 *
 * Same convention as lib/budgetCapability.js / lib/actualCapability.js:
 *   - `canViewSensitive*` — controls whether banking / line rates and
 *     totals render or fall back to <SensitiveValue/>.
 *   - `can*` — controls whether action buttons render at all.
 *
 * Centralising the perm map here means components don't sprinkle
 * `hasPerm(me, 'pos.foo')` directly; future renames only touch this file.
 */
import { hasPerm } from '@/lib/perms';


// ─── Suppliers ───────────────────────────────────────────────────────
export function canViewSuppliers(me) { return hasPerm(me, 'suppliers.view'); }
export function canViewSensitiveSupplier(me) {
  return hasPerm(me, 'suppliers.view_sensitive');
}
export function canCreateSupplier(me) { return hasPerm(me, 'suppliers.create'); }
export function canEditSupplier(me)   { return hasPerm(me, 'suppliers.edit'); }
export function canArchiveSupplier(me){ return hasPerm(me, 'suppliers.archive'); }


// ─── Purchase Orders ─────────────────────────────────────────────────
export function canViewPOs(me)                { return hasPerm(me, 'pos.view'); }
export function canViewSensitivePO(me)        { return hasPerm(me, 'pos.view_sensitive'); }
export function canCreatePO(me)               { return hasPerm(me, 'pos.create'); }
export function canEditPO(me)                 { return hasPerm(me, 'pos.edit'); }
export function canEditIssuedPO(me)           { return hasPerm(me, 'pos.edit_issued'); }
export function canDeletePO(me)               { return hasPerm(me, 'pos.delete'); }
export function canSubmitPO(me)               { return hasPerm(me, 'pos.create') || hasPerm(me, 'pos.edit'); }
export function canIssuePO(me)                { return hasPerm(me, 'pos.issue'); }
export function canApprovePO(me)              { return hasPerm(me, 'pos.approve'); }
export function canRejectPO(me)               { return hasPerm(me, 'pos.approve'); }
export function canVoidPO(me)                 { return hasPerm(me, 'pos.void'); }
export function canClosePO(me)                { return hasPerm(me, 'pos.close'); }
export function canReceiptPO(me)              { return hasPerm(me, 'pos.receipt'); }
export function canEditReceipt(me)            { return hasPerm(me, 'pos.edit_issued'); }


// ─── Number prefixes ─────────────────────────────────────────────────
//   - View: anyone who can view POs (read-only of the numbering surface).
//   - Edit: suppliers.edit OR pos.edit (per backend authz in R1 router).
export function canViewPrefixes(me) {
  return canViewPOs(me) || canViewSuppliers(me);
}
export function canEditPrefixes(me) {
  return canEditPO(me) || canEditSupplier(me);
}


// ─── Status → next-action allow-list ─────────────────────────────────
// Drives which lifecycle buttons render on PurchaseOrderDetail; keeps
// the per-status decision in one place rather than spread across components.
export function nextActionsForStatus(status) {
  switch (status) {
    case 'draft':                  return ['edit', 'submit', 'delete'];
    case 'submitted':              return ['approve', 'reject'];
    case 'issued':                 return ['receipt', 'void', 'edit_issued'];
    case 'partially_receipted':    return ['receipt', 'edit_issued'];
    case 'receipted':              return ['close', 'edit_issued'];
    case 'closed':                 return [];
    case 'voided':                 return [];
    case 'rejected':               return ['edit'];
    default:                       return [];
  }
}
