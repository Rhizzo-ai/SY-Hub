# SY Homes Operations Platform — Product Requirements Document

## Original Problem Statement
SY Homes is a UK property development company. This platform replaces spreadsheets, WhatsApp, and Buildertrend with a single system of record for development and construction operations. Phase 1 scope: 77 tables across 10 modules delivered via 25 sequential build prompts.

## Stack (locked)
- **Database**: PostgreSQL 15 (`syhomes` DB, user `syhomes`). Managed via `pg_ctlcluster` + idempotent bootstrap in `/root/.emergent/on-restart.sh`.
- **Schema migrations**: Alembic — `/app/backend/alembic/`.
- **Backend**: FastAPI + SQLAlchemy 2.x + psycopg3 + APScheduler
- **Auth**: argon2-cffi (argon2id) + pyotp (TOTP) + qrcode + pyjwt (HS256) + cryptography (Fernet)
- **Frontend**: React 19 + React Router 7 + Tailwind + shadcn/Radix + RHF + Zod + date-fns-tz
- **Fonts**: Chivo (headings), IBM Plex Sans (body), IBM Plex Mono (numbers)

## Conventions (applied globally)
- Tables plural snake_case; fields snake_case; FKs `_id`; timestamps `_at` UTC; dates `_date`; enums `PascalCase_With_Underscores`.
- UUID v4 IDs; `DECIMAL(14,2)` money; `DECIMAL(6,3)` percentages 0–100.
- FKs default `ON DELETE RESTRICT`; junctions `CASCADE`; soft-archive via status field.
- `created_at` + `updated_at` + `tenant_id` on every table; `updated_at` auto-refresh via PG trigger `set_updated_at()`.
- **All schema changes go through Alembic migrations.**
- **Authentication enforced at FastAPI dependency level** — 403 fires before handler logic.

## Architecture
```
/app/backend/
├── server.py                        # lifespan: alembic upgrade head → seed → seed_rbac → start schedulers
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 0001_initial_entities.py
│       └── 0002_users_rbac.py       # users + RBAC + entities.created_by_user_id
├── .env                             # DATABASE_URL, JWT_SECRET, MFA_ENCRYPTION_KEY, BOOTSTRAP_ADMIN_*
├── scripts/
│   └── seed_test_users.py           # idempotent test fixtures
├── tests/
│   ├── conftest.py
│   ├── test_entities_api.py         # Prompt 1.1 (updated for auth)
│   ├── test_insurance_alerts.py
│   └── test_auth_rbac.py            # Prompt 1.2 (32 tests)
└── app/
    ├── db.py
    ├── deps.py                      # name-based tenant lookup (legacy; prefer auth-derived)
    ├── auth/
    │   ├── passwords.py             # argon2id hash/verify/history
    │   ├── mfa.py                   # TOTP + Fernet + backup codes
    │   ├── tokens.py                # JWT HS256 (4h in 1.2)
    │   ├── permissions.py           # compute_effective_permissions + UserPermissions dataclass
    │   └── deps.py                  # get_current_user + require_permission(*codes) factory
    ├── models/{tenant,entity,user,rbac}.py
    ├── schemas/entity.py
    ├── routers/
    │   ├── auth.py                  # /login, /mfa/*, /password/change, /logout, /me
    │   ├── users.py                 # CRUD + unlock + scrub_pii + role assignment
    │   ├── roles.py                 # /roles (list+detail) + /permissions (list)
    │   ├── entities.py              # retrofitted with permission deps + scope filter + sensitive stripping
    │   └── meta.py
    ├── seed.py                      # tenant + entity seed
    ├── seed_rbac.py                 # permissions (~90) + roles (10) + role-permissions mapping + bootstrap admin
    └── jobs/
        ├── insurance_alerts.py
        └── role_expiry.py           # hourly: Active user_roles → Expired when expires_at passed

/app/frontend/src/
├── context/AuthContext.jsx
├── lib/{api,format}.js
├── components/
│   ├── AppShell.jsx                 # sidebar with current user + logout; Users/Roles/Perms enabled
│   ├── user/RoleAssignmentModal.jsx
│   └── entity/{EntityForm,InsuranceBadge,EntityStatusBadge}.jsx
└── pages/
    ├── LoginPage.jsx
    ├── EntitiesList/Detail/New/Edit.jsx
    ├── UsersList/Detail/New.jsx
    └── RolesAndPermissions.jsx      # RolesList + RoleDetail + PermissionsList
```

## What's Been Implemented

### 2026-04-19 — Prompt 1.1: Entities ✅
(See previous PRD revisions — tables, CRUD, scheduled insurance alerts, full UI. Alembic 0001 migration. 53/53 tests.)

### 2026-04-19 — Prompt 1.2: Users, Roles, Permissions ✅

### 2026-04-21 — Prompt 1.2 close-out patch ✅
- **Password complexity**: added uppercase / lowercase / number / symbol rules to `validate_complexity` (on top of the existing 12-char min + 5-password history). `hash_password` calls validate; a new `hash_token` sibling is used for random invitation tokens which shouldn't have to meet user-password policy. Decoy-timing hash updated to a compliant string.
- **Public policy endpoint**: `GET /api/auth/password-policy` returns the rule catalogue so the UI never drifts from the backend.
- **ProfileSecurity UI**: the Change Password section now shows all 5 rules as a live-validated green-dot list beneath the "New password" field, plus a static reminder about the 5-password history window.
- **Admin unlock**:
  - `POST /api/users/{id}/unlock` now refuses with 400 if the user isn't actually locked (previously silently succeeded).
  - Audit breadcrumb appended to `admin_notes` (`[Unlocked by <email> (<id>) at <timestamp>]`) until Prompt 1.4's `audit_events` table lands. Also emits an `INFO` log line on `syhomes.auth`.
  - UsersList shows a red "LOCKED" badge + an inline "Unlock" action column (only rendered when the viewer holds `users.admin`, and only enabled per-row when the target is actually locked).
  - UserSummary API response now carries `locked_until` + `failed_login_attempts` so the list view can gate the button without a per-row detail fetch.
- **Tests**: +9 new cases (`test_password_complexity.py`) covering the policy endpoint, each of the 5 rules (reject weak / accept strong), and the unlock endpoint's 204 success / 400 not-locked / 403 forbidden paths. Older test that assumed idempotent unlock on an already-unlocked user updated to lock first via failed logins. Full suite: **128 passed, 1 skipped, 0 failed**.

### Lockout policy (confirmed, unchanged in this patch)
- **Threshold**: 5 failed logins
- **Lockout**: **time-based** — 15 min on 1st offence, 30 min on 2nd, 60 min on 3rd+ (escalates via `lockout_level`, persists across lockouts)
- **Counter reset**: `failed_login_attempts` is reset to 0 on **any** successful login (`_clear_lockout` in `auth.py`); `locked_until` is also cleared then. `lockout_level` is **not** reset on success — so a user who has tripped the lockout three times this year still gets the 60-min penalty on offence #4. Admin unlock clears `lockout_level` back to 0.

### 2026-04-19 — Prompt 1.2 addendum: MFA security gap closures ✅
- **Alembic 0003**: `users.mfa_enforced_at` → `mfa_enrolled_at` (name reflects intent: moment of enrolment, not policy enforcement).
- **Gap 1 — Disable MFA requires password re-auth**: `POST /api/auth/mfa/disable` now takes `{current_password}`. Wrong password → 400. Closes the session-hijack-strips-MFA vector.
- **Gap 2 — Regenerate backup codes requires password + current TOTP**: `POST /api/auth/mfa/backup-codes/regenerate` takes `{current_password, current_totp}`. Either wrong → 400. Prevents an attacker with a live session from invalidating the user's physical recovery path.
- **Gap 3 — Hard block on login for MFA-enforced roles**: Users holding `super_admin` / `director` / `finance` who haven't enrolled now receive a short-lived (15 min) `mfa_pending` JWT instead of a full access token. That token only unlocks `/auth/me`, `/auth/mfa/enroll/*`, `/auth/password/change`, `/auth/logout`. Any protected endpoint (e.g. `/api/entities`) returns 401. Completing `/mfa/enroll/confirm` atomically issues a full access token + sets the httpOnly cookie (token swap).
- **Seniority**: The login response surfaces `enforced_role_name` of the most-senior enforced role the user holds (by `roles.priority ASC`). UI displays "Your role (Director) requires two-factor authentication…" dynamically.
- **Frontend forced-enrolment gate** (`/app/frontend/src/pages/ForcedMfaEnroll.jsx`): Full-screen gate rendered by `ProtectedRoute` whenever the session is in `pending_mfa` state. Intro → Scan → Backup-codes flow, with `Log out` available at every step. Navigating to `/entities` while pending shows the gate (hard-block honoured client-side too).
- **ProfileSecurity disable modal**: `data-testid='mfa-disable-password'` input; submit disabled without password.
- **ProfileSecurity regen modal**: `data-testid='mfa-regen-password'` + `mfa-regen-totp`; submit disabled until both filled.
- **Test suite**: conftest helper `login_with_auto_enroll` caches the TOTP secret per email for the pytest session so MFA-enforced fixtures never skip after the first enrolment. Real bootstrap admin (`rhys@syhomes.co.uk`) is **never** auto-enrolled by tests — `super_admin_token` aliases to `test-admin`. 119/119 backend tests pass (58 existing + 21 gap-closure + 40 others).
- **Testing agent 5th iteration**: 21/21 new backend tests + 8/8 frontend flows green; no critical/minor issues.

### 2026-04-19 — Prompt 1.2: Users, Roles, Permissions ✅
- **Tables** (migration 0002): `users`, `roles`, `permissions`, `role_permissions`, `user_roles`, `user_role_entities`, `user_role_projects`. `entities.created_by_user_id` retrofit column + index.
- **RBAC model**: 10 system roles seeded; 87 atomic permissions across 24 resources; role-permission mapping in `seed_rbac.py`.
- **Auth primitives**: argon2id password hashing (64 MiB / 3 / 4 per OWASP), password history (5 deep), 12-char minimum; Fernet-encrypted TOTP secrets; 10 single-use backup codes (argon2-hashed); HS256 JWT access tokens (4h in 1.2; reduced to 15min + refresh tokens in 1.3).
- **Account lockout**: 5 failed attempts → 15/30/60-min escalating lockouts; super_admin `/unlock` endpoint.
- **MFA flow**: `/mfa/enroll/start` → QR; `/mfa/enroll/confirm` → 10 backup codes returned once; login → mfa_challenge JWT → `/mfa/verify` → access token. Backup codes consumable (used_at stamped).
- **Effective permissions**: JOIN-per-request (no cache yet per agreed simplification for 1.2); union of active role-permissions minus per-assignment `view_overrides`; entity-scope + project-scope honoured; `UserPermissions.has_on_entity(code, entity_id)` + `entity_ids_with(code)` helpers.
- **Dependency-level enforcement**: `Depends(require_permission(*codes))` factory — 403 fires before handler logic. Applied to every entities route and every users/roles/permissions route.
- **Entities retrofit**: `created_by_user_id` stamped on POST; list filtered by scope; sensitive fields (`bank_*`, `xero_*`) stripped from response unless caller has `entities.view_sensitive` or `entities.admin`; Banking/Xero PUT paths blocked without `entities.view_sensitive`.
- **Scheduled jobs**: hourly `user_roles` expiry sweep → marks `Active` rows past `expires_at` as `Expired`.
- **Bootstrap**: requires `BOOTSTRAP_ADMIN_EMAIL` + `BOOTSTRAP_ADMIN_PASSWORD` in `.env`; seed fails loudly if absent. Grants `super_admin` role, scope=All/All.
- **Frontend**: `/login` page (two-pane enterprise layout, TOTP + backup-code fallback); `AuthContext` with JWT localStorage + 401 auto-logout; top-bar user menu + logout; `/users` list + `/users/:id` detail with role-assignment modal (entity_scope=All/Specific picker, view_overrides, expiry); `/users/new` invite flow with one-time token display; `/roles` list + `/roles/:id` matrix (read-only, grouped by resource); `/permissions` grouped list; Entity detail Banking + Xero sections show "Restricted — insufficient permissions" placeholder when `entities.view_sensitive` missing.
- **Test users** (7 fixtures): `test-admin`, `test-director`, `test-pm` (scoped to Shrewsbury), `test-finance`, `test-site`, `test-readonly`, `test-archived`. Seeded idempotently via `scripts/seed_test_users.py`. Real super_admin (`rhys@syhomes.co.uk`) stays out of test credentials file.
- **Testing**: 85/85 backend tests pass (32 auth/RBAC + 31 entities + 22 insurance). Frontend flows verified: login, logout, scope-filtered lists, sensitive-field gating, role assignment, invite token display.

## Acceptance Criteria for Prompt 1.2 — all met
- ✅ First super_admin created during initial setup (from .env-provided credentials)
- ✅ 10 roles seeded and visible on /roles
- ✅ 87 permissions seeded and visible on /permissions (spec said ~90)
- ✅ Can assign a role to a user with entity/project scope
- ✅ Director role sees all entities; PM scoped to Shrewsbury sees only Shrewsbury
- ✅ view_overrides correctly removes specific permissions from an assignment
- ✅ Expired user_roles marked Expired via hourly scheduled job
- ✅ Password change rejects reuse of last 5 passwords
- ✅ MFA flow end-to-end (TOTP enrolment → QR → backup codes → login prompt → verify)
- ✅ Account locks after 5 failed attempts; super_admin /unlock works
- 🕒 Self-approval modal — **helper in place; UI deferred** (no approval workflows exist until budgets/appraisals modules)
- ✅ Archived users cannot log in; row preserved for FK integrity

## Deferred per agreed deviations (with pointers for the prompt that picks them up)
- Effective-permissions caching → Prompt 1.3 (when sessions arrive)
- SMS/Email MFA → requires Twilio/SendGrid integrations (later module)
- Login history/sessions/refresh tokens → Prompt 1.3
- SSO (Google/Microsoft/Apple) → Prompt 1.3
- Password breach check (HIBP) → Prompt 1.3
- Audit log writes on role changes → Prompt 1.4
- project_scope='Specific' UI → Prompt 1.5 (projects FK)
- Self-approval modal integration → first prompt with an approval workflow
- PII scrub UI confirmation dialog → Prompt 1.7 (Notifications gives us a confirm UX pattern)

## Prioritised Backlog (Foundation 1.1 → 1.7)
- **P0**: 1.3 Sessions/Login History/Invitations/SSO/API Keys; 1.4 Audit log (with retroactive hooks on entities & user_role changes); 1.5 Projects; 1.6 (reserved); 1.7 Notifications (closes the `_emit_alert` log hook).
- **P1**: Modules 2–10 (Projects, Cost Codes, Appraisals, Budgets, Cash Flow, Programme, Documents, Compliance).
- **P2**: Xero OAuth (5.1), Bank feed, Group consolidation, Multi-tenancy surfacing.

## Process Commitments
- Never silently defer agreed standards — surface deviations in-channel before changing course.
- Every prompt delivers: migration + backend + tests + UI + test-fixture coverage.
- `alembic check` must return clean before declaring a prompt complete.
- Real human credentials never committed to disk; test users get deterministic passwords in `test_credentials.md`.
