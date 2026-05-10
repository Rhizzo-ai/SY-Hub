/**
 * Permission helper (Build Pack v2 §R2.2).
 *
 * Backend stores permissions as a flat string list on the user object
 * (e.g. ['budgets.read', 'budgets.edit', 'budgets.admin']).
 *
 * Budgets convention from 2.4A:
 *   - budgets.read           list + read
 *   - budgets.create         POST /budgets/from-appraisal
 *   - budgets.edit           lifecycle (activate/lock/close/new-version),
 *                            line edits, line reorder, item CRUD
 *   - budgets.admin          unlock, refresh-attention, lock-override
 *   - budgets.view_sensitive sensitive fields visible (FTC method/value,
 *                            internal notes)
 *
 * NB: The Build Pack §R2.2 listed `budgets.create` for line edits — that
 * was a doc error. The shipping backend gates line edits on `budgets.edit`
 * (see backend/app/routers/budgets.py @router.patch '/budget-lines/...').
 */
export function hasPerm(user, perm) {
  if (!user) return false;
  if (!Array.isArray(user.permissions)) return false;
  return user.permissions.includes(perm);
}

export function hasAnyPerm(user, perms) {
  return perms.some((p) => hasPerm(user, p));
}
