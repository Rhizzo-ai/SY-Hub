# Test credentials — SY-Hub spot-check sandbox

All test users share one password sourced from `backend/.env`:

```
TEST_USER_PASSWORD=TestUser-Dev-2026!
```

MFA is disabled on all `test-*@example.test` accounts by the seed
scripts (`seed_r7_spotcheck.sh` + `seed_r7_batch1_pos.py`). If a user
shows `mfa_required: true` again after a re-seed:

```
psql ... -c "UPDATE users SET mfa_enabled=false, mfa_method=NULL,
  mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
  mfa_enrolled_at=NULL, failed_login_attempts=0,
  locked_until=NULL, lockout_level=0
  WHERE email LIKE 'test-%@example.test'"
```

## Spot-check users

| Email                              | Role               | Notes                              |
|-----------------------------------|--------------------|------------------------------------|
| `test-admin@example.test`         | Super Administrator | Primary operator login              |
| `test-director@example.test`      | Director           | Approver role                      |
| `test-pm@example.test`            | Project Manager    | Creator of seed POs #1/#2/#4       |
| `test-finance@example.test`       | Finance            |                                    |
| `test-site@example.test`          | Site Manager       |                                    |
| `test-readonly@example.test`      | Read Only          | Visibility test (entity_scope=All) |

## Spot-check project (R7 Batch 1)

```
Project ID: b2a265ef-dc30-4779-96f6-e139d1881e07
Project URL: {REACT_APP_BACKEND_URL}/projects/b2a265ef-dc30-4779-96f6-e139d1881e07
```

Five POs seeded across the lifecycle — see `/app/scripts/seed_r7_batch1_pos.py`
output for direct per-PO URLs and the state matrix (draft / pending_approval
×2 / approved ×2 with two self-approval-rule targets).

## Bootstrap admin

`rhys@syhomes.co.uk` exists in seeded DBs with MFA enabled. Not used for
test flows — operator-only.

## BCR (Prompt 2.6-FE) — preferred test user

Use **`test-pm@example.test`** for BCR end-to-end flows. The PM role
has ALL 6 `budget_changes.*` permissions (view / create / edit /
submit / approve / apply) AND does NOT trigger MFA enrollment
(super_admin / director / finance roles DO enforce MFA — they sit on
`mfa_pending` after login until enrolled, so /auth/me returns
permissions=[]).

Seeded budget for BCR tests (created by `seed_r7_spotcheck.sh`):
- Project ID: `b2a265ef-dc30-4779-96f6-e139d1881e07`
- Budget ID:  `5a329b39-2a22-492e-a929-908a99096e8f` (Active)
- Budget URL: `{REACT_APP_BACKEND_URL}/projects/b2a265ef-dc30-4779-96f6-e139d1881e07/budgets/5a329b39-2a22-492e-a929-908a99096e8f?tab=changes`
- 10 budget lines across ACQ-/EXT-/FIN- prefix categories.

For the LD2 self-approval test, raise a BCR > £10k as `test-pm`, then
log in as a SECOND user (the only currently MFA-clean second user is
the seeded super-admin or — once MFA-enrolled — director/finance).
For day-one smoke, the single-user happy path is via `test-pm`.
