# Change Log — SY Homes Platform Build

Running log of deviations, refinements, and corrections made during the build
of Phase 1. Update this any time something built differs from what the
specification says, or when a specification error is found and corrected.

## Format

Each entry: date, prompt reference (if applicable), change, rationale.

## Entries

### 2026-04-19 — Initial Specification

- Phase 1 specification pack v1.0 committed.
- `programme_calendars` schema updated from XLSX (7 per-weekday booleans) to
  JSONB-based design to match Emergent brief. Field count 1,293 → 1,288.
- Platform Spec docx updated to reference 1,288 field count.

<!-- Add entries below as you build. Example format:

### 2026-04-19 — Prompt 1.1 Entities built

- Full vertical slice delivered: schema, migration, API, React UI, validation, seed data, scheduler.
- 8/8 acceptance criteria fully passing.
- Tenants table added (multi-tenant ready, single-tenant live). - Tenant scoping as built (corrected 2026-04-22): tenant-scoped tables are `entities` and `users` only; global catalogue (`tenants`, `roles`, `permissions`, `role_permissions`); derivable via FK chain (`user_roles`, `user_role_entities`, `user_role_projects`, `user_sessions`, `user_login_history`, `email_send_log`). The original CHANGELOG claim that "all other tables include tenant_id" was inaccurate — architecture is defensible, docs are now correct.
- Alembic migration 0001_initial_entities: tenants + entities + 5 enums + partial unique indexes + set_updated_at trigger + per-table triggers.
- APScheduler daily 06:00 UTC insurance expiry sweep; exact-day threshold logic (60/30/14/7/0) with expired daily-loop.
- 53 backend tests passing (31 API + 22 threshold sweep).
- Idempotent container bootstrap at /root/.emergent/on-restart.sh.

**Deviations:**
- Emergent initially deferred Alembic to create_all(), retrofitted before Prompt 1.2.
- Pattern set: Emergent to surface agreed-standard deviations upfront before deviating, not silently.

**Known items for future prompts:**
- Permission stubs in entities router to be wired in Prompt 1.2
- created_by_user_id on entities to be backfilled retroactively in Prompt 1.2
- Cosmetic React warning (`<span>` in `<option>`) to fix in Prompt 1.2
- Suggested 30-min polish when Prompt 1.7 lands: surface insurance urgency dot on Entities list once notifications table exists


### 2026-04-20 — Prompt 1.2 retrofit: MFA enrolment UI

Gap caught during manual smoke test: MFA backend primitives were built
(argon2 secret, Fernet backup codes, TOTP verify) and 13/13 acceptance
criteria reported as passing, but there was no user-facing enrolment
UI — the testing subagent had been enrolling via direct API calls only.

Retrofit added:
- Profile area accessible from user avatar in AppShell topbar
- /profile/security page with MFA enable/disable/regenerate flow
- QR code + manual-entry secret display on enrolment
- TOTP verification step before completion
- 10 backup codes shown with copy-to-clipboard (shown once)
- Login flow extended: TOTP challenge after password, backup code fallback
- MFA prompt-to-enrol on next login for super_admin, director, finance roles

Lesson for future prompts: add explicit "end-to-end via UI" verification
to acceptance-criteria testing, not just API-level testing. Automated
tests pass against endpoints; users experience UIs.

-->
## Polish Pass TODOs (post-Phase 1)

UX refinements deferred until all 25 build prompts complete. Don't action
during build — log here, address in one focused polish pass.

### Entity UX
- Demote "Entities" from primary sidebar to Settings/Admin section.
  In daily operations SY Homes staff don't think of themselves as working
  for three separate companies; it's one team. Entity structure is plumbing,
  not foreground. Keep data model exactly as built (required for VAT, CT,
  lender reporting, ringfenced liability) — just tone down UI prominence.
- Auto-derive entity on cost postings from project (and linked ConstructionCo
  for construction costs). Don't require manual entity selection in common
  cases.
- Default dashboards to unified "Group" view; entity breakdown as optional
  filter, not default display.
- Keep entity exposure in finance/Xero flows (where Louise and the accountant
  genuinely care) and at project setup (set once, forgotten).

### Brand polish
- Apply SY Homes brand palette: orange #E85A1B (primary accent),
  navy #1F2D3D (primary dark).
- Select and apply production font stack.
- Unified component styling pass across all 10 modules.

### Audit UX (post-1.4)
- Per-record Audit Trail tab on /users/:id and /entities/:id. API endpoint supports
  the query (`GET /audit?resource_type=...&resource_id=...`); only the tab UI is missing.
  Today users filter from the global /audit page.
- Actor / entity / project picker widgets in /audit filter bar (currently free-text UUIDs).

### Project module (post-1.5)
- Revisit stage machine — hard-coded FORWARD_TRANSITIONS dict in `app/services/project_stage.py`.
  Move to `system_config` once 1.7 lands so rules tune without deploy. Also consider allowing
  Sales and Post_Completion concurrently (developers sell while mobilising the next phase).
- `ProjectDetail.jsx` is 788 lines — split `AdvanceStageModal`, `OverrideStageModal`, `TeamTab`,
  `AuditTab` into separate files.
- `update_project` uses raw-body read to reject `project_code` mutations because `ProjectUpdate`
  schema doesn't expose the field. Cleaner: add `project_code` to the schema with a validator
  that raises on presence. Safer against upstream middleware changes.
- `derive_planning_expiry` uses `date.replace(year=...)` which throws on Feb 29 approvals.
  Fix with `dateutil.relativedelta` or try/except fallback to Feb 28.

### Test infra (post-Patch #2)
- `pyproject.toml` lives at `/app/backend/pyproject.toml` not repo root. If a future top-level pyproject.toml is added (e.g. for monorepo packaging), pytest discovery may resolve to the wrong one. Add a comment in the file or a CI assertion.

### 2026-04-20 — Scope expansion decision: full company OS

After completing Prompts 1.1 and 1.2, paused to clarify the long-term
vision. Decision made: SY Hub is to become a full company operating
system covering site operations (daily logs, clocking, chat, QA
checklists, contractor/labourer portals), not only the financial-
control platform the original 25-prompt brief described.

Implications:
- Build expands from 25 prompts to ~35-40 prompts
- Realistic timeline: 10-14 months at 20-25 hours/week (was 4-6 months)
- Realistic cost: £8-15k including possible designer + Xero developer
- Foundation track (Prompts 1.3 through 1.7) continues as specced
- Tracks 2-5 to be re-specced after Foundation complete
- Commercial decision: build for SY Homes only, accept rebuild cost
  if commercialised later (Rhizzo-ai)

See SY_Hub_Scope_Expansion_Memo.md for full details.

Project Instructions document also created (held in Claude Project,
not in this repo) governing how Claude operates across all future
chats in the project.

## Prompt 1.2 — Users, Roles, Permissions (CLOSED)

**Built:**
- Argon2id password hashing, TOTP MFA, JWT auth
- 10 seeded roles, 87 permissions
- Bootstrap super_admin
- Login, MFA challenge, password change, profile security
- 135/135 backend tests passing

**Close-out patches:**
- Patch #1: Password complexity (upper/lower/number/symbol), admin unlock UI, lockout policy confirmed (5 attempts → 15/30/60 min escalating, counter resets on success)
- Patch #2: Edit user UI (name, email, phone, status; gated on users.admin; email collision → 409; self-deactivation blocked)

**Deviations from spec:**
- Password history check (≠ last 5) added — not in original spec, sensible
- Interim audit via `admin_notes` stamps (proper audit_events deferred to 1.4)
- TOTP ±1 step window kept (RFC 6238 standard, ~30s grace)

**Deferred to later prompts:**
- Forgot-password + admin password-reset → 1.3 (shares email/token infra with invitations)
- Email delivery of invitations → 1.3
- Audit log promotion → 1.4
- Manual lock button → 1.4

**Deferred to Polish Pass:**
- HIBP breach check on passwords
- Roles & Permissions management UI
- Company/contact detail fields (belong to supplier/subbie records in Track 2)

**Known gaps acceptable at this stage:**
- No role/permission editing UI (use seed file + redeploy)
- Invitations require manual token copy-paste until 1.3 wires email


## Prompt 1.3 — Sessions, Login History, Invitations, SSO, API Keys (IN PROGRESS)

Scope proved larger than a single Emergent build cycle. Staged delivery:

**Stage 1 (this session):**
- Session management (JWT access 15min + opaque refresh 30d/90d remember-me, rotation, replay detection)
- Idle timeout (60 min)
- Retroactive rewire of 1.2 auth to new token model
- Login history table (append-only, 2+ year retention)
- /profile/sessions, /users/:id/sessions, /users/:id/login-history UIs
- Email infrastructure (EmailProvider abstraction + ConsoleEmailProvider default; SendGrid implementation drafted but commented out pending credentials — ConsoleEmailProvider is the only active provider)
- Password reset flow: self-service + admin-initiated
- /forgot-password + /reset-password UIs
- Geolocation via MaxMind GeoLite2 (fallback to NULL country if .mmdb absent)
- In-process rate limiting on login + password reset endpoints
- Fernet encryption key **required via `MFA_ENCRYPTION_KEY` env var — backend refuses to start without it. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and store in `.env` before first boot. Losing the key renders stored MFA secrets un-decryptable.**

**Deferred to Stage 2 (next session):**
- Email-delivered invitations (Section E)
- SSO: Google, Microsoft, Apple (Section G) — Microsoft primary test provider (SY Homes is M365-heavy)
- API keys for service accounts (Section H)
- Suspicious activity detection: new-country alerts, impossible travel (Section I)
- /invitations, /api-keys, /profile/security/sso UIs

**Deliberate deferrals (unchanged):**
- HIBP breach check → Polish Pass
- WebAuthn / FIDO2 → Phase 6
- SMS/Email MFA → Prompt 1.7
- IP allow-listing → Future Tasks
- Manual lock button → 1.4
- Role/permission management UI → Polish Pass

### 2026-04-22 — Prompt 1.3 Stage 1b close-out patch (audit remediation) ✅

**Four audit findings closed in a single build cycle:**

- **(I6) MFA enforcement honours role expiry** — `_most_senior_enforced_role`
  now filters `user_roles` on `(status='Active' AND (expires_at IS NULL OR
  expires_at > now()))`, aligning MFA gate with `compute_effective_permissions`.
  An enforced role that has expired no longer forces the user into MFA
  enrolment on login.

- **(M8) CORS startup guard** — `_resolve_cors_origins()` in `server.py`
  raises `RuntimeError` when `CORS_ORIGINS` is empty or contains `*`.
  Paired with `allow_credentials=True`, a wildcard origin is a classic
  CSRF footgun; the server now refuses to start rather than quietly
  serving a permissive policy.

- **(I3) Rate-limit bypass hardening** — `SYHOMES_RATE_LIMIT_DISABLED=1`
  is only honoured when `APP_ENV=test` is also set. A stray disable flag
  in production logs at `ERROR` and leaves the limiter active. `.env`
  now explicitly sets `APP_ENV=test` for the dev pod.

- **(C1, critical) Frontend auth moved to HttpOnly cookies** — access and
  refresh tokens no longer appear in ANY JSON response body. `/auth/login`,
  `/auth/refresh` (now 204), and `/auth/mfa/enroll/confirm` set and rotate
  cookies server-side; frontend runs with `withCredentials: true` and zero
  localStorage token state. Bearer fallback removed from `_extract_token`
  — a successful XSS can no longer exfiltrate a bearable session.

**Backend residuals discovered and fixed during the patch:**

- `/auth/refresh` was crashing (`AttributeError: 'RefreshRequest' object
  has no attribute 'refresh_token'`) because an earlier C1 patch stripped
  the field from the Pydantic model but left `payload.refresh_token` in
  the handler. Endpoint now reads `request.cookies.get("refresh_token")`,
  returns 401 + a `Refresh_Failed` login-history row on missing cookie.
- `MfaEnrollConfirmResponse` still exposed `access_token`/`refresh_token`
  in the body; replaced with `{backup_codes, session_issued}`.
- `LoginResponse.mfa_pending_token` field removed; the pending JWT rides
  only via the `access_token` cookie. Frontend detects pending state via
  `mfa_enrollment_required: true` + `enforced_role_name`.
- `LoginResponse`/`RefreshResponse` constructor calls cleaned up to stop
  passing kwargs the Pydantic models don't declare (silently dropped).

**Frontend rewrite** (`/app/frontend/src/`):
- `lib/api.js` — no localStorage, no Bearer interceptor, 204-aware refresh,
  `authedFetch` helper for blob downloads.
- `context/AuthContext.jsx` — hydrates `me` from login body; `/auth/me` only
  called once on boot for cookie-survival detection.
- `pages/ForcedMfaEnroll.jsx` — drops token read from enrol-confirm body.
- `pages/AdminLoginHistory.jsx` — CSV export via cookie-based fetch.

**Test suite migrated to cookies-only** (`/app/backend/tests/`):
- `conftest.py::login_with_auto_enroll` now returns a `requests.Session`
  with cookies set instead of a raw bearer string. New `plain_login` helper
  for non-MFA roles. Session jars model the production frontend.
- All seven prior test files migrated: `test_auth_rbac.py`,
  `test_entities_api.py`, `test_mfa.py`, `test_mfa_gap_closure.py`,
  `test_password_complexity.py`, `test_sessions_history_reset.py`,
  `test_user_edit.py`. `test_insurance_alerts.py` unchanged (no auth).
- **+19 new regression tests** in `tests/test_audit_remediation.py`:
  Patch 1 (2), Patch 2 (4), Patch 3 (4), Patch 4 (4), residuals (5).

**Full suite: 179 passed, 0 failed, 0 skipped** (was 160 → +19).

**Deliberately simplified:** None.

**Production deployment notes:**
- Set `APP_ENV=production` (not `test`) — this flips cookie `Secure=True`
  and ensures the rate-limit disable flag is inert.
- `CORS_ORIGINS` must list explicit origins, no `*`.

**Preview environment caveat:**
- The Emergent preview uses an ephemeral Postgres. Pod cycles wipe the
  DB including MFA enrolment, forcing re-enrolment when users return.
  Not a bug — production deployment requires persistent storage
  (managed Postgres / RDS / equivalent).

  ---

### 2026-04-22 — Schema and design notes (audit-driven corrections)

**Schema note — `user_sessions.access_token_jti`:**
Stores the JWT ID claim as a session-to-token binding, not a hash of the access token. The JWT is already signed by `JWT_SECRET` and therefore tamper-proof without needing a DB hash; the JTI lets us revoke specific access tokens by session. The original Prompt 1.3 brief specified `access_token_hash`; the JTI approach is a deliberate simplification with equivalent security properties.

**Schema additions not previously documented (Prompts 1.2 and 1.3):**
- `users.email_verified_at` (timestamp, nullable)
- `users.phone_verified` (boolean, default false)
- `users.avatar_url` (text, nullable)
- `users.lockout_level` (int, default 0) — drives 15/30/60 min escalation
- `users.mfa_enforced_at` renamed to `users.mfa_enrolled_at` (migration 0003)
- `user_sessions.previous_refresh_token_hash` — for single-hop replay detection
- `user_sessions.remember_me` (boolean) — extends refresh TTL to 90 days when true
- `user_sessions.location_latitude`, `user_sessions.location_longitude` (decimal) — MaxMind geo data
- `user_login_history` event_type enum expanded with `Refresh_Success`, `Refresh_Failed`, `SSO_Link`, `SSO_Unlink`, `Impersonation_Start`, `Impersonation_End`, `Session_Revoked`, `Suspicious_Activity_Detected` (most Stage 2 values pre-seeded)

### 2026-04-23 — Prompt 1.4: Audit Log ✅

**Single-cycle build: table, service, retrofits, UI, retention, tests.**

- **New table `audit_log`** (migration 0006). Columns per spec: actor, impersonator,
  action (enum of 12), resource_type + resource_id, entity_id + project_id,
  field_changes JSONB, metadata JSONB, IP, UA, session_id, created_at. Six
  indexes. Append-only via DB trigger. `metadata` column stored as `metadata_json`
  at the SQLAlchemy layer (framework reserves the former); API surface uses
  `metadata` unchanged.

- **Trigger update (migration 0007)** — append-only enforcement now admits
  `pg_trigger_depth() > 1` (FK-cascade SET NULL). Direct UPDATE/DELETE still
  raise "audit_log is append-only"; FK-driven nil-outs succeed. Discovered
  during first retrofit test (entity delete with audit rows referencing it).

  **Implication:** when an entity or session is deleted, its associated audit
  rows retain `resource_type`/`resource_id` but lose `entity_id`/`session_id`
  via FK SET NULL. The audit row itself is never deleted; its cross-reference
  context just narrows. Filter by `resource_type='entities' AND resource_id=X`
  to find history of a deleted entity rather than `entity_id=X`.

- **`app/services/audit.py`**:
  - `record_audit(db, *, action, resource_type, resource_id, ...)` — primary
    entrypoint. Never raises; audit-write failures logged at ERROR and swallowed
    so business writes survive. Extracts IP / UA / session_id /
    impersonator_user_id from `request.state`.
  - `field_diff(before, after)` — ordered, sorted, unchanged-elided.
  - `SENSITIVE_FIELDS` constant + `_redact()` — password hashes, MFA secrets,
    token hashes, invitation / reset tokens replaced with `[REDACTED]` in both
    old and new values.
  - `stamp_self_approval(metadata, actor, submitted_by)` — pure helper for
    Track 2+ approval flows; sets `metadata.self_approval = True` when actor ==
    submitter.
  - Module docstring documents retention policy + approval discipline +
    impersonation contract for future prompt authors.

- **Retrofit wiring** (13 write points across 4 routers): entities
  Create/Update/Delete; users edit + admin unlock + role assign/revoke; auth
  Login (MFA and non-MFA), Logout, password change, password reset complete,
  MFA enrol/disable/regenerate; sessions self-revoke, revoke-others, admin
  revoke-all. Refresh is deliberately NOT audited (stays in login_history only
  for security forensics). Existing `admin_notes` stamps from Prompts 1.2/1.3
  kept intact alongside audit rows.

- **Permissions**: `audit.view`, `audit.view_sensitive`, `audit.export`,
  `audit.admin` seeded. Super_admin: all. Director: view + export scoped.
  Finance: view scoped. Other roles: none.

- **Router `/api/audit`**:
  - `GET /audit?page=&page_size=&resource_type=&resource_id=&actor_user_id=&entity_id=&project_id=&action=&date_from=&date_to=`
  - `GET /audit/{id}`
  - `GET /audit/export.csv`, `GET /audit/export.json` — 10k row cap with
    explicit 400 when exceeded; additive `audit.export` required.
  - Scope filter: `audit.admin` → unscoped; else scoped by user's
    effective_entity_ids. Tenant-level rows (null entity_id: login / user-level
    / system) visible to everyone with `audit.view`.

- **Frontend `/audit`**: paginated list with action-pill filter bar, resource-
  type + date-range filters, detail modal (field_changes table + redacted
  values + metadata JSON + impersonation banner), CSV export. Nav link
  permission-gated. Per-record Audit Trail tabs on /users/:id and /entities/:id
  NOT built this cycle — global page filtered by resource_type + resource_id
  provides equivalent data (logged to Polish Pass).

- **Retention (`audit_retention.py`)**: OFF by default, dry-run default,
  empty allow-list no-op, 7-year hard floor. Bypass via
  `ALTER TABLE audit_log DISABLE TRIGGER USER` inside the purge transaction
  (app DB user owns the table, no superuser required). Scheduler wiring
  deferred until 1.6 / 1.7.

- **Tests**: +42 in `tests/test_audit_log.py`. Append-only enforcement,
  service correctness, sensitive redaction, impersonation pickup, retrofit
  smoke (entity CRUD / user edit / admin unlock / password change / login /
  refresh does NOT audit / logout DOES audit / session revoke / MFA enrol),
  API filtering + scoping, CSV/JSON export, retention purge disabled-by-default
  + dry-run + allow-list + 7-year floor.

**Full suite: 179 → 221 passed (+42), 0 failed, 0 skipped.**

**Deliberately simplified:**
- Per-record Audit Trail tab on /users/:id and /entities/:id (global /audit
  filtered by resource_type + resource_id gives equivalent data; dedicated
  tab is UI polish for next iteration).
- Actor / entity / project picker widgets in the filter bar (accept UUIDs via
  backend query params; UI inputs are free-text for resource_type + action
  pills for actions).
- Revoke-others emits one audit row per session (intentional — forensic
  fidelity over row-count efficiency).

### 2026-04-23 — Prompt 1.5: Projects + Project Team Members ✅

### Schema (Alembic 0008, 0009)
- **New table** `projects` — unit-of-truth for development sites. 30+ columns spanning
  identity (project_code, name, type, parent_project_id, primary/construction_entity_id),
  site (address, postcode, local authority, ha/acres), tenure, planning
  (ref/type/status/approval/expiry, implementation/S106/CIL flags), targets (units, dates,
  affordable_housing_pct), stage machine (current_stage + stage_entered_at), status
  (Active/On_Hold/Dead/Complete with dead_reason), cached financials (gdv/build_cost/
  all_in_cost/profit/margin + financials_refreshed_at), project_lead_user_id,
  created_by_user_id, notes. 4 indexes + partial `ix_projects_planning_expiry_candidates`
  for the sweep.
- **New table** `project_team_members` — project/user/role junction with `is_primary`,
  `assigned_by_user_id`, `assigned_at`, `removed_at` (soft), and a partial unique
  `ux_team_one_active_primary_per_role` enforcing one active primary per (project, role).
- **Retroactive FKs** (0009):
  - `user_role_projects.project_id → projects.id ON DELETE CASCADE` (deferred from 1.2)
  - `audit_log.project_id → projects.id ON DELETE SET NULL` (deferred from 1.4)
- `updated_at` trigger wired on both new tables.

### Backend
- Auto-generated project codes: 3-char alphanumeric prefix from name + 3+ digit sequential
  counter (e.g. `SHR-001`). Overrides accepted if they match `^[A-Z0-9]{3}-\d{3,}$`.
  Immutable after creation (409 on duplicate; raw-body rejection on PUT).
- Site area reconciliation: ha ↔ acres at 4dp; ha wins when both supplied. Null pair
  remains null.
- Planning expiry auto-calc: +3y for Full / Outline / Hybrid / Permitted_Dev /
  Prior_Approval; +2y for Reserved_Matters. Manual overrides stamp
  `metadata.planning_expiry_manual_override=true` in audit.
- **Hard-coded forward-only stage machine** (`app/services/project_stage.py`):
  Lead → Appraisal → Deal_Pipeline → Planning → Pre_Con → Construction →
  {Sales, Post_Completion} → Closed, with Dead as an allowed target from any active
  stage. Status auto-syncs (Dead → Dead, Closed → Complete).
- Super_admin stage override: min 10-char reason, director_notifications payload
  written to audit metadata, atomically flips status on Dead/Closed/recovery paths.
  Explicit super_admin gate — not inherited from `projects.edit`.
- Project team management: add/remove/list with `?history=true` toggle, primary
  Project_Lead syncs to `projects.project_lead_user_id` (nulls on removal).
- Cached financials refresh stub: returns zeros + stamps timestamp. Gated on
  `projects.view_sensitive`. Real rollup arrives Prompts 2.5 + 2.7.
- Planning expiry sweep: daily 07:00 UTC APScheduler cron. Fires at day thresholds
  {365, 180, 90, 30, 0} and every day past expiry. Payloads logged today; insertion
  into `notifications` lands with Prompt 1.7.
- Delete hook: `has_project_dependents()` currently a no-op; one-place extension for
  future tables (appraisals, budgets, actuals, commitments, budget_changes,
  cash_flow_entries, programmes, documents, compliance_registers, xero_*).
- RBAC: added 7 project permissions (view, view_sensitive, create, edit, delete,
  approve, admin). Director/super retain full coverage; project_manager gets
  create/edit/view_sensitive. Strict scoping via
  `user_role.project_scope ∈ {All, Specific, None}` on list + detail.

### Frontend
- `/projects` list — search (name/code/address/postcode), multi-select filters
  (type, stage, status), margin% column gated on `projects.view_sensitive`,
  pagination, filter chips, empty state with permission-gated CTA.
- `/projects/new` — required-field validation, symmetric ha↔acres live conversion,
  planning expiry auto-fill preview (+3y/+2y per type), route redirects away when
  `projects.create` is missing.
- `/projects/:id` — header with stage badge + dead-banner, per-stage action buttons
  reflecting `FORWARD_TRANSITIONS`, Dead button opens reason-required modal,
  super_admin-only Override button (10-char reason validated both sides), delete
  gated on `projects.delete`.
- Overview tab: 5 collapsible sections (Summary, Site, Planning, Targets,
  Financials). Financials section renders only with `projects.view_sensitive` and
  carries a Refresh button + "last refreshed" stamp.
- Team tab: list (with removed-members toggle), Add Team Member modal (user +
  role + is_primary), soft Remove, primary marker (★).
- Audit tab: pulls `/api/audit?project_id=…`, explicit 403-forbidden message for
  users lacking `audit.view`, deep-link to full `/audit` page.

### Tests
- **+93 pytest cases** in `tests/test_projects.py` covering: project code gen +
  override validation + duplicates + immutability; ha↔acres round-trip + NULL;
  planning expiry auto-calc (Full/Outline/Reserved_Matters/missing); manual
  override audit flag; stage advance (init, forward, cannot-skip, cannot-reverse,
  walk-to-closed, Dead-from-any, Dead-without-reason); super_admin override
  (permission gate, 10-char validator, same-stage reject, Dead-reason requirement,
  audit metadata + director_notifications payload, reactivates Dead projects);
  team CRUD (unique active primary, role validation, unknown user, project_lead
  sync on primary add/remove, idempotent remove, cross-project 404); audit
  diff (no-change = no-audit, manual-override-flag); RBAC (401/403 matrices,
  readonly/director/finance financial visibility, pagination, search, stage +
  entity filters); delete (204, 404, audit row project_id cascade-set-null);
  planning expiry sweep thresholds (30/100/past/non-active/started skips);
  financials refresh stub (super 200, readonly 403, timestamp stamped);
  retroactive FK existence + delete cascade behaviour; unit tests on every
  service helper.
- Suite total: **314 passed / 1 skipped / 0 failed** (was 221 → +93).

### Known deviations
- **Stage machine is deliberately hard-coded forward-only** with a super_admin
  override, not the "non-sequential allowed but flagged" spec wording. Property
  development is genuinely linear and stray stage clicks make forensic work
  painful.
- Financials refresh returns zeroes pending Prompts 2.5 (actuals) + 2.7 (cash flow).
  The endpoint and UI wiring exist so the stale-indicator + refresh button work
  today.
- Director stage-override notifications are recorded in audit metadata today;
  actual delivery arrives with the `notifications` table in Prompt 1.7.

### 2026-04-23 — Audit Remediation Patch #2 ✅

Pre-existing audit-coverage gaps surfaced by Claude Code's review of
Prompts 1.4 + 1.5. None introduced by 1.5; all five fixes ship together.

**I1 — User invite endpoint now writes an audit row**
- `POST /api/users` previously committed a new user row with
  `status='Pending_Invitation'` without recording anything in
  `audit_log`. Forensic blind spot since Prompt 1.2.
- Wired `record_audit(action='Create', resource_type='users')` between
  `db.flush()` and `db.commit()` so the user and audit rows commit
  atomically. `field_changes` carries `email`, `user_type`,
  `primary_entity_id`, `status`. Sensitive token / credential columns
  deliberately omitted (NULL or random invitation token at this point —
  neither belongs in audit). Metadata stamps `action='invite'` and
  `invited_by`.
- Endpoint now takes `request: Request` so IP / user-agent are captured
  on the audit row.

**I2 — PII scrub endpoint now writes an audit row before scrubbing**
- `POST /api/users/{id}/scrub_pii` is the most destructive single
  endpoint in the system (GDPR right-to-erasure). It now records a
  `Delete` audit row BEFORE the scrub runs, so an investigator can
  reconstruct that a scrub happened and who performed it, without ever
  exposing the scrubbed PII to the audit log.
- `field_changes` lists every scrubbed column (email, first_name,
  last_name, display_name, phone, avatar_url, job_title,
  primary_entity_id, user_type, status_before) with both `old` and
  `new` set to the literal string `"[SCRUBBED]"`. The pre-scrub values
  exist only in a transient Python dict that goes out of scope as soon
  as the audit row is built.
- Metadata records `action='pii_scrub'`,
  `gdpr_basis='right_to_erasure'`, `preserves_fk_integrity=true`.
- Endpoint now takes `request: Request` for IP / UA capture.

**I3 — Bank fields and UTR added to `SENSITIVE_FIELDS`**
- Entity audit diffs previously carried `bank_name`,
  `bank_account_name`, and `bank_account_number_masked` in cleartext.
  All three now in the redaction set. The masked column is already
  partially obscured at write time (`****1234`); redacting it
  consistently in audit diffs simplifies the rule and defends against
  a future write-path bug that might bypass the mask.
- Residual discovered during the schema sweep: `entities.utr` (UK
  Unique Taxpayer Reference) is sensitive PII for sole traders /
  partnerships and commercially sensitive for SPVs / JV vehicles.
  Added to `SENSITIVE_FIELDS` in the same patch.
- Lock test `test_sensitive_fields_set_includes_banking_and_utr`
  asserts the redaction set contents so future PRs cannot quietly
  remove these.

**M1 — `audit_log_no_modify` carve-out documented in-line**
- Added migration `0010_audit_trigger_comment` that
  `CREATE OR REPLACE`s the trigger function with a block comment
  explaining the `pg_trigger_depth() > 1` carve-out's safety boundary:
  the carve-out only admits FK referential actions, and any future
  trigger that mutates `audit_log` rows from another trigger context
  would silently bypass the append-only guard.
- Behaviour byte-identical pre and post; the comment is visible via
  `\df+ audit_log_no_modify`.
- Mirroring application-side comment added in
  `app/services/audit_retention.py` at the `DISABLE TRIGGER USER`
  call site.

**M7 — Bare `pytest` invocation now works**
- `tests/conftest.py` uses `from tests.conftest import …` style imports.
  Without `/app/backend` on `sys.path`, bare `pytest tests/` failed with
  `ModuleNotFoundError: No module named 'tests'`.
- Added `/app/backend/pyproject.toml` with three-line
  `[tool.pytest.ini_options]` block (`pythonpath = ["."]`,
  `testpaths = ["tests"]`, `addopts = "-q --tb=short"`).
- README updated with a "Running tests" section showing the bare
  invocation. `python -m pytest` continues to work and remains the
  preferred CI form.

**Tests**
- +7 new in `tests/test_audit_remediation_patch_2.py`. Suite total:
  314 → **321 passed**, 0 failed, 0 skipped (the previous 1 skipped
  was a pre-3.11 guard now running on Python 3.11).

**Files touched**
- `app/routers/users.py` — invite + scrub_pii rewired (request +
  record_audit + pre-scrub capture).
- `app/services/audit.py` — `SENSITIVE_FIELDS` += `{bank_name,
  bank_account_name, bank_account_number_masked, utr}`.
- `app/services/audit_retention.py` — safety-boundary comment.
- `alembic/versions/0010_audit_trigger_comment.py` — new (no-op
  behaviourally; embeds documentation in the live function).
- `pyproject.toml` — new (pytest config).
- `README.md` — Running tests section.
- `tests/test_audit_remediation_patch_2.py` — new (7 tests).

**Deliberately simplified**
- `bank_account_number_masked` is redacted in audit even though it's
  already masked at write time. Trade-off: simpler one-line redaction
  rule and defence-in-depth against a future masking bug, at the cost
  of slightly less informative diffs (`[REDACTED] → [REDACTED]`
  instead of `****1234 → ****8901`).
- No retroactive backfill of `audit_log` for invites and PII scrubs
  that pre-dated this patch. Going forward only.
- No new endpoints, no behavioural schema changes. 0010 is a
  pure-documentation `CREATE OR REPLACE`.
- `pyproject.toml` lives at `/app/backend/pyproject.toml`, not the repo
  root. If a future top-level `pyproject.toml` is ever added (e.g. for
  monorepo packaging), pytest discovery may resolve to the wrong one.
  Logged to Polish Pass.

### 2026-04-24 — Prompt 1.6 — Cost Codes ✅

Reference data for the financial spine. Built before any module that posts costs (appraisals, budgets, actuals, commitments, cash flow) so they all reference a stable catalogue.

**Schema (Alembic 0011, 0012, 0013, 0014):**
- 5 new tables: `cost_code_sections`, `cost_codes`, `project_cost_codes`, plus supporting structures.
- 9 sections seeded from `SY_Homes_Cost_Codes.xlsx` source spreadsheet.
- 133 cost codes seeded across the 9 sections.
- Codes follow `{PREFIX}-{NNN}` format (3-char alphanumeric prefix from section, zero-padded sequence). Codes are immutable post-use; cosmetic + entity-routing fields remain editable.
- Retire-with-`replaced_by_code_id` pattern: codes can be retired pointing at a successor; never hard-deleted. Same pattern likely to recur for other catalogues.

**Backend:**
- `app/services/cost_codes.py` — section + code services with section/code validation, immutability checks against `is_cost_code_in_use()`, retire-with-replaced_by, idempotent seed.
- `is_cost_code_in_use()` currently checks `project_cost_codes` only. TODO comments mark Phase 2 join points (appraisals 2.2, budgets 2.4, actuals + commitments 2.5).
- Bulk seeds emit one summary audit entry per run (`metadata.kind='seed_run'`), not per-row.
- 18 endpoints across `/api/cost-codes` and `/api/cost-code-sections` (list, get, create, update, retire, project assignment).

**Frontend:**
- `/cost-codes` admin page — sectioned list with inline edit, retire flow, retired-toggle, project-scope view.

**Permissions:**
- Pre-1.6 baseline: 87. 1.6 added 2 (`cost_codes.view`, `cost_codes.admin`). Catalogue had also defensively pre-seeded `cost_codes.create / .edit / .delete` from earlier prompts; those remain orphan and are flagged for the end-of-Foundation audit (Patch #3).

**Tests:**
- +73 in `tests/test_cost_codes.py`. Schema, seeds, immutability lock, retire pattern, project assignment, audit wiring, RBAC.
- Suite total: 321 → 394 passed / 0 failed / 0 skipped.

**Deliberately simplified:**
- Xero account mapping deferred to Track 5 (Xero integration). The column exists on `cost_codes` but is null at seed.
- No per-project custom codes — catalogue is closed. Add via Polish Pass if a project genuinely needs a one-off.
- Hierarchy is flat: section → code, no sub-sections.

**Spec deviations:**
- Spec mentioned 11 sections / ~120 codes; actual seed from the source spreadsheet is 9 sections / 133 codes. Source spreadsheet is canonical.
- SER-06 vs SER-10 surfaced as duplicate lift installation codes from the source spreadsheet. Both seeded as-is; flagged for end-of-Foundation audit (one to be retired pointing at the other).

**Residuals (flagged for Patch #3):**
- Orphan `cost_codes.create`, `cost_codes.edit`, `cost_codes.delete` permissions.
- SER-06 / SER-10 duplicate to be reconciled via retire-with-replaced_by.
- Audit log action enum compromise: bulk seeds use `action='Create'` plus `metadata.kind='seed_run'`. Reconsider whether to add `Bulk_Insert` / `Bulk_Toggle` / `Seed_Run` as first-class enum values.

---

### 2026-04-25 — Prompt 1.6 Patch 1.6.1 — seed_rbac role-grant verification ✅

Audit of `seed_rbac.py` after 1.6 ship found that cost_codes was added to `PERMISSION_CATALOGUE` but the role-permission grants were only added to migration 0014, not to the `ROLE_PERMISSIONS` dicts in `seed_rbac.py`. This meant migration 0014 was the only source of those grants, and any fresh-boot / new-tenant / re-seeded scenario would silently drop the grants for non-wildcard roles.

Tests passed because migrations run during test setup. But seed_rbac is supposed to be idempotent and authoritative — it wasn't.

**Fix:**
- `seed_rbac.py` updated so `ROLE_PERMISSIONS` dicts include the cost_codes grants directly. Migration 0014 retained as historical record.
- Idempotent on existing migrated DBs: re-running seed produces no changes.
- Fresh-boot scenarios now grant correctly without needing migration 0014 to be the source of truth.

**Tests:**
- +8 lock tests in `tests/test_seed_rbac_locks.py` asserting that `ROLE_PERMISSIONS` contents match expected grants for cost_codes (and existing 1.2 / 1.4 / 1.5 grants). Catches future drift between seed_rbac and migration history.
- Suite total: 394 → 402 passed / 0 failed / 0 skipped.

**Deliberately simplified:**
- No retroactive consolidation of migration 0014 into seed_rbac as the single source of truth. Migration stays as historical record; seed_rbac is now also authoritative going forward.

---

## [0.7.0] — Prompt 1.7 — System Config + Notifications — 2026-04-26

### Added
- `system_config` table (Alembic 0015) — typed key/value store with `default_value` snapshot column for /restore. Categories enum extended with `Audit` and `System`.
- `system_config` 38-key seed (`app/seed_system_config.py`, called from lifespan after `seed_rbac`) across 9 populated categories: Finance(3), Appraisal(8), Budget(5), Programme(4), Security(7), Integration(2), Notification(5), Reporting(2), Audit(2). One summary audit row per seed run.
- `notifications` table (Alembic 0015) — 15-type × 4-priority enums, 22 columns, 3 indexes incl. partial on `expires_at IS NOT NULL`, `ON DELETE CASCADE` on `recipient_user_id`.
- `app/services/system_config.py` — singleton with thread-safe in-memory cache, typed `_parse`/`_serialise`, `get`/`get_or_default`/`set_value`/`restore`/`invalidate`/`list_all`. `_query_count_for` exposed for tests.
- `app/services/notifications.py` — `dispatch(...)` (synchronous) + `safe_dispatch(...)` (never raises into business path). Defaults `expires_at` to `now + notification.auto_expire_days`. Email via existing `ConsoleEmailProvider` for High|Critical only. SMS branch logs `# TODO[SMS]` (scaffolded). Records audit Create.
- `app/services/notification_grouping.py` — read-time bucket-by-(type, hour-bucket) with config-driven threshold and window.
- `app/routers/system_config.py` — under `/api/v1/system-config`: GET list grouped, GET one, PUT, POST restore.
- `app/routers/notifications.py` — under `/api/v1/notifications`: GET inbox (filters+pagination), GET unread (lazy-grouped, 50 cap), GET unread-count, PATCH read, PATCH dismiss, POST mark-all-read.
- New API mount: `APIRouter(prefix="/v1")` containing `system_config` + `notifications` mounted under `/api`. Pre-existing `/api/*` routes untouched.
- `app/jobs/notification_expiry.py` — APScheduler BackgroundScheduler, daily 03:00 UTC bulk dismiss with one summary audit row.
- `app/jobs/audit_retention.py` — APScheduler BackgroundScheduler, daily 03:00 UTC, gated by `audit.retention_purge_enabled` (default false). Calls existing `purge_old_audit_rows`; 7-year hard floor enforced inside the purge module.
- `lifespan(...)` in `server.py` now calls `seed_system_config_role_grants()` then `seed_system_config()` after `seed_rbac()`, and starts/stops both new schedulers cleanly.
- Frontend pages: `src/pages/ConfigPage.jsx`, `src/pages/NotificationsPage.jsx`. Frontend component: `src/components/NotificationBell.jsx`. Routes wired in `src/App.js`. Navbar item + bell injected in `src/components/AppShell.jsx`. All elements carry `data-testid`.
- Tests: 55 new across `tests/test_system_config.py`, `tests/test_notifications.py`, `tests/test_scheduler_jobs.py`, `tests/test_retro_wires.py`. Total suite 457 passing.

### Changed
- `app/seed_rbac.py` — `ROLE_PERMISSIONS["director"]` now also excludes `system_config.admin` and `system_config.edit` (super_admin-only per spec). Director permission count: 84 → 82.
- `app/seed_system_config.seed_system_config_role_grants()` — grants `system_config.view` to all 10 roles AND revokes any pre-existing non-super_admin grants of `system_config.{admin,edit}` (one-shot cleanup; idempotent).
- `app/scheduler.py::planning_expiry_sweep` — now dispatches `Deadline_Approaching` notifications (priority Critical past expiry, High ≤30d, Normal otherwise) to project_lead + scoped/unscoped directors, in addition to returning the existing payload list.
- `app/jobs/insurance_alerts.py::_emit_alert` — calls `_dispatch_insurance_alert` to send `Insurance_Expiry` notifications (Critical at expired/0_day, High otherwise) to directors with view access to the entity. Best-effort; never blocks the alert loop.
- `app/routers/projects.py` stage override — dispatches `System_Announcement` priority High to all directors (excluding the actor super_admin) on top of the existing audit metadata.
- `app/routers/auth.py` — password reset request, MFA enrol confirm, MFA disable now each dispatch a `Security_Alert` priority High to the affected user.
- `tests/test_auth_rbac.py::test_roles_returns_10_seeded_roles` — updated assertions for post-1.7 role counts: read_only 9, investor_read_only 4, subcontractor_portal 3, consultant_portal 4, director 82.
- `app/services/system_config.invalidate(...)` — preserves the cumulative DB-hit counter across invalidations (test diagnostic only).

### Retro-wires (TODO[NOTIFY] closed)
- ✅ Planning expiry sweep → `Deadline_Approaching` to project_lead + directors. (`app/scheduler.py`)
- ✅ Stage override → `System_Announcement` priority High to all directors. (`app/routers/projects.py`)
- ✅ Insurance `_emit_alert` → `Insurance_Expiry` priority High (Critical at expired/0-day) to directors with view access. (`app/jobs/insurance_alerts.py`)
- ✅ Password reset request → `Security_Alert` priority High to user. (`app/routers/auth.py`)
- ✅ MFA enrol confirm → `Security_Alert` priority High to user. (`app/routers/auth.py`)
- ✅ MFA disable → `Security_Alert` priority High to user. (`app/routers/auth.py`)
- ✅ Login-from-new-device — confirmed deferred to 1.3 stage 2; not yet present in code, no retro-wire required.
- Post-build grep for `TODO[NOTIFY]` and known siblings (`TODO: notify`, `notification placeholder`, `notification stub`, `notification scaffolded`, `Prompt 1.7 will`, `Prompt 1.7 lands`): **ZERO hits**.

### Spec deviations
- **Endpoints under `/api/v1/...` while existing app uses `/api/...`** — followed the spec verbatim. Pre-existing `/api/*` routes are untouched. Polish Pass entry to migrate older modules to `/api/v1` on a per-prompt basis.
- **`system_config` extra column `default_value`** — required to support the spec's "Restore to default" UI without re-running seed. Snapshotted at insert time.
- **`system_config_category` enum extended with `Audit` and `System`** — needed to host `audit.retention_*` keys.
- **Permission count delta = 0, not +2** — spec said "+2" but `system_config.view`, `system_config.admin`, `system_config.edit`, `notifications.view`, `notifications.edit` were already present in `PERMISSION_CATALOGUE` from defensive earlier seeding. We added zero new codes; we tightened role grants instead. Total stays at 87.
- **Director loses `system_config.{admin,edit}`** — required to make `system_config.admin` super_admin-only as spec'd. Director permission count drops 84 → 82.
- **`audit_retention_sweep` does not accept a `years` argument** — current `purge_old_audit_rows` enforces a fixed 7-year floor at the module level; we log the requested `audit.retention_years` for visibility and respect the hard floor regardless.

### Deliberately simplified
- Single `BackgroundScheduler` per job module rather than a single shared scheduler — keeps each job's lifecycle independent and matches the existing pattern set by `insurance_alerts.py` / `planning_expiry.py`. Polish Pass: consolidate.
- `ConfigPage` read-only state renders the value inside a disabled `<button>` (with `data-readonly` + `data-config-value` attributes) rather than `<input disabled>`. Functional and testable; not yet form-element-pure.
- Notifications `body` is plain markdown-ish text passed straight to `<div>`. No Markdown renderer pulled in. Polish Pass.
- Frontend bell polls every 30s; no WebSocket push.
- Notification grouping is read-time only on `/unread`. Full inbox is ungrouped.

### Residuals / surfaced during build
- Existing pytest fixture `login_with_auto_enroll` caches the TOTP secret in-process. Browser-driven super_admin testing (e.g. `/config` write path) cannot ride that cache. Validated via 23 pytest tests instead. Future: add a non-MFA super_admin fixture user, or expose a CI flag to skip MFA enforcement on `test-admin@example.test`.
- Pre-existing ruff lint warning `email.py:91 F841 Local variable 'key' is assigned to but never used` predates 1.7 and was not touched.
- `app/scheduler.py::planning_expiry_sweep` and `_emit_alert` keep their existing log lines alongside the new notification dispatches (belt-and-braces during cutover).

### Polish Pass items added to log
1. Persistent APScheduler jobstore (SQLAlchemy or Redis) so multi-worker production doesn't double-fire.
2. Notification body sensitive-field scrubbing — currently bodies may embed resource references (project codes, dates).
3. Tighten `cost_codes` permission catalogue (carry-over from spec).
4. Per-key `minimum_role_to_edit` enforcement at the router layer (column kept; v1 enforces super_admin only).
5. Notification dispatch queue + worker for high-volume scenarios.
6. Render read-only ConfigPage values as `<input disabled>` for tooling parity.
7. Migrate older `/api/*` routes to `/api/v1/*` on a per-prompt basis.
8. Email template library (`ConsoleEmailProvider` plain-text only in v1).
9. Per-tenant / per-entity config overrides; config change approval workflow.
10. Real-time WebSocket push for notifications (replace 30s polling for high-priority).
11. Phone verification + Twilio for SMS dispatch.
