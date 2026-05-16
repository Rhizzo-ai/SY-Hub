/**
 * Capability helpers for the Actuals module (Chat 19B §R1.4).
 *
 * Inputs:
 *   - `actual` — an Actual object (may be null for "no-actual" gates).
 *   - `me` — { permissions: string[], is_super_admin: boolean }.
 *   - `isDesktop` — boolean from useIsDesktop().
 *
 * Returns booleans. All gates combine state-machine truth + permission
 * truth. Mobile rules (Q2):
 *   - Allowed on mobile: view, create.
 *   - Desktop-only: post, mark-paid, void, dispute, undispute,
 *     release-retention, edit, delete, attach, delete-attachment.
 *
 * Pure functions, no React. Same pattern as `budgetCapability.js`.
 */

const hasPerm = (me, perm) =>
  !!me?.is_super_admin ||
  (Array.isArray(me?.permissions) && me.permissions.includes(perm));

export function canViewActuals(me) {
  return hasPerm(me, 'actuals.view');
}

export function canCreateActual(me, _isDesktop) {
  // Mobile create is allowed (Q2 — routes to a dedicated /actuals/new page
  // on mobile; opens in a Sheet on desktop).
  return hasPerm(me, 'actuals.create');
}

export function canEditDraft(actual, me, isDesktop) {
  if (!isDesktop) return false;
  if (!actual || actual.status !== 'Draft') return false;
  return hasPerm(me, 'actuals.edit');
}

export function canDeleteDraft(actual, me, isDesktop) {
  if (!isDesktop) return false;
  if (!actual || actual.status !== 'Draft') return false;
  return hasPerm(me, 'actuals.edit');
}

export function canPostDraft(actual, me, isDesktop) {
  if (!isDesktop) return false;
  if (!actual || actual.status !== 'Draft') return false;
  // Verified against live `app/routers/actuals.py::post_actual` 2026-05-16:
  // POST /actuals/:id/post requires `actuals.edit` (the router docstring
  // mentions `actuals.post` but that label is documentation-only — the
  // `require_permission(...)` decorator uses `actuals.edit`). PM users
  // hold `actuals.edit` without `actuals.approve` and MUST see the Post
  // button.
  return hasPerm(me, 'actuals.edit');
}

export function canMarkPaid(actual, me, isDesktop) {
  if (!isDesktop) return false;
  if (!actual || actual.status !== 'Posted') return false;
  return hasPerm(me, 'actuals.approve');
}

export function canVoid(actual, me, isDesktop) {
  if (!isDesktop) return false;
  if (!actual) return false;
  if (actual.status === 'Void') return false;
  // Paid actuals can't be voided — service requires a credit note instead.
  if (actual.status === 'Paid') return false;
  return hasPerm(me, 'actuals.approve');
}

export function canDispute(actual, me, isDesktop) {
  if (!isDesktop) return false;
  if (!actual || actual.status !== 'Posted') return false;
  return hasPerm(me, 'actuals.edit');
}

export function canUndispute(actual, me, isDesktop) {
  if (!isDesktop) return false;
  if (!actual || actual.status !== 'Disputed') return false;
  return hasPerm(me, 'actuals.edit');
}

export function canReleaseRetention(actual, me, isDesktop) {
  if (!isDesktop) return false;
  if (!actual) return false;
  if (!['Posted', 'Paid'].includes(actual.status)) return false;
  if (actual.retention_released) return false;
  return hasPerm(me, 'actuals.approve');
}

export function canAttach(actual, me, isDesktop) {
  if (!isDesktop) return false;
  if (!actual) return false;
  if (actual.status === 'Void') return false;
  return hasPerm(me, 'actuals.edit');
}

export function canDeleteAttachment(actual, me, isDesktop) {
  return canAttach(actual, me, isDesktop);
}

export function canViewSensitive(me) {
  return hasPerm(me, 'actuals.view_sensitive');
}

export function canViewPaymentsPage(me) {
  // Louise's page — actuals.view + the "broad" scope. For now any user with
  // actuals.view can see it; a stricter perm may land later (B31 territory).
  return hasPerm(me, 'actuals.view');
}
