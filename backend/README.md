# SY Homes Operations Platform — Backend

FastAPI + PostgreSQL + Alembic. See `/app/memory/PRD.md` for feature scope and
`/app/memory/test_credentials.md` for test accounts.

## Environment setup

Copy `.env` keys from the checked-in template or ask another engineer. Key
variables:

| Var | Required? | Notes |
| --- | --- | --- |
| `DATABASE_URL` | yes | Postgres DSN |
| `MONGO_URL` / `DB_NAME` | legacy | protected placeholders; do not remove |
| `JWT_SECRET` | yes | HS256 signing key for access tokens |
| `MFA_ENCRYPTION_KEY` | auto | Fernet key, generated on first boot |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` / `_FIRST_NAME` / `_LAST_NAME` | yes | seed super_admin |
| `SYHOMES_RATE_LIMIT_DISABLED` | dev only | bypasses per-IP/email limits during pytest |

## Running

```bash
cd /app/backend
alembic upgrade head                   # always
python scripts/seed_test_users.py      # idempotent; creates ~8 test accounts
pytest                                 # configured by pyproject.toml
```

## Running tests

```bash
cd /app/backend
pytest
```

The repo-root `pyproject.toml` configures `pythonpath = ["."]` and
`testpaths = ["tests"]`, so a bare `pytest` invocation discovers the suite
and resolves `from tests.conftest import …` cleanly. `python -m pytest`
also works and is preferred in CI.

## Third-party integrations (Prompt 1.3 stage 1b)

### Email — `ConsoleEmailProvider` default

By default, all outbound email writes to stdout + `email_send_log` with
`status='dev_console'`. This keeps local dev loop-free and lets you verify
the template rendering without a provider account.

**Production flip to SendGrid:**

1. Add to `backend/.env`:
   ```
   SENDGRID_API_KEY=SG.xxxxxxxx
   EMAIL_FROM_ADDRESS=noreply@syhomes.co.uk
   EMAIL_FROM_NAME="SY Homes Operations"
   EMAIL_REPLY_TO=support@syhomes.co.uk
   ```
2. `pip install sendgrid && pip freeze > requirements.txt`
3. Uncomment the `SendGridEmailProvider` class and branch in
   `app/services/email.py` (4 contiguous blocks marked `SendGrid provider`).
4. `sudo supervisorctl restart backend`.

**DNS for deliverability (do this BEFORE flipping):** configure SPF, DKIM,
and DMARC records on the sending domain. SendGrid's dashboard generates the
exact CNAME values you need. Without these, messages will land in spam.

### Geolocation — MaxMind GeoLite2 (self-hosted)

Ships without the mmdb file. Every `geolocate(ip)` call gracefully returns
`None`/`country=NULL` until the file is present.

**To enable:**

1. Create a free MaxMind account: https://www.maxmind.com/en/geolite2/signup
2. Generate a license key in your portal.
3. Add to `backend/.env`:
   ```
   MAXMIND_LICENSE_KEY=your_key_here
   ```
4. `python scripts/download_geolite2.py` — drops the ~60 MB mmdb into
   `backend/data/geolite2/`. Next request auto-picks it up.
5. Schedule `scripts/download_geolite2.py` as a weekly cron — MaxMind's
   EULA requires keeping the file current.

## Auth architecture notes (1.3 stage 1b)

- **Access tokens**: HS256 JWT, 15-minute TTL, carry a `sid` claim binding
  them to a `user_sessions` row. Old tokens without `sid` (issued pre-1.3)
  are rejected — restart clears the cache.
- **Refresh tokens**: opaque 32-byte random, SHA-256 hashed in
  `user_sessions.refresh_token_hash`. 30-day TTL default, 90 with
  Remember me. Rotated on every `/auth/refresh`; previous hash kept in
  `previous_refresh_token_hash` for replay detection.
- **Replay detection**: presenting a previously-rotated refresh token
  revokes *all* sessions for the user and stamps a
  `Suspicious_Activity_Detected` login-history event. Attacker forced out;
  legitimate user re-auths with password.
- **Idle timeout**: 60 min without activity. Server checks
  `last_active_at` on every authenticated request (throttled to one write
  per 60 s); client warns at 55 min, force-logs-out at 60.
- **Login history**: `user_login_history` is append-only — a DB trigger
  raises on UPDATE/DELETE. Retention is 2+ years (no cleanup job yet).

## Deferred to next stage (Prompt 1.3 stage 2)

- Invitation email delivery (system exists in 1.2, email send is the gap).
- SSO (Google / Microsoft / Apple) via `external_identity_providers`.
- API keys for Service_Accounts via `api_keys`.
- Suspicious-activity alerts (new-country, impossible-travel, replay-mail).
- `/invitations`, `/api-keys`, `/profile/security/sso` UIs.
- Rate-limits on SSO callbacks.
