/**
 * Budget capability helpers — Prompt 2.4B-i §R5 support.
 *
 * Captures the (status × permission) matrix for the budget lifecycle UI
 * so call sites stay declarative. Matrix is derived from the backend
 * permission decorators in `backend/app/routers/budgets.py` (verified
 * 2026-05-10), NOT from the Build Pack §R5.3 table (which used legacy
 * `budgets.create` for activate/lock — backend uses `budgets.edit`).
 *
 * Backend perm map:
 *   activate  → budgets.edit
 *   lock      → budgets.edit
 *   unlock    → budgets.admin
 *   close     → budgets.edit
 *   new-version → budgets.edit
 *
 * Status transitions allowed (from backend service layer):
 *   Activate  : Draft
 *   Lock      : Active
 *   Unlock    : Locked
 *   Close     : Active OR Locked
 *   New ver.  : Active OR Locked OR Closed
 *
 * The functions take an auth `me` shape ({ permissions: string[] }) and
 * a budget status string. Mobile-floor gating is layered on top at the
 * component level via `useIsDesktop()` — capability functions do NOT
 * know about device.
 */

function has(me, code) {
  if (!me || !Array.isArray(me.permissions)) return false;
  return me.permissions.includes(code);
}

export function canActivate(me, status) {
  return status === 'Draft' && has(me, 'budgets.edit');
}

export function canLock(me, status) {
  return status === 'Active' && has(me, 'budgets.edit');
}

export function canUnlock(me, status) {
  return status === 'Locked' && has(me, 'budgets.admin');
}

export function canClose(me, status) {
  return (status === 'Active' || status === 'Locked')
    && has(me, 'budgets.edit');
}

export function canCreateNewVersion(me, status) {
  return (status === 'Active' || status === 'Locked' || status === 'Closed')
    && has(me, 'budgets.edit');
}

export function canCreateFromAppraisal(me) {
  return has(me, 'budgets.create');
}

export function canRefreshAttention(me) {
  return has(me, 'budgets.admin');
}

// B107 §4 — director sign-off on an unbudgeted line. Backend gate:
// `budgets.clear_unbudgeted` (director + super_admin; finance default-OFF).
export function canClearUnbudgeted(me) {
  return has(me, 'budgets.clear_unbudgeted');
}

export function canEditLines(me, status) {
  // Line edits allowed on Draft + Active. Locked/Closed/Superseded are read-only.
  return (status === 'Draft' || status === 'Active') && has(me, 'budgets.edit');
}

// ──────────────────────────────────────────────────────────────────────
// §R6.1 editability matrix helpers — status-only (no perm/device).
// Combine with canEditLines() at the call-site for the full gate.
// ──────────────────────────────────────────────────────────────────────

export function isBudgetEditable(status) {
  return status === 'Draft' || status === 'Active';
}

export function isLineCreatable(status) {
  return status === 'Draft';
}

export function isCostCodeMutable(status) {
  return status === 'Draft';
}

// B88 Pack 2 — Tier 1 (Full) vs Tier 2 (Construction) scope.
// Mirrors backend `cost_code_scope.caller_scope`. Super-admin gets full
// by RBAC wildcard so `permissions.includes` works for them too.
export function getBudgetScope(me) {
  if (!me || !Array.isArray(me.permissions)) return 'construction';
  return me.permissions.includes('budgets.view_sensitive')
    ? 'full' : 'construction';
}

export function canSeeFullBudget(me) {
  return getBudgetScope(me) === 'full';
}
