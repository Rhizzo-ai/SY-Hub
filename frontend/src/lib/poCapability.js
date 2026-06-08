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
// Chat 41 §R-eyeball-2 (Prompt 2.7-FE-revision) — hard delete.
export function canDeleteSupplier(me) { return hasPerm(me, 'suppliers.delete'); }


// ─── Trades (Chat 41 §R7.2 — Build Pack 2.7-FE-revision) ─────────────
export function canViewTrades(me)   { return hasPerm(me, 'trades.view'); }
export function canCreateTrades(me) { return hasPerm(me, 'trades.create'); }


// ─── CIS (Chat 40 §R3 #3) ────────────────────────────────────────────
export function canViewCIS(me)          { return hasPerm(me, 'cis.view'); }
export function canViewSensitiveCIS(me) { return hasPerm(me, 'cis.view_sensitive'); }
export function canVerifyCIS(me)        { return hasPerm(me, 'cis.verify'); }


// ─── Supplier documents (Chat 40 §R3 #3) ─────────────────────────────
export function canViewDocs(me)          { return hasPerm(me, 'supplier_documents.view'); }
export function canViewSensitiveDocs(me) { return hasPerm(me, 'supplier_documents.view_sensitive'); }
export function canCreateDocs(me)        { return hasPerm(me, 'supplier_documents.create'); }
export function canEditDocs(me)          { return hasPerm(me, 'supplier_documents.edit'); }
export function canArchiveDocs(me)       { return hasPerm(me, 'supplier_documents.archive'); }


// ─── Document folders (Chat 46, Build Pack 2.7-DOCS-FE §R2.0) ────────
// Folder VIEW follows `canViewDocs` (the backend gates folder reads on
// the owner-surface view perm — supplier_documents.view for suppliers).
// Folder WRITES (create / rename / archive / unarchive) and MOVES use
// the platform-wide `documents.*` actions.
export function canCreateFolder(me) { return hasPerm(me, 'documents.create'); }
export function canEditFolder(me)   { return hasPerm(me, 'documents.edit'); }
export function canMoveDocs(me)     { return hasPerm(me, 'documents.move'); }


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


// ─── Subcontracts (Chat 47, Build Pack 2.8-FE-i §R2.0) ───────────────
//
// One helper per perm + per action. The action helpers map to the
// backend's actual perm gates on origin/main, which differ from the
// Build Pack §R0.3 documentation in one place — see FLAG 1b in the
// Chat-47 closing notes / CHANGELOG §2.8-FE-i:
//
//   POST /v1/subcontracts/{id}/activate   → subcontracts.approve
//   POST /v1/subcontracts/{id}/complete   → subcontracts.edit  ← Build
//                                             Pack §R0.3 said `approve`;
//                                             actual router uses `edit`.
//   POST /v1/subcontracts/{id}/terminate  → subcontracts.approve
//
// `canCompleteSubcontract` therefore accepts `edit OR approve` so the
// UI doesn't hide a button the backend would accept. A user with only
// `subcontracts.edit` (a director-tier without approve, say) can still
// drive a subcontract through Activate→Complete because Activate
// requires `approve` upstream — in practice the same role usually
// holds both.
export function canViewSubcontracts(me)      { return hasPerm(me, 'subcontracts.view'); }
export function canViewSubcontractSums(me)   { return hasPerm(me, 'subcontracts.view_sensitive'); }
export function canCreateSubcontract(me)     { return hasPerm(me, 'subcontracts.create'); }
export function canEditSubcontract(me)       { return hasPerm(me, 'subcontracts.edit'); }
export function canActivateSubcontract(me)   { return hasPerm(me, 'subcontracts.approve'); }
export function canCompleteSubcontract(me) {
  return hasPerm(me, 'subcontracts.edit') || hasPerm(me, 'subcontracts.approve');
}
export function canTerminateSubcontract(me)  { return hasPerm(me, 'subcontracts.approve'); }


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



// ─── Subcontract status → next-actions (Build Pack §R4.3) ────────────
// Source of truth for which lifecycle buttons render on the subcontract
// detail panel. Statuses use the backend's capitalised enum
// ('Draft' | 'Active' | 'Completed' | 'Terminated'); terminal statuses
// return [].
export function nextActionsForSubcontractStatus(status) {
  switch (status) {
    case 'Draft':       return ['activate', 'terminate'];
    case 'Active':      return ['complete', 'terminate'];
    case 'Completed':   return [];
    case 'Terminated':  return [];
    default:            return [];
  }
}

export const SUBCONTRACT_TERMINAL_STATUSES = new Set(['Completed', 'Terminated']);
