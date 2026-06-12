# Chat 52 — Build Pack B83 — Closing Summary

**Pack:** Build Pack B83 · Role & Permissions Admin · Backend + frontend
**Scope:** The platform's permission surface — a role × permission matrix with batch grant editing, custom-role lifecycle, a new `role_permission_revocations` table giving operator edits permanent precedence over the additive RBAC bootstrap seed, mandatory audit logging, and hard lock-out guards.
**Status:** COMPLETE through Gate 2 report. Gate 1 operator-verified file-by-file on `origin/main`. Two gates total (docs batched into Gate 2 per operator decision).

## What shipped

### Gate 1 — Backend (migration + seed precedence + endpoints + 34 tests)

- **Alembic migration `0046_rbac_operator_overrides`** — `role_permission_revocations` table: PK `(role_id, permission_id)`, FKs to roles/permissions ON DELETE CASCADE, `revoked_by_user_id` FK users SET NULL, `revoked_at` timestamptz default now(). No data step. Down drops the table.
- **Seed precedence (D1)** — `_seed_role_permissions` loads revoked pairs and never re-adds them. **Operator-approved deviation:** inspector `has_table` guard around the revocations query, because `app.bootstrap.run_migrations_and_seeds` is a staged dance that runs the filtered RBAC seed at rev **0017** on cold start — before 0046 exists. The unguarded §R3.1 query would have crashed every cold-start bootstrap at `seed_rbac_pre`. Guard is semantically identical on the warm path. Cold-start proven live: DB drop/recreate → bootstrap OK (`seed_rbac_pre result=ok`, `alembic=0046`, perms=136, roles=10).
- **`POST /api/roles/permissions-batch`** (`roles.admin`) — transactional all-or-nothing. Validation pass (404 unknown role; 403 super_admin target, detail "super_admin grants are locked and cannot be modified"; 422 unknown codes naming every code; 422 add∩remove overlap; 422 duplicate role_ids; ≤50 changes). Removes delete the grant AND upsert a revocation stamped with the acting user (removing an ungranted code is idempotent and still writes the revocation — pre-empts future seed grants). Adds insert the grant AND delete the revocation (re-grant heals the override). ONE `Permission_Change` audit row per role with sorted added/removed lists + `{role_code, added_count, removed_count, source: "b83_admin"}`. Response `{"updated": [RoleDetail…]}`.
- **`POST /api/roles`** — slug code generation (lowercase / `_` / strip / collapse / 50 max; empty → 422; collision → 409 no auto-suffix); priority default 40; **amended-D5 default grants**: every permission with `is_sensitive = false` AND `action NOT IN ('delete','admin','void')` — 89 of 136 at ship time — inserted atomically; audit Create.
- **`PATCH /api/roles/{id}`** — 409 "System role metadata is locked" for system roles; `code` immutable; `field_diff` audit Update.
- **`DELETE /api/roles/{id}`** — 409 "System roles cannot be deleted"; 409 "Role is assigned to N user(s); remove the assignments first" on ANY `user_roles` row (any status — mirrors FK `ondelete="RESTRICT"`); cascade cleans grants + revocations; audit Delete; 204.
- **Route order convention** — static paths declared before `/{role_id}`; §R5#33 pins the batch path against shadowing.
- **Tests** — `backend/tests/test_role_permissions_admin.py`, 34 functions named exactly per §R5. Warm 2nd-run suite: **1517 passed · 3 pre-existing xpassed · 0 failed** (junit 1520/0/0). Test-count reconciliation vs Chat 51 close (1483 + 3 xpassed = 1486 collected): +34 exactly, zero unexplained (verified by node-id diff against a `HEAD~1` worktree).
- **Live proofs** (Gate 1 report): batch revoke → audit row; **warm bootstrap re-seed → grant still absent + revocation persists** (the decisive D1 proof); re-grant heals; super_admin 403; director 403 `Missing permission(s): roles.admin`; Quantity Surveyor create → 89 grants == D5 SQL count; delete guard 409 → 204 after unassignment; bootstrap ordering citation; full cold-start drop/recreate proof.

### Gate 2 — Frontend + docs

- **`/admin/roles`** — `pages/admin/RolePermissionsAdmin.jsx`; nav "Role Permissions" beside Cost Codes (`roles.view`-gated). API client `lib/api/roles.js` — paths `/api/roles…`, NO `/v1` (URL-contract tests pin this). Components under `components/admin/`: `RoleReviewModal.jsx`, `RoleLifecycleDialogs.jsx` (create/rename/delete), `permissionConsequences.js`.
- **Matrix** — 136 permission rows grouped by resource (collapsible), 10+ role columns ordered by priority; sticky header AND sticky first column; brand teal `#0F6A7A` ticks, orange `#FC7827` sensitive accents, grey `#CECECE` locked super_admin column (always ticked, disabled, lock-icon tooltip "Super admin always has every permission"); orange sensitive dots; `title` hover tooltips + tap-to-expand descriptions; bespoke consequence lines for `budgets.view_sensitive`, `actuals.view_sensitive`, `roles.admin`, `users.admin`, `system_config.admin`, `cost_codes.delete`, `suppliers.delete`, `budget_changes.approve`, `budget_changes.apply`, `payment_notices.release`, `subcontract_valuations.certify`; generic line otherwise. Footnote: custom roles do not automatically receive future-build permissions.
- **Draft + save (D8/D9)** — local diff vs server truth; pending bar "N changes pending — Review & Save / Discard"; review modal with green adds / red removes / orange sensitive warnings / zero-permission checkbox confirm; ONE batch call; success reconciles from `updated`. **Every failure: toast + inline alert, draft preserved — no silent onError** (Chat 51 lesson, restated and enforced by test).
- **Lifecycle UI** — New-role dialog with D5 copy ("starts with all standard permissions ticked — sensitive and destructive permissions (delete / admin / void) start unticked"); custom-column kebab → Rename / Delete; 409 guard text rendered verbatim; system columns kebab-free. `roles.view` = read-only render (disabled ticks, no buttons/kebabs).
- **Mobile** — horizontal scroll with sticky permission column; dialogs full-screen on small viewports.
- **Frontend tests** — 15 component tests (`RolePermissionsAdmin.test.jsx`: groups, locked super_admin, pending bar + discard, sensitive + zero-permission review warnings, save-error visibility + draft preservation, create-dialog validation incl. server 409, read-only gating, forbidden state, kebab placement, tooltips) + 8 URL-contract tests (`roles.test.js`). Full frontend suite **825 passed / 96 suites / 0 failed**.
- **Docs** — this file + CHANGELOG entry (D-table + custom-roles note included). `docs/SY_Hub_Phase2_Backlog.md` untouched.

## Deviations from the Build Pack

1. **§R3.1 cold-start guard** (operator-approved at pre-flight, ruling #1) — `has_table` check around the revocations query; comment `# pre-0046 cold-start stage — table not yet migrated (B83)`.
2. **Gate-2 single backend run** (operator efficiency amendment) — zero backend production files changed at Gate 2, so the suite ran once; the two-run rule did not snap back.
3. **Head-sentinel test bump** 0045 → 0046 across 10 pre-existing migration tests (routine per their own docstrings).

## Known accepted behaviour (do not "fix")

- Custom roles do NOT automatically receive permissions added by future builds — `ROLE_PERMISSIONS` only references the 10 system role codes. UI carries the footnote.
- 3 pre-existing xpassed tests (audit export ×2, login-history ×1) remain xfail-marked from P1.R2 — untouched.

## Counts at close

`alembic head = 0046_rbac_operator_overrides` · permissions **136 (unchanged)** · roles **10** (+ operator-created custom roles) · backend warm suite 1517 passed / 3 xpassed / 0 failed · frontend 825 passed / 0 failed.

## Pointers for the next session

- Pod recovery unchanged: `bash /app/scripts/provision_postgres.sh` → `/root/.venv/bin/python -m app.bootstrap` (env-source first). Provisioning-script nits (SQL `create db` typo + on-restart.sh using system Python) logged operator-side — OUT of B83 scope, untouched.
- `role_permission_revocations` is the single source of operator grant-removal truth; any future role/permission tooling must respect it (remove = upsert revocation; add = delete revocation).
- User↔role assignment UI remains on the user admin surface (D4) — candidate for a future pack alongside concurrent-editor conflict handling (last-write-wins accepted v1).
