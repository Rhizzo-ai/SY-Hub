# NEW-CRIT-1 + H1 — Closing Summary

**Build Pack:** NEW-CRIT-1 + H1 — Role-Assignment Privilege-Escalation Fix
**Track:** Critical-fix plan, item 2 (after C3).
**Type:** SECURITY fix — backend only. Security-gate proof required.
**Scope:** Two files — `backend/app/routers/users.py` (single production file)
and `backend/tests/test_role_assignment_escalation.py` (new). No migration, no
new permission, no model change, no frontend.
**Backlog:** `docs/SY_Hub_Phase2_Backlog.md` left untouched (operator-only).

---

## 1. The vulnerability (confirmed)

`backend/app/routers/users.py` exposed two role-management endpoints, both
gated only by `require_permission("users.edit", ...)`:

- `POST /{user_id}/roles` (assign_role) — its **only** escalation guard blocked
  granting `super_admin`. Every other role (director, finance, …) could be
  granted by any `users.edit` holder. A non-director could therefore grant
  themselves or anyone else **director** (budget approval, appraisal sign-off,
  `budgets.clear_unbudgeted`) or **finance**. Privilege escalation.
- `DELETE /{user_id}/roles/{user_role_id}` (revoke_role) — **no** escalation
  guard at all. Any `users.edit` holder could strip any role from anyone,
  including removing the last super_admin → total administrative lockout.

## 2. The fix (three rules)

All layered INSIDE the handlers, in addition to the existing
`require_permission` dependencies (never replacing them). The superset rule
lives in one place — `_assert_can_manage_role` — called by both handlers.

1. **Superset on grant** — actor may grant a role only if they personally hold
   every permission the role grants. Self-maintaining (no role blocklist to
   keep updated); subsumes and replaces the old super_admin-only special-case.
   Empty-permission roles are grantable (they confer no power to escalate to).
2. **No self-assignment** — actor may never assign a role to their own account,
   regardless of permissions held. Flat block, fired before the superset check
   (cheaper, clearer message).
3. **Superset on revoke + last-super_admin protection** — same superset test on
   revoke, plus a 409 refusal to revoke the last remaining active super_admin
   in the tenant. `UserRole` carries no `tenant_id`, so the count joins through
   `User.tenant_id` (confirmed against the live model).

### Audit of blocked attempts

Every denied grant/revoke writes a `Permission_Change` audit row
(`kind = role_assignment_denied | role_revocation_denied`;
`rule = self_assignment | superset | last_super_admin`) and commits it before
raising, so the trail survives the rejected request. The audit write is
defensively wrapped — a logging failure can never swallow the 403/409.

### Untouched

The `require_permission` dependencies, the success-path audit, and all other
handler logic (scope inserts, serialise-return, commit) are unchanged. The
inline `compute_effective_permissions` import was promoted to the top-level
import block (no duplicate left). The revoke `role` lookup was moved up so the
checks can inspect it — single binding, no shadowing.

## 3. Live-code verification (before editing)

Read line-by-line against the pack's §1 quotes. Everything matched: endpoint
locations, the single super_admin-only guard, import blocks,
`compute_effective_permissions` / `UserPermissions.all_permissions`, the
`role_permissions`/`Permission` query pattern, `UserRole` having no
`tenant_id`, the `record_audit` signature, `"Active"/"Revoked"` string
statuses, and the `super_admin` role code. No discrepancies.

## 4. Tests — `backend/tests/test_role_assignment_escalation.py` (19)

Real Postgres via the running app (NOT mocked). Conventions mirror
`test_role_permissions_admin.py`. Each test asserts the HTTP status AND queries
`user_roles` / `audit_log` — the response is never trusted alone.

- Grant superset (6): missing-perm → 403; full-set → 201; finance blocked;
  super_admin blocked (via generic superset, not the old special-case);
  super_admin allowed for super_admin; zero-permission role allowed.
- Self-assignment (2): blocked even as super_admin; blocked for non-admin
  (self-check fires before superset — asserted via the message).
- Revoke superset (2): missing-perm → 403 (assignment stays Active);
  full-set → 204.
- Last super_admin (3): last one → 409; another exists → 204; tenant-scoped —
  a super_admin in a SECOND tenant does not count (proven end-to-end).
- Audit (3): blocked grant / blocked revoke write the denial rows with the
  correct `kind`/`rule`; successful grant still writes `role_assignment`.
- Regression guards (3): dependency still 403s without `users.edit`; re-revoke
  of an already-Revoked assignment is an idempotent 204; invalid entity_scope
  still 422 (proves placement is after the validation that must run first).

The suite leaves zero footprint (teardown removes custom roles, assignments,
target/other-tenant users, and synthetic tenants; the login-bearing editor user
is retained role-less and reused idempotently).

## 5. Security-gate evidence (live, operator-cleared)

```
health:       GET /api/health → 200
new tests:    19 passed (live Postgres)

regression:   tests/test_role_permissions_admin.py tests/test_auth_rbac.py tests/test_user_edit.py
              80 collected → 78 passed, 2 failed
              Both failures pre-existing & unrelated (super_admin perm count 143 vs hard-coded 136):
                - test_auth_rbac.py::TestAuthMe::test_me_super_admin_returns_87_permissions
                - test_auth_rbac.py::TestRoles::test_roles_returns_10_seeded_roles
              No new failures.

live echo:    POST /api/users/{id}/roles   role = director
              [users.edit-only actor]  HTTP 403  "Cannot grant role 'director': you do not hold all of its permissions."
              [super_admin actor    ]  HTTP 201  role_code=director

pod stability: pg_postmaster_start_time 2026-06-19 23:26:45Z — single continuous
               postmaster, no recycle during proof capture. Post-run state clean
               (roles=10, active super_admins restored to 2 — no lockout/drift).
```

## 6. Files changed

- `backend/app/routers/users.py` — three escalation guards + denial audit
  helper + import promotion (+162/−7).
- `backend/tests/test_role_assignment_escalation.py` — new, 19 tests.
- `CHANGELOG.md` — newest-first NEW-CRIT-1 + H1 entry.
- `docs/chat-summaries/NEW-CRIT-1-H1-closing.md` — this doc.

## 7. Flagged (not absorbed)

`app/deps.py::get_current_tenant_id` is hard-coded Phase-1 single-tenant — it
always resolves the default "SY Homes" tenant regardless of the authenticated
user (its own docstring notes Phase-2 will inspect the session/subdomain). The
last-super_admin count is therefore evaluated against the default tenant. The
fix's tenant-scoped join is correct and future-proof; the Phase-2 tenant
binding is recommended as a separate backlog entry for the operator.

## 8. Guardrails honoured

- Backend only — one production file, one new test file.
- No migration, no new permission, no model change, no frontend.
- Backlog (`docs/SY_Hub_Phase2_Backlog.md`) untouched.
- No scope expansion — the one adjacent issue (single-tenant
  `get_current_tenant_id`) was flagged, not absorbed.
- No git push by the agent — push via "Save to GitHub".
