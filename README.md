## Environment Variables

### Required

- `DATABASE_URL` — Postgres connection string
- `JWT_SECRET` — signing secret for JWT access tokens (generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`)
- `MFA_ENCRYPTION_KEY` — Fernet key for encrypting MFA secrets and backup codes at rest. Backend refuses to start without it. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and store in `.env` before first boot. **Losing this key renders all stored MFA secrets permanently un-decryptable** — users will need to re-enrol MFA from scratch.
- `APP_ENV` — one of `test`, `development`, `production`. Controls cookie `Secure` flag and gates the rate-limit bypass flag.
- `CORS_ORIGINS` — comma-separated list of allowed origins (e.g. `https://app.syhomes.co.uk,https://preview.emergentagent.com`). Wildcards (`*`) are rejected at startup because `allow_credentials=True` is set.

### Optional

- `SENDGRID_API_KEY`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`, `EMAIL_REPLY_TO` — required before switching from `ConsoleEmailProvider` to SendGrid for transactional email (invitations, password resets, alerts). SendGrid branch is drafted in `app/services/email.py` but commented out; uncomment when credentials are configured.
- `MAXMIND_LICENSE_KEY` — required for automated GeoLite2 database updates via `scripts/download_geolite2.py` (weekly cron recommended). Without the `.mmdb` file, `location_country`/`location_city` stay NULL on login-history rows.
- `SYHOMES_RATE_LIMIT_DISABLED=1` — bypasses rate limiting. **Only honoured when `APP_ENV=test` is also set.** In any other environment, the flag is logged as an ERROR at startup and rate limiting remains active.

### Security notes

- Access tokens (JWT, 15-min TTL) and refresh tokens (opaque, 30d default / 90d with "Remember me") are delivered as HttpOnly cookies only — never in JSON response bodies.
- Refresh tokens rotate on every use; single-hop replay triggers revocation of all the user's sessions.
- For production cross-site POSTs, a CSRF token pattern would need to be added. Not required in current single-origin deployment (SameSite=Lax on cookies is sufficient).

### Deployment checklist

- [ ] `APP_ENV=production` set (flips cookie `Secure=True`)
- [ ] `CORS_ORIGINS` set to explicit origin list (no `*`)
- [ ] `MFA_ENCRYPTION_KEY` backed up securely (password manager + offline)
- [ ] `JWT_SECRET` backed up securely
- [ ] `DATABASE_URL` points to persistent Postgres (not ephemeral preview)
- [ ] SPF, DKIM, DMARC records configured on the sending subdomain before enabling SendGrid
- [ ] `SYHOMES_RATE_LIMIT_DISABLED` unset
