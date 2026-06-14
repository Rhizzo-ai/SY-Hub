# Test Credentials — SY-Hub (pod-local)

These accounts are seeded by `scripts/seed_test_users.py` (idempotent). Reset MFA before headless flows via:

```sql
UPDATE users SET mfa_enabled=false, mfa_method=NULL,
  mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
  mfa_enrolled_at=NULL, failed_login_attempts=0,
  locked_until=NULL, lockout_level=0
WHERE email LIKE 'test-%@example.test';
```

Password (all accounts): from `backend/.env::TEST_USER_PASSWORD` — currently `TestUser-Dev-2026!`.

| Email                          | Role             | Notes                                  |
|--------------------------------|------------------|----------------------------------------|
| `test-admin@example.test`      | `super_admin`    | MFA enforced (re-enrols on first login)|
| `test-director@example.test`   | `director`       | MFA enforced                           |
| `test-finance@example.test`    | `finance`        | MFA enforced                           |
| `test-pm@example.test`         | `project_manager`| No MFA — preferred for headless screenshot flows. Has `packages.*`, `pos.*`, and `pos.view_sensitive`. |
| `test-site@example.test`       | `site_manager`   | No MFA. Has `pos.view` but NOT `pos.view_sensitive` (pricing-redaction test target). |
| `test-readonly@example.test`   | `read_only`      | No MFA. Read-only.                     |
| `test-archived@example.test`   | `read_only`      | Archived. Login should fail.           |

For Pack 3.5 screenshot proofs (Gates 5/6/7), use `test-pm@example.test`. For LIVE-API award proofs (Gates 3/4), `test-admin@example.test` works after MFA reset.
