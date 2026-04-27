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


## Background jobs / scheduling (1.4, 1.5, 1.7)

The platform uses **APScheduler** (`apscheduler` Python package, listed in
`pyproject.toml`) with `BackgroundScheduler` and the **default in-memory
jobstore**. Jobs are registered at app startup via the `lifespan(...)`
handler in `server.py` and torn down cleanly on shutdown.

Currently scheduled (all timezone UTC):

| Job id | Trigger | Module | Purpose |
| --- | --- | --- | --- |
| `insurance_expiry_alerts` | daily 06:00 | `app/jobs/insurance_alerts.py` | Per-policy expiry alerts (1.1) — retro-wired in 1.7 to dispatch notifications. |
| `role_expiry_sweep` | hourly | `app/jobs/role_expiry.py` | Marks expired `user_roles` (1.2). |
| `planning_expiry_sweep` | daily 07:00 | `app/scheduler.py` | Project planning permission alerts (1.5) — retro-wired in 1.7. |
| `notification_expiry_sweep` | daily 03:00 | `app/jobs/notification_expiry.py` | Bulk-dismiss expired notifications (1.7). |
| `audit_retention_sweep` | daily 03:00 | `app/jobs/audit_retention.py` | Calls `purge_old_audit_rows` if `audit.retention_purge_enabled`=true. Gated OFF by default. 7-year hard floor enforced in `app/services/audit_retention.py`. |

### Production caveat — multi-process scheduler

The in-memory jobstore is **per-process**. Running the API under multiple
worker processes (`uvicorn --workers N`, gunicorn workers, etc.) will
fire each scheduled job N times per tick. This is correct for the
Emergent hosted single-worker dev environment but **not safe for
multi-worker production**.

When we move to multi-worker production, switch to a persistent jobstore
(SQLAlchemy on the existing Postgres or Redis) and gate startup so only
one worker initialises the scheduler. Tracked in the Polish Pass log
(`/app/memory/PRD.md` § Prompt 1.7 Polish Pass items #1).

## System configuration (1.7)

Runtime-tunable settings live in the `system_config` table — typed
key/value pairs seeded with 38 keys across 9 populated categories
(see `app/seed_system_config.SEEDS`). The service layer, not direct DB
access, is the supported read path.

```python
from app.services import system_config

# Typed read — raises KeyError if the key isn't seeded.
min_pwd_len = system_config.get("security.password_min_length")  # int 12

# Tolerant read — returns the default when the key is missing.
hurdle_pct = system_config.get_or_default(
    "finance.default_hurdle_on_cost_pct", 20,
)

# Write (super_admin only at the router layer; bypass that gate at your peril).
from app.db import SessionLocal
db = SessionLocal()
try:
    system_config.set_value(
        db, "security.password_min_length", 14, user_id=current_user.id,
    )
    db.commit()
finally:
    db.close()

# Restore to the seed default.
system_config.restore(db, "security.password_min_length", user_id=current_user.id)
```

Reads are cached in-process. Writes through `set_value`/`restore` invalidate
the cache automatically. If you need to bust the cache from outside the
service (e.g. test setup), call `system_config.invalidate(key=None)`.

### Adding a new key

1. Append a tuple to `SEEDS` in `app/seed_system_config.py`.
2. Restart the backend — the lifespan-time `seed_system_config()` is
   idempotent and will insert the new row only.
3. Add a row to the matching category section of the `/config` UI test
   fixture if you want explicit `data-testid` coverage.

### Rate limiting and the bell endpoint

The frontend bell polls `GET /api/v1/notifications/unread-count` every
30 seconds per authenticated user. This endpoint is **deliberately not
rate-limited**. The rate limiter (`app/services/rate_limit.py`) is an
opt-in per-endpoint helper called explicitly by the few routes that
need it (login, password reset). It is *not* installed as a global
middleware. The five entries in `LIMITS` (lines 75–81 of that module)
are the entire scope of rate-limited routes.

If you ever introduce a global rate-limit middleware, add an explicit
exemption for `/api/v1/notifications/unread-count` and re-run the
bell-polling integration test in `tests/test_notifications.py
::TestPolling::test_polling_does_not_trip_rate_limiter`.
