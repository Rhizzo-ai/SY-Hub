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
