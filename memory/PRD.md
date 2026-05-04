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


### 2026-05-04 — Prompt 2.3 Checkpoint 2: Appraisal Governance ✅

**Migration 0022** (`/app/backend/alembic/versions/0022_appraisal_governance.py`)
- Three new tables with triggers and constraints:
  - `appraisal_revisions` (11 cols, 3 CHECKs, 4 indexes incl. UNIQUE on `appraisal_id_to`).
  - `appraisal_scenarios` (8 cols, 1 CHECK Base/parent XOR, 5 indexes incl. 2 UNIQUEs).
  - `appraisal_decision_log` (12 cols, 4 CHECKs, 5 indexes, self-FK).
- New enums: `appraisal_revision_reason_enum` (8 values) + `decision_type_enum` (6 values).
- `validate_scenario_parent` trigger function blocks non-Base parents.
- `reject_decision_log_mutation` trigger function enforces append-only on
  decision log (UPDATE + DELETE → exception).
- `appraisal_scenarios` backfill (Base row per group; no-op with 0 rows).
- `system_config` seed: `appraisal_decisions_required_threshold = 3`
  (Integer, Appraisal category). **Spec deviation resolved**: drafted
  migration assumed `(key, value, value_type, description)` columns;
  actual 1.7 schema uses `(config_key, config_value, value_type, category,
  description, is_system_locked, minimum_role_to_edit, default_value)` —
  migration INSERT corrected before apply.
- Lock duration: 0.44s.

**Services** (3 new files under `app/services/`)
- `appraisal_revisions.py::create_new_version` — single-transaction orchestration: source.is_current=false (flush) → mark_superseded if Approved → clone_as_new_version → new.is_current=true (flush) → revision row → recompute. Atomic handover satisfies partial-unique gate.
- `appraisal_scenarios.py` — `create_scenario` (from Base v1 anchor only), `list_group_scenarios` (fixed Base→Upside→Downside→Sensitivity order), `get_group_comparator` (absolute values only; frontend computes deltas).
- `appraisal_decisions.py` — `log_decision` (Europe/London timezone enforcement, Conditional_Go XOR conditions, Correction XOR reference, version match, is_current gate), `list_for_appraisal`, `get_nudge_state` (counts distinct Go/No_Go/Defer deciders).
- `appraisal_calc.py::_recompute_revision_deltas` appended as pipeline step 9 (idempotent).

**Router** (new file `app/routers/appraisal_governance.py`)
- 9 endpoints under `/api/v1`:
  - `POST /appraisals/{id}/new-version` (appraisals.edit, 201)
  - `GET /appraisals/{id}/revisions` (appraisals.view)
  - `GET /projects/{id}/revisions` (appraisals.view)
  - `POST /appraisals/{base_id}/scenarios` (appraisals.edit, 201)
  - `GET /appraisal-groups/{group_id}/scenarios` (appraisals.view)
  - `GET /appraisal-groups/{group_id}/comparator` (appraisals.view)
  - `POST /appraisals/{id}/decisions` (**appraisals.approve**, 201)
  - `GET /appraisals/{id}/decisions` (appraisals.view)
  - `GET /projects/{id}/nudge` (appraisals.view)

**Endpoint behaviour changes in `app/routers/appraisals.py`**
- `/reopen` Approved-clone branch **removed** per spec B.4. Approved and
  Rejected both now toggle to status=`Reopened` on the same row; no clone,
  no version bump, is_current unchanged. Both also require `is_current=true`.
- Appraisal create endpoint backfills Base-scenario anchor for new groups.

**Tests**: `tests/test_appraisal_governance.py` (44 tests across 8 classes).
- `TestMigration0022` — 3 tests (tables, enum values, system_config seed).
- `TestDecisionLogImmutability` — 2 tests (DB-layer UPDATE + DELETE raise).
- `TestScenarioParentTrigger` — 1 test (raw SQL insert with non-Base parent raises).
- `TestNewVersionEndpoint` — 8 tests (Approved, Rejected, Draft-blocked, short summary, invalid reason, source-not-current, lineage, deltas populated, readonly-forbidden).
- `TestReopenFinalForm` — 4 tests (Rejected toggle, Approved toggle no clone, Draft blocked, non-current blocked).
- `TestScenarios` — 8 tests (create Upside, short description, Base rejected, duplicate label, non-Base source, ordered listing, comparator shape, readonly forbidden).
- `TestDecisions` — 11 tests (Go happy, Conditional_Go require + happy, conditions-for-Go blocked, future-dated, version mismatch, non-current blocked, Correction require + happy, client proxy rejected, list ordering, readonly-forbidden).
- `TestNudge` — 5 tests (no Approved Base, under threshold, at threshold, non-core types excluded, readonly can view).

**Full suite: 581/581 passing** (was 537 → +44 governance tests + 2 modified; 0 regressions).

**STOP** — Checkpoint 2 complete. Awaiting user go-ahead before Checkpoint 3 (frontend: RevisionTimeline, ScenariosPanel, ScenarioComparator, DecisionsTab, nudge banner).


### 2026-05-03 — Prompt 2.3 Checkpoint 1: Appraisal Retrofit ✅

**Migration 0021** (`/app/backend/alembic/versions/0021_appraisal_retrofit.py`)
- Renames on `appraisals`: `version`→`version_number`, `state`→`status`,
  `total_gdv`→`gdv_total`, `total_profit`→`profit_total` (`total_cost` unchanged).
- Adds `appraisal_group_id` (uuid NOT NULL, model-side default `uuid.uuid4`),
  `is_current` (bool NOT NULL DEFAULT false), `scenario` (`appraisal_scenario_enum`
  NOT NULL DEFAULT 'Base').
- Extends `appraisal_state` enum with `Withdrawn` + `Reopened`; extends
  `audit_action` enum with `Appraisal.NewVersion`, `Appraisal.ScenarioCreate`,
  `Appraisal.DecisionLog`, `Appraisal.Withdraw` — all wrapped in
  `autocommit_block()` per PG 15.16 enum-extension rule.
- Drops `uq_appraisals_project_version` UNIQUE CONSTRAINT (R0 verified it was
  a CONSTRAINT, not bare INDEX). Creates `uq_appraisals_project_scenario_version`
  (composite UNIQUE) and `uq_appraisals_current_per_project_scenario`
  (partial UNIQUE WHERE is_current=true).
- Backfills `appraisal_group_id` (one UUID per project_id) and `is_current=true`
  for the latest non-terminal version per (project, scenario). Pre-retrofit row
  count was 0 so backfill was a no-op; assertions guard re-runs with data.
- ALTER TABLE lock duration: 0.45s.

**Backend code rename pass** — files: `app/models/appraisals.py`,
`app/routers/appraisals.py`, `app/services/appraisal_calc.py`,
`app/services/appraisal_versioning.py`, `app/services/rlv_solver.py`,
`app/models/audit.py`, `tests/test_appraisals.py`.

**State machine extension**:
- `is_editable` whitelist now includes `Reopened` per Phase B.1.
- `ALLOWED_TRANSITIONS`: Draft→{Submitted,Withdrawn}; Submitted→{Approved,
  Rejected,Draft,Withdrawn}; Approved→{Superseded,Reopened}; Rejected→{Reopened};
  Reopened→{Submitted,Withdrawn}; Withdrawn/Superseded terminal.

**Endpoint behaviour split** (Phase F + B.2 — option ii: defer `/new-version` to C2):
- `/appraisals/{id}/withdraw` — rewritten. Sources: Draft, Submitted, Reopened.
  Sets `status='Withdrawn'`, `is_current=false`. **Submitter-only restriction
  removed**: any `appraisals.edit` holder may withdraw. Audit action:
  `Appraisal.Withdraw`. Returns 400 `NOT_WITHDRAWABLE` for non-allowed sources.
- `/appraisals/{id}/reopen` — partial rewrite. Rejected→Reopened (was Draft);
  rejection_reason cleared. Approved-clone path retained with
  `# TODO 2.3 C2:` comment so 2.2 clone tests continue to pass post-rename.
  is_current handover atomic: source flipped false BEFORE new row flipped true.
- `/new-version` — deferred entirely to Checkpoint 2.

**Frontend retrofit**: `STATE_BADGE` extended in both `atoms.jsx` and inline
copy in `AppraisalsList.jsx` (Withdrawn = muted gray italic, Reopened = amber).
All field reads renamed across `AppraisalPage.jsx`, `AppraisalsList.jsx`,
`SummaryTab.jsx`, `UnitsTab.jsx`. Edit-gate broadened to Draft+Reopened.
Withdraw CTA visible to any `appraisals.edit` holder when status ∈
{Draft, Submitted, Reopened}. New banners for Withdrawn and Reopened.

**Tests**: 30+ existing 2.2 tests updated for renames + new endpoint semantics
(in particular: `test_reopen_rejected_returns_to_reopened` was
`test_reopen_rejected_returns_to_draft`; state-machine matrix expanded).
6 new C1 acceptance tests added under `TestRetrofit23C1`:
1. `test_create_sets_retrofit_columns` (group_id, is_current, scenario, version_number)
2. `test_withdraw_from_draft`
3. `test_withdraw_from_submitted`
4. `test_withdraw_from_approved_blocked` (NOT_WITHDRAWABLE)
5. `test_reopened_appraisal_is_editable` (edit-gate post-Reopened)
6. `test_audit_log_carries_appraisal_withdraw_action`
**Full suite: 537/537 passing** (was 531).

**Phase 1 spec deviations resolved (CHANGELOG-documented)**:
- Drafted migration said `audit_action_enum` and `DROP INDEX`; actual PG types
  are `audit_action` and the original was a UNIQUE CONSTRAINT — corrected.
- `/reopen` Approved-clone retained for C1 (option ii); to be split in C2.
- Withdraw broadened from submitter-only to any `appraisals.edit` holder.
- Rejected→Reopened (was Rejected→Draft).
- New 2.3 audit values use `Appraisal.*` namespace; existing flat values
  (`Reopen`, `Submit`) untouched. Inconsistency accepted, CHANGELOG-noted.

**STOP** — checkpoint complete. Awaiting user go-ahead before Checkpoint 2
(Migration 0022 + 3 new tables + immutability triggers + services + endpoints).

### 2026-04-23 — Prompt 1.5: Projects + Project Team Members ✅

**Schema (Alembic 0008 + 0009)**
- `projects` (~30 cols): project_code (unique), name, project_type, parent_project_id (self-FK),
  primary_entity_id / construction_entity_id, land_ownership_method, site_address + postcode,
  site_area_ha + acres (4dp numeric), tenure, planning_{ref,type,status,approval_date,expiry_date},
  implementation_required, s106/cil/vat flags, units_target/actual, affordable_housing_pct,
  target/actual start+PC dates, current_stage + stage_entered_at, status, dead_reason, cached
  financials (gdv/build_cost/all_in_cost/profit/margin + financials_refreshed_at), project_lead_user_id,
  created_by_user_id, notes. 4 indexes + partial index on planning_expiry for sweep candidates.
- `project_team_members`: project_id, user_id, role_on_project, is_primary, assigned_{by_user_id,at},
  removed_at, notes. Partial unique index `ux_team_one_active_primary_per_role` enforces one
  active primary per (project, role) via `WHERE is_primary=true AND removed_at IS NULL`.
- 0009 wires retroactive FKs: `user_role_projects.project_id → projects.id (CASCADE)` and
  `audit_log.project_id → projects.id (SET NULL)`.
- Trigger `set_updated_at` on both tables.

**Backend endpoints** (all `/api/projects…`, cookies-only auth)
- `GET /` — list with filters (project_type[], current_stage[], status[], q, primary_entity_id,
  project_lead_user_id), pagination, strict RBAC scoping (user_role.project_scope = All/Specific/None).
- `POST /` — create; auto-generates `project_code` via 3-char slug prefix + sequential counter;
  override accepted if it matches `^[A-Z0-9]{3}-\d{3,}$`. Reconciles area (ha wins over acres).
  Auto-calculates planning_expiry (+3y for Full/Outline/Hybrid/Permitted_Dev/Prior_Approval;
  +2y for Reserved_Matters).
- `GET/PUT/DELETE /{id}` — with 404-on-scope-miss, project_code immutability, area + expiry
  auto-recalc on update, manual-expiry-override flagged in audit metadata, delete hook via
  `has_project_dependents()` (stub today; extends per Prompts 2.2/2.4/2.5/3.2/4.2/4.3/5.1).
- `POST /{id}/stage/advance` — forward-only transitions via hard-coded FORWARD_TRANSITIONS;
  requires `dead_reason` when moving to Dead. Status auto-syncs (Dead→Dead, Closed→Complete).
- `POST /{id}/stage/override` — super_admin ONLY; min 10-char reason; `director_notifications`
  payload written into audit metadata (actual notifications land in Prompt 1.7).
- `GET/POST /{id}/team` + `DELETE /{id}/team/{tm_id}` — soft-remove via `removed_at`;
  primary Project_Lead syncs to `projects.project_lead_user_id` (and nulls on removal).
- `POST /{id}/financials/refresh` — STUB; returns zeros, stamps `financials_refreshed_at`.
  Requires `projects.view_sensitive`.

**Scheduler**
- `planning_expiry_sweep` daily 07:00 UTC (APScheduler cron). Filters active, unstarted,
  implementation-required projects with a planning_expiry_date set. Fires at exact-day
  thresholds {365, 180, 90, 30, 0} and daily past expiry. Returns notification payloads
  (logged today; inserted into `notifications` in Prompt 1.7).

**Services**
- `app/services/projects.py` — code generation, area reconciliation, expiry derivation,
  delete-dependents hook.
- `app/services/project_stage.py` — FORWARD_TRANSITIONS graph + `is_allowed_forward()` +
  `derived_status()`. **Deliberate deviation**: forward-only hard-coded model rather than
  "flagged non-sequential" per spec. Polish Pass (post-1.7) moves the graph into `system_config`
  and considers allowing Sales ↔ Post_Completion concurrency.
- `app/services/project_financials.py` — zero-valued stub until 2.5 + 2.7 land.

**Seed**
- `seed_rbac.py` adds `projects.{view, view_sensitive, create, edit, delete, approve, admin}`.
- project_manager role gains projects.create/edit/view_sensitive. director + super_admin
  retain full coverage via their catch-all grants.

**Frontend**
- `/projects` list — search (name/code/address/postcode), filters (type/stage/status),
  margin% column gated on `projects.view_sensitive`, pagination, filter chips, empty state.
- `/projects/new` — required-field validation, live ha↔acres conversion (symmetric),
  planning expiry auto-fill preview (+3y/+2y per type), route gated on `projects.create`.
- `/projects/:id` — Header with current-stage badge, dead-banner when Status=Dead, action
  buttons mirror FORWARD_TRANSITIONS (Dead button opens reason-required modal),
  super_admin-only Override button (10-char min reason validated both sides), delete button.
- Overview tab: 5 collapsible sections (Summary, Site, Planning, Targets, Financials).
  Financials section only renders for users with `projects.view_sensitive`, includes
  "Last refreshed" stamp + Refresh button.
- Team tab: primary-per-role marker, Add Team Member modal (user picker + role + primary
  toggle), Remove (soft), history toggle to show removed members.
- Audit tab: pulls `/api/audit?project_id=…`, handles 403 with explicit forbidden message
  (falls back to existing `/audit` page for full view).

**Tests**: +93 new (`tests/test_projects.py`) covering project code gen + override validation
+ duplicates + immutability, ha↔acres reconciliation (incl. round-trip + NULL), planning
expiry auto-calc (Full/Outline/Reserved_Matters/missing), manual override audit flag,
stage advance (init, forward, cannot skip/reverse, walk-to-closed), Dead from any stage,
Closed→Complete auto-status, super_admin override (permission gate, 10-char reason,
same-stage reject, Dead-reason requirement, audit metadata + director_notifications),
team CRUD (one primary per role unique constraint, role validation, unknown user, soft
remove, project_lead_user_id sync, idempotent removal, cross-project 404), audit diff
tracking (no-change = no-audit), RBAC (401, 403s, readonly sees no financials, director/
finance/super see financials, pagination, search, filter by stage/entity), delete 204 +
404 + cascade-set-null on audit project_id, planning expiry sweep thresholds (30/100/past/
non-active/started-project skips), financials refresh stub (200 on super, 403 on readonly,
timestamp stamped), retro FKs exist + set-null on delete, unit tests on service helpers.
Full suite: **314 passed, 1 skipped, 0 failed** (was 221 → +93).

**Known deviations from spec**
- Stage machine is hard-coded forward-only with an explicit super_admin override, deliberately
  chosen over the spec's "non-sequential allowed but flagged" model. Revisit in Polish Pass
  (post-1.7): move FORWARD_TRANSITIONS into system_config, and consider whether Sales and
  Post_Completion should run concurrently (developers often sell plots while mobilising the
  next phase).
- Financials refresh returns zeros pending Prompts 2.5 + 2.7.
- Director notifications for stage overrides are written into audit metadata today; actual
  notification delivery lands with the `notifications` table in Prompt 1.7.

## What's Been Implemented

### 2026-04-19 — Prompt 1.1: Entities ✅
(See previous PRD revisions — tables, CRUD, scheduled insurance alerts, full UI. Alembic 0001 migration. 53/53 tests.)

### 2026-04-19 — Prompt 1.2: Users, Roles, Permissions ✅

### 2026-04-21 — Prompt 1.3 stage 1b: Sessions + Refresh + Login History + Password Reset ✅

**Schema (Alembic 0004 + 0005)**
- `user_sessions`: id, user_id, access_token_jti, refresh_token_hash, previous_refresh_token_hash, ip_address, user_agent, device_name, location_{country,city,lat,long}, impersonator_user_id, remember_me, last_active_at, expires_at, revoked_at, revoked_reason (enum). 3 indexes (user+revoked, refresh_hash, expires, prev_refresh).
- `user_login_history`: append-only — DB trigger raises on UPDATE/DELETE. 20-value `event_type` enum + 15-value `failure_reason` enum. 3 indexes (user+ts, email+ts, event+ts).
- `email_send_log`: minimal deliverability trail — to_address, subject, template_id, status, error, provider_message_id, created_at.

**Backend (endpoints)**
- `POST /api/auth/login` — issues access + refresh; supports `remember_me` (30d default / 90d). Rate-limited 10/min per IP, 5/min per email.
- `POST /api/auth/refresh` — rotates refresh token; presenting a previously-rotated token revokes ALL user's sessions + stamps `Suspicious_Activity_Detected`.
- `POST /api/auth/logout` — revokes current session (via refresh cookie) with reason=Logout.
- `POST /api/auth/password-reset/request` — always 200 (no enumeration); rate-limited 3/hr per email, 10/hr per IP; emails via Console provider.
- `POST /api/auth/password-reset/complete` — validates token + 1-hr expiry, requires MFA code if MFA enabled, revokes ALL sessions, emails password_changed notice.
- `POST /api/auth/password/change` — revokes all OTHER sessions (current survives), stamps MFA_Change history event, sends changed-email.
- `GET /api/users/me/sessions`, `POST /api/users/me/sessions/{id}/revoke`, `POST /api/users/me/sessions/revoke-others`.
- `GET /api/users/{id}/sessions` (users.admin), `POST /api/users/{id}/sessions/revoke-all` (sends session_revoked_email).
- `GET /api/users/{id}/login-history` — paginated, filter by event_types[] + date range + success_only. `GET /api/users/{id}/login-history.csv` — CSV export.

**Backend (infra)**
- **Sessions service** (`app/services/sessions.py`): create/rotate/revoke + idle-timeout check. JWT now carries `sid` + `jti`; 15-min TTL.
- **Session-aware auth deps**: `get_optional_principal` / `get_current_principal` look up the session row on every authed request, enforce `revoked_at`, match JWT `jti` to `access_token_jti`, check 60-min idle, touch `last_active_at` throttled to 1 write per 60s.
- **Email infra** (`app/services/email.py` + `email_templates.py`): pluggable `EmailProvider` interface with `ConsoleEmailProvider` default. SendGrid path staged (commented) — flip in 4 lines when key supplied. Templates: password_reset_email, password_changed_email, session_revoked_email (inline-CSS SY Homes shell).
- **Geolocation** (`app/services/geolocation.py`): MaxMind GeoLite2 wrapper; absent mmdb → `country=NULL` gracefully. Bootstrap script `scripts/download_geolite2.py` pulls ~60 MB tarball when `MAXMIND_LICENSE_KEY` set. Private/loopback IPs → `country='Local'`.
- **Rate limiter** (`app/services/rate_limit.py`): in-process token bucket, thread-safe. `SYHOMES_RATE_LIMIT_DISABLED=1` flag for test runs (set in dev `.env`). Redis migration flagged for production deployment.

**Frontend (pages / surfaces)**
- `/forgot-password` + `/reset-password?token=…` — public pages with live 5-rule password checklist + MFA code field (shown conditionally).
- `/profile/sessions` — table of every browser/device, Current pill, Revoke per row, "Revoke all other sessions" bulk action, Remember-me badge, IP redaction.
- `/users/:id/sessions` (admin) — same shape + "Revoke all sessions" with email notification.
- `/users/:id/login-history` (admin) — paginated 50/page, event-type multi-select, success/fail toggle, CSV export.
- LoginPage — Remember me checkbox + Forgot password link + 90-day copy.
- AuthContext — auto-refresh on 401 via single in-flight promise; idle-timer (55m warn / 60m force logout); LocalStorage-backed token pair with dispatched `syhomes:unauthorized` event for clean state teardown.
- AppShell dropdown — added "Active sessions" item beside "Change password".
- UserDetail header — new Sessions + Login history buttons (users.admin only).

**Tests**: +25 new (`tests/test_sessions_history_reset.py`) covering:
- Login returns session-bound access + refresh + device fingerprint from UA
- remember_me extends expiry to 88–90 days
- Refresh rotates; old refresh → replay → all sessions revoked + `new_access` also invalidated
- Logout revokes session with reason=Logout
- Password change revokes other sessions but keeps current alive
- Login history records every event; trigger raises on UPDATE/DELETE
- List-my-sessions marks current correctly; revoke-others keeps current alive
- Admin list + revoke-all; email_send_log row written for password_reset_email
- Password reset full flow: unknown email 200, known email 200, valid token completes, expired token 400, used token rejected 2nd time, weak password 422
- Login history admin endpoint: list + forbidden for non-admin + CSV export

Full suite: **160 passed, 1 skipped, 0 failed** (was 135 → +25).

**Deferred to 1.3 stage 2**: invitation email delivery, SSO (Google/Microsoft/Apple), API keys, suspicious-activity alerts (new-country + impossible-travel detection), `/invitations` + `/api-keys` + `/profile/security/sso` UIs, rate limits on SSO callbacks.

**Production config required before flipping to live**:
- `SENDGRID_API_KEY` + `EMAIL_FROM_ADDRESS` + `EMAIL_FROM_NAME` + `EMAIL_REPLY_TO` (uncomment SendGridEmailProvider in `app/services/email.py`).
- `MAXMIND_LICENSE_KEY` + run `scripts/download_geolite2.py` on a weekly cron.
- DNS SPF/DKIM/DMARC on the sending domain (see `backend/README.md`).
- Remove `SYHOMES_RATE_LIMIT_DISABLED=1` from `.env`.
- Plan Redis migration for rate limiter when deploying multi-worker.

### 2026-04-21 — Prompt 1.2 close-out patch #2: Edit User ✅
- **Backend**: `PUT /api/users/{id}` tightened to require `users.admin` (was `users.edit`). Schema now accepts `email` on top of the prior scalar fields; rejects Archived status (use `/scrub_pii`); only permits Active/Suspended/Pending_Invitation transitions. Email change flips `email_verified=false` + nulls `email_verified_at` and the user must re-verify on next login (full flow lands in 1.3). Email collision on the tenant returns 409 with a friendly message. Self-deactivation blocked with 400. Diff between before/after is tracked and only the changed fields stamp `admin_notes` (`[Edited by <email> (<id>) at <ts>: <fields>]`). Emits `INFO` on `syhomes.auth`.
- **Frontend**: new `/users/:id/edit` page (`UserEdit.jsx`) with first/last name, email, phone, Active ↔ Suspended toggle. Inline validation (required + email regex + email-change warning banner + self-deactivation lockout), live "N changes" diff counter, Save button disabled until the form is valid and dirty. Edit buttons added to both UsersList (per-row action column) and UserDetail (header) — both gated on `users.admin`.
- **Tests**: +7 cases (`test_user_edit.py`) covering success path, email collision 409, non-admin 403, email-change email_verified flip, suspended user can't log in + reactivation restores login, self-deactivation 400, Archived rejection. Full suite: **135 passed, 1 skipped, 0 failed**.

### 2026-04-21 — Prompt 1.2 close-out patch ✅ (complexity + unlock)
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
- **P0**: ✅ 1.3 Sessions/Login History/Invitations/SSO/API Keys; ✅ 1.4 Audit log; ✅ 1.5 Projects; ✅ 1.6 Cost Codes; ✅ **1.7 System Config + Notifications** — Foundation track CLOSED 26 Apr 2026.
- **P1**: Modules 2–10 (Appraisals, Budgets, Cash Flow, Programme, Documents, Compliance, Sales).
- **P2**: Xero OAuth (5.1), Bank feed, Group consolidation, Multi-tenancy surfacing.

## Prompt 2.2 — Appraisals Core (2 May 2026, backend + tests complete)
- ✅ Alembic 0019: 4 tables (`appraisals`, `appraisal_units`, `appraisal_cost_lines`, `appraisal_finance_model`) with triggers, indexes, FKs to projects/users/cost_codes. 7 enum types. Two new permission codes (`appraisals.submit`, `appraisals.view_financials`) bring total perms to 83.
- ✅ Alembic 0020 — enum fidelity: `permission_action` += `submit`, `view_financials`; `audit_action` += `Submit`. Permission rows backfilled; 1:1 code↔action mapping restored.
- ✅ Models in `app/models/appraisals.py` with ORM relationships (cascade delete).
- ✅ Three calculation engines (Decimal-only, no floats):
  - `appraisal_classification.py` — SDLT category resolver (honours surcharge/corporate threshold + developer relief).
  - `finance_engine.py` — four interest modes (Simple_Monthly, Compound_Monthly, Rolled_Up, Serviced) with arrangement + exit fees. Compound_Quarterly deferred.
  - `rlv_solver.py` — secant iterator, Decimal-only, 50-iteration cap, negative-land guard, does NOT mutate header land price.
  - `appraisal_calc.py` — canonical **8-step pipeline** (units → cost pass 1 → GDV → SDLT → cost pass 2 → Finance → header recompute → updated_at/is_stale).
- ✅ `appraisal_versioning.py` — state machine + `clone_as_new_version` (deep-clones units/lines/facilities) + `mark_superseded`.
- ✅ Router at `/api/v1/appraisals` + `/api/v1/projects/:id/appraisals`:
  - CRUD for appraisals, units, cost lines, finance facilities.
  - State machine: submit / approve / reject (reason ≥5 chars required) / withdraw (submitter-only) / reopen (Rejected→Draft; Approved→clone new version + source Superseded).
  - `recompute` and `recalculate-rlv` endpoints.
  - **Field gating**: keys for land_purchase_price, totals, margins, RLV, target_profit_* are **OMITTED** (not nullified) for callers without `appraisals.view_financials`.
  - Defaults consumed on create from `appraisal_default_settings` (specific project_type beats 'All'), seeding Percentage_Of_* cost-line skeleton + SDLT_Engine + Finance_Engine auto-lines.
  - `/submit` endpoint emits `audit_action='Submit'` (distinct from `Update`/`Approve`).
- ✅ RBAC updated: super_admin=83, director=79, project_manager + finance gain `appraisals.view_financials` + `appraisals.submit`.
- ✅ **531/531 tests passing** (491 baseline + 40 new in `test_appraisals.py` covering SDLT classification, finance-engine modes, RLV convergence/non-convergence/non-mutation, 8-step pipeline ordering assertions, state-machine transitions, router integration end-to-end, financial-field gating, and enum-fidelity regression guards).
- ✅ **Frontend Phase D COMPLETE (2 May 2026, full E2E verified)**:
  - `yarn add decimal.js@10.6.0` + `app/frontend/src/lib/appraisalMath.js` helpers
  - `AppraisalsList.jsx` at `/projects/:id/appraisals` (version list, state badges, financial KPIs gated)
  - `AppraisalPage.jsx` at `/appraisals/:id` with 5 tabs (Header, Units, Costs, Finance, Summary)
  - **Two-layer calc model**: LIVE decimal.js transforms on unit rows (gia, gdv/sqft, gdv total/type, build/unit, build total/type) — instant, no round-trip. Everything else (KPIs, auto cost lines, facility interest/fees, RLV) has stale-until-save pills.
  - **RLV three-state panel**: `rlv-panel-empty` → `rlv-panel-calculated` (timestamp + recalc) → `rlv-panel-non_convergence` (banner + solver message). State flips, does not collapse.
  - State-machine UI: Draft editable; Submit/Approve/Reject/Reopen/Withdraw CTAs gated by permissions + role. Rejection-reason banner, submitted banner, superseded banner.
  - `testing_agent_v3_fork` — 18/18 acceptance scenarios passed against live preview URL (iteration_8.json).
  - **Code-quality refactor** (2 May 2026, same-day): split the 1176-line `AppraisalPage.jsx` into a 232-line shell + 6 focused modules under `components/appraisal/` (`atoms.jsx` 91, `HeaderTab.jsx` 122, `UnitsTab.jsx` 224, `CostsTab.jsx` 218, `FinanceTab.jsx` 175, `SummaryTab.jsx` 195). All files now well under 250 lines. testing_agent_v3_fork re-ran the full 18/18 acceptance sweep (iteration_9.json) — zero regressions. Dropped 3 dead testids (`rlv-state-empty/calculated/non-convergence`) that duplicated the canonical `rlv-panel-${state}` hooks.
- 📋 Future/Backlog (per spec): IRR/ROCE, optimistic concurrency control, live SONIA tracking, Compound_Quarterly, frontend Appraisal UI.
- ⚠️ Known fresh-DB bootstrap issue (pre-existing from 2.1, NOT introduced by 2.2): migration 0018 + 0019 require tenant + super_admin to exist — but lifespan runs `alembic upgrade head` BEFORE `seed()`. On pristine DBs the first boot fails; re-seeding + re-running alembic resolves. Logged for a future "migration bootstrap order" fix.

## Prompt 1.7 — System Config + Notifications (26 Apr 2026)
- ✅ `system_config` table + 38-key seed across 9 populated categories (Finance:3, Appraisal:8, Budget:5, Programme:4, Security:7, Integration:2, Notification:5, Reporting:2, Audit:2). Categories `Document`, `CashFlow`, `System` reserved in enum for future seeds.
- ✅ `notifications` table (15-type enum × 4-priority enum, 22 columns, 3 indexes incl. partial on `expires_at IS NOT NULL`).
- ✅ `SystemConfig` singleton service with in-memory cache + `set/restore/invalidate`. Typed parse/serialise for String/Integer/Decimal/Boolean/JSON/Date.
- ✅ `NotificationService.dispatch(...)` + `safe_dispatch(...)` wrapper. High|Critical → email via existing ConsoleEmailProvider. SMS branch logs `# TODO[SMS]` (deferred). Defaults expires_at to `now + auto_expire_days` (config-driven).
- ✅ Endpoints under `/api/v1/system-config` (GET list/grouped, GET one, PUT, POST restore) and `/api/v1/notifications` (GET inbox/filtered, GET unread/lazy-grouped, GET unread-count, PATCH read, PATCH dismiss, POST mark-all-read).
- ✅ APScheduler jobs (in-memory single-process): `notification_expiry_sweep` (daily 03:00 UTC) and `audit_retention_sweep` (daily 03:00 UTC, gated off by default via `audit.retention_purge_enabled`).
- ✅ Retro-wires: planning expiry sweep → Deadline_Approaching; stage override → System_Announcement High to all directors; insurance `_emit_alert` → Insurance_Expiry High/Critical; password reset request, MFA enrol, MFA disable → Security_Alert High to user. Post-build grep for `TODO[NOTIFY]` returns ZERO hits.
- ✅ RBAC: `system_config.view` granted to all 10 roles; `system_config.admin` super_admin only. Director loses `system_config.{admin,edit}` (count drops 84→82). Permission count remains 87 (codes were already in the catalogue from defensive earlier seeding; no new codes added).
- ✅ Frontend: `/config` grouped editor (typed inputs, Restore button, lock icon, read-only pill), navbar bell with 30s polling (`<NotificationBell>`), `/notifications` inbox with filters + bulk actions.
- ✅ Tests: 55 new across `test_system_config.py` (~22), `test_notifications.py` (~20), `test_scheduler_jobs.py` (~6), `test_retro_wires.py` (~7). Total suite **457/457** passing (402 baseline + 55).
- 📋 Polish Pass: persistent APScheduler jobstore for multi-process prod; per-key `minimum_role_to_edit` enforcement; notification body sensitive-field redaction; dispatch queue/worker; tighten `cost_codes` permission catalogue; render read-only ConfigPage values as `<input disabled>` for tooling parity; migrate older `/api/*` routes onto `/api/v1/*`.

## Process Commitments
- Never silently defer agreed standards — surface deviations in-channel before changing course.
- Every prompt delivers: migration + backend + tests + UI + test-fixture coverage.
- `alembic check` must return clean before declaring a prompt complete.
- Real human credentials never committed to disk; test users get deterministic passwords in `test_credentials.md`.
