/**
 * Permission helper (Build Pack v2 §R2.2).
 *
 * Backend stores permissions as a flat string list on the user object.
 *
 * Budgets convention from 2.4A (verified against `permissions.code` in
 * the live DB, 2026-05-10):
 *   - budgets.view             list + read       (BPv2 called this `read`)
 *   - budgets.create           POST /budgets/from-appraisal
 *   - budgets.approve          (legacy / approval gate, not used here)
 *   - budgets.edit             lifecycle (activate/lock/close/new-version),
 *                              line edits, line reorder, item CRUD
 *   - budgets.admin            unlock, refresh-attention, lock-override
 *   - budgets.view_sensitive   sensitive fields visible (FTC method/value,
 *                              actuals, CNI, FFC, variance, internal notes)
 *
 * NBs:
 *   1. Build Pack §R2.2 listed `budgets.create` for line edits — doc error.
 *      Line edits are gated on `budgets.edit` (see backend
 *      app/routers/budgets.py @router.patch '/budget-lines/...').
 *   2. Build Pack §R3.1 used `budgets.read` as the list-read perm — that
 *      perm does not exist. Use `budgets.view`.
 */
export function hasPerm(user, perm) {
  if (!user) return false;
  if (!Array.isArray(user.permissions)) return false;
  return user.permissions.includes(perm);
}

export function hasAnyPerm(user, perms) {
  return perms.some((p) => hasPerm(user, p));
}
