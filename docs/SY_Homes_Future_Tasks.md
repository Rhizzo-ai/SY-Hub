# SY Homes — Future Tasks & Deferred Work

A running log of formally-captured backlog items that span multiple prompts
or live outside any one build-prompt's scope. Items here have been
surfaced more than once or have meaningful operational risk if left
unaddressed.

Format per entry:
- **Title**
- **Surfaced in**: which prompt(s) / patch(es) the issue first appeared
- **Severity**: P0 (block release) / P1 (ship-blocker for next major) / P2 (polish)
- **Description**
- **Proposed resolution**
- **Owner / Target prompt**

---

## 1. Fresh-DB bootstrap ordering

- **Surfaced in**: Prompt 2.1 (migration 0017 — first time); Prompt 2.2
  (migrations 0018 + 0019 — recurrence)
- **Severity**: P1 (ops / CI / disaster-recovery risk; does not affect
  existing running installs)
- **Description**: Migrations 0017, 0018, and 0019 add enum values or seed
  rows that downstream seed steps (`app/seed.py`, `app/seed_rbac.py`,
  `app/seed_system_config.py`) then consume. The `server.py` lifespan
  currently runs `alembic upgrade head` **before** `seed()`, which works
  on an existing database (tenants + super_admin already present) but
  fails hard on a pristine / freshly-dropped database because 0018 and
  0019 inline-seed data that requires those rows to exist. The failure
  mode is a clean `RuntimeError: seed cannot run — no tenants present.`
  but the app then can't start, and recovery requires manually running
  `python -c "from app.seed import seed; seed()"` followed by
  `alembic upgrade head` out-of-band. This pattern has now surfaced
  twice. Left unfixed, the first prod restore-from-backup or CI
  cold-start will trip on it.
- **Proposed resolution**:
  1. Document the exact pristine-DB bootstrap sequence in a
     `backend/docs/DB_BOOTSTRAP.md` runbook (`pg_drop` → initial alembic
     upgrade to the last pre-seed-requiring revision → `seed()` +
     `seed_rbac()` → alembic upgrade head → `scripts/seed_test_users.py`).
  2. Add a CI smoke test that executes the above from zero on every PR:
     create a throwaway Postgres DB, run the full sequence, then run
     `pytest`. Catches any future migration that re-introduces the
     pattern.
  3. Longer-term fix: split the inline seed inserts out of the
     migrations and into a dedicated post-migration seed module that
     runs at the correct phase of the lifespan, so migrations never
     have a runtime data dependency. 0018's dependency on `tenants` +
     `users` is the canonical example to refactor first.
- **Owner / Target prompt**: ops/infra polish pass between Prompt 2.x
  and Track 3 kickoff. Not a Prompt-2.3 gate.

---

## 2. (placeholder — future entries appended here)
