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

## 1. Fresh-DB bootstrap ordering — **P0 → RESOLVED (bootstrap-fix-p0, 2026-05-04)**

Resolved by introducing `app/bootstrap.py` as the canonical pod-restart
entrypoint, invoked by `/root/.emergent/on-restart.sh` on every container
boot. The orchestrator embeds the staged migration + seed dance (alembic
to 0017 → tenant seed → filtered RBAC seed → alembic to head → full RBAC
top-up → system_config seeds → test users → verify) as the single,
idempotent code path. A Postgres advisory lock prevents concurrent
runs; verify_invariants asserts the post-seed shape (alembic at head,
permission count, role count, super_admin user, every ROLE_PERMISSIONS
code resolves). 15 new tests under `tests/test_bootstrap.py` exercise
every failure mode plus a true cold-start (drop+create DB, run script,
assert green) and a snapshot-restore simulation (build to 0019, verify
enum lacks the 0020 values, run bootstrap, assert self-heal). The
runbook lives in the module docstring of `app.bootstrap`.

Production failure modes covered:
- BOOTSTRAP_ADMIN_* missing       → exit 1 with cause=env_missing
- Postgres unreachable in N s     → exit 2 with cause=pg_unreachable
- Concurrent bootstrap            → exit 3 with cause=lock_unavailable
- Migration error                 → exit 4 with alembic stderr captured
- Any seed failure                → exit 5 with cause=seed_failed
- Invariant drift (any of 6)      → exit 6 with cause=&lt;specific&gt;

Sandbox provisioning steps for future fresh forks (Postgres install,
syhomes role/db creation, supervisor wiring) are documented in
`app.bootstrap`'s "Sandbox provisioning notes" section.

(Original P0 / P1 history retained below for context.)

## 1a. Fresh-DB bootstrap ordering — **P0 (RECURRING) [historical]**

Surfaced at 0017, recurred at 0018/0019 (2.2), and recurred TWICE during Prompt 2.3 Step 0 (May 2026). Three confirmed pod-restart triggers in two months. Documented runbook works (manual sequence: seed → seed_rbac partial → seed_test_users → alembic upgrade → seed_rbac full) but it's a manual hot-fix every time.

**Mandatory fix before next Track 2 prompt**: split inline INSERT seeds out of migrations 0018, 0019, 0020 into a dedicated post-migration data-seed module that runs at the lifespan phase AFTER `alembic upgrade head` AND `seed()` + `seed_rbac()`. Add a CI smoke test that drops the DB, runs cold-start, and asserts pytest passes.

(Original P1 entry retained below for context.)

## 1b. Fresh-DB bootstrap ordering (original P1 entry, historical)

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

## 2. `appraisal_scenarios` FK ON DELETE RESTRICT blocks test cascade — **P1**

- **Surfaced in**: bootstrap-fix-p0 verification run (2026-05-04). The
  pytest suite passes only when invoked with
  `--ignore=tests/test_c3_governance_smoke.py`; including the smoke test
  pollutes downstream fixtures because its teardown cannot delete the
  parent `projects` / `appraisals` rows.
- **Severity**: P1 — blocks clean test cascades and will block Prompt
  2.4 (Budgets) cascade work that needs to delete projects in fixture
  teardown.
- **Description**: Migration 0022 (`appraisal_governance`) created
  `appraisal_scenarios.scenario_appraisal_id_fkey` with `ON DELETE
  RESTRICT`. This blocks the natural project → appraisal → scenario
  delete cascade used by test fixture teardowns. Two sub-issues:
  - **(a)** `tests/test_c3_governance_smoke.py` has no teardown at all,
    so even with a permissive FK the rows would leak between tests;
  - **(b)** the FK should be `ON DELETE CASCADE` so the parent project
    delete propagates to scenarios without bespoke teardown logic per
    test.
- **Proposed resolution**:
  1. Refactor `tests/test_c3_governance_smoke.py` to use the standard
     project/appraisal fixtures and explicit teardown (or autouse
     transactional rollback fixture) — sub-issue (a).
  2. New alembic migration `0023_appraisal_scenarios_fk_cascade` to
     `ALTER TABLE appraisal_scenarios DROP CONSTRAINT
     scenario_appraisal_id_fkey` and re-add it with `ON DELETE
     CASCADE` — sub-issue (b).
  3. Remove the `--ignore=tests/test_c3_governance_smoke.py` workaround
     from CI / docs once both sub-issues are green.
- **Owner / Target prompt**: must be resolved before Prompt 2.4
  (Budgets) cascade work begins.

---

## 3. CI pipeline + bootstrap anchor smoke test — **P1**

- **Surfaced in**: bootstrap-fix-p0 PR review (2026-05-05). Cold-start
  bootstrap failures hit 5/5 times during 2.3 work; every catch was a
  human noticing a broken pod. There is currently no CI to catch this
  class of regression before it lands.
- **Severity**: P1 — operational risk grows with every new migration
  and seed step. Without CI gating, the bootstrap-fix-p0 contract
  decays over time.
- **Description**: Establish a CI pipeline for the SY Hub repo. The
  anchor test is a single proof-of-life check:
  `python -m app.bootstrap` against an ephemeral Postgres 16, asserting
  `rc=0` and the 6 verify invariants on a freshly created DB. This
  exact run would have caught all 5 cold-start failures during 2.3.
- **Scope-as-a-fix (not a one-line addition)** — discrete decisions
  required:
  1. **Runner choice** — GitHub Actions (default, free for the org's
     plan) vs. self-hosted on the Emergent sandbox vs. CircleCI/other.
     Cost, secrets exposure, and concurrency limits all differ.
  2. **Test-DB strategy** — service container (`services: postgres:`
     in GHA), Docker Compose, or `pg_tmp`/`testing.postgresql`. Must
     match prod Postgres 16 (PGDG, not Debian default 15) and ship
     `pgcrypto` for `gen_random_uuid()` server-defaults.
  3. **Secrets handling for `BOOTSTRAP_ADMIN_*`** — needs CI-only
     dummy values committed to a CI env file or repo-secret-injected
     at job start. Production `BOOTSTRAP_ADMIN_PASSWORD_HASH` must
     never be readable in CI logs.
  4. **Merge-gating policy** — required check on `main`? Required for
     PR merge? Allowed-to-fail on draft PRs? Define before turning it
     on so contributors aren't surprised by a red required check.
  5. **Scope creep guard** — first iteration runs *only* the
     bootstrap anchor + `pytest --ignore=tests/test_c3_governance_smoke.py`.
     Expanding to lint / type-check / coverage is a separate ticket.
- **Proposed resolution**: spike the four decisions above, land a
  minimal `.github/workflows/ci.yml` (or equivalent) that brings up
  Postgres 16, runs `python -m app.bootstrap` (assert rc=0), then runs
  the pytest suite with the documented ignore. Iterate from there.
- **Owner / Target prompt**: before or alongside Prompt 2.4 (Budgets).
  Explicitly out of scope for the bootstrap-fix-p0 PR — keep that PR
  product-surface-clean.

---

## 4. (placeholder — future entries appended here)
