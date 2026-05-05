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

## 1. Fresh-DB bootstrap ordering — **RESOLVED (Chat 14, 5 May 2026)**

**Status: RESOLVED.** Bootstrap orchestrator landed on `main` during Chat 14 (work tracked under logical label `bootstrap-fix-p0`; landed via Emergent auto-commits, not a PR — see chat-14-closing §11). The §R0 manual recovery dance documented in C1/C2/C3 handoffs is now obsolete. Fresh-DB and snapshot-restore boots succeed unattended.

**What landed:**
- `/app/backend/app/bootstrap.py` — single entry-point at `python -m app.bootstrap`. Nine-step flow: env-var precheck → wait_for_postgres → acquire pg advisory lock → detect_db_state → alembic upgrade head → seed → seed_rbac → seed_test_users (if present) → verify_invariants → release lock + summary. Concurrency-safe via Postgres advisory lock. Per-step k=v timing logs. Verify-invariants asserts alembic at head, perm count matches `len(PERMISSION_CATALOGUE)`, role count matches `len(ROLE_CATALOGUE)`, super_admin exists + is role-assigned, every code in `ROLE_PERMISSIONS` resolves to a real permission row.
- `/app/backend/tests/test_bootstrap.py` — 15 tests covering env precheck, Postgres timeout, detect_state branches, verify_invariants happy + 5 failure modes, concurrent-lock test, end-to-end integration. Test count moved 581 → 596.
- `/app/scripts/supervisord_backend.conf.template` — checked-in template for `[program:backend]` block (`autostart=false`, `autorestart=false`). Source of truth for the supervisor gating contract.
- `/app/scripts/on-restart.sh` — idempotently applies the supervisor template at the top of every hook fire (self-healing on container rebuild), then runs `python -m app.bootstrap`, then `sudo supervisorctl start backend` only on `rc=0`. Mirrored to live `/root/.emergent/on-restart.sh`.
- `/app/scripts/README.md` — fresh-fork install instructions; "Supervisor backend gating" section.
- `/app/docs/SY_Hub_Bootstrap_Fix_P0_Build_Pack.md` — Build Pack v2 verbatim (378 lines), committed alongside the code.

**Verification:** Cold-start (drop DB → bootstrap → 596 tests pass) ✅. Idempotence (3× consecutive runs, diff = elapsed only) ✅. Concurrency (one rc=0, one rc=3 cause=lock_unavailable) ✅. Snapshot-restore simulation (DB at 0019, missing enum values, bootstrap → orchestrator advances to head, both enum values present) ✅. Supervisor gating (failure path: postgres stopped → bootstrap rc=2 → backend STOPPED, hook exit=2; happy path: bootstrap rc=0 → backend RUNNING, /api/health 200) ✅.

**Reference docs:** `chat-14-closing.md` (full session record); `SY_Hub_Bootstrap_Fix_P0_Build_Pack.md` (the spec the fix was built against).

(Original entries retained below for historical context.)

## 1a. Fresh-DB bootstrap ordering — **historical (P0 RECURRING wording, pre-fix)**

Surfaced at 0017, recurred at 0018/0019 (2.2), and recurred TWICE during Prompt 2.3 Step 0 (May 2026). Three confirmed pod-restart triggers in two months. Five total recurrences by the time the fix landed. Documented runbook worked (manual sequence: seed → seed_rbac partial → seed_test_users → alembic upgrade → seed_rbac full) but it was a manual hot-fix every time.

**Mandatory fix before next Track 2 prompt**: split inline INSERT seeds out of migrations 0018, 0019, 0020 into a dedicated post-migration data-seed module that runs at the lifespan phase AFTER `alembic upgrade head` AND `seed()` + `seed_rbac()`. Add a CI smoke test that drops the DB, runs cold-start, and asserts pytest passes.

## 1b. Fresh-DB bootstrap ordering — **original P1 entry**

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

## 2. `appraisal_scenarios` FK ON DELETE RESTRICT — **P1 (gates Prompt 2.4)**

- **Surfaced in**: Chat 14 baseline check (5 May 2026) — surfaced as a side-effect of the bootstrap fix's full-suite run; the smoke test pollution issue had been masked by the `--ignore=tests/test_c3_governance_smoke.py` workaround.
- **Severity**: P1 — blocks Prompt 2.4 (Budgets). Budgets work will introduce more cascade scenarios (project deletion → budgets → budget_changes → actuals); a known broken cascade pattern in the codebase will compound risk.
- **Description**: `appraisal_scenarios.scenario_appraisal_id_fkey` is `ON DELETE RESTRICT` (introduced in migration 0022 as part of the C2 backend work). This blocks the cascade from `DELETE FROM projects → appraisals → scenarios` in test teardown. The current pytest invocation works around this with `--ignore=tests/test_c3_governance_smoke.py`, which keeps the suite green at 596 but masks the underlying issue.

  Two sub-issues:

  **2a (test infrastructure):** `tests/test_c3_governance_smoke.py` has no teardown. It's a smoke-probe test that should run post-deploy, not as part of the unit regression suite. Even if the FK were `CASCADE`, this test would still pollute the DB state for subsequent tests because it doesn't clean up after itself.

  **2b (data model):** The FK should be `ON DELETE CASCADE`, not `RESTRICT`. The product-level intent is "deleting a project removes all of its appraisals and their scenarios" — `RESTRICT` violates that.

- **Proposed resolution**:
  1. Migration `0023_appraisal_scenarios_fk_cascade`: drop the FK, recreate with `ON DELETE CASCADE`. Proper `downgrade()` that recreates the original `RESTRICT` behaviour. Verify both directions with explicit tests.
  2. Refactor `tests/test_c3_governance_smoke.py` with proper teardown — pytest fixture, same conftest patterns the rest of the suite uses; do not invent new infrastructure.
  3. Drop the `--ignore=tests/test_c3_governance_smoke.py` flag from pytest invocation. Full suite must be green at the new count (596 + however many smoke tests are in that file).
  4. Verify the cascade actually works end-to-end: create project → appraisal → scenario → DELETE project → confirm scenario row is gone. Not just "the FK has CASCADE in `pg_constraint`."
- **Owner / Target prompt**: Chat 15 (Pre-2.4 Cleanup). Both sub-issues land in one PR-equivalent unit of work (logical branch label `pre-2.4-cleanup`). Hard gate: must be resolved before Prompt 2.4 (Budgets).

---

## 3. CI pipeline (anchor: bootstrap smoke test) — **P1**

- **Surfaced in**: Chat 14 (5 May 2026) — proposed by the bootstrap-fix-p0 agent at session close; deferred from that PR to keep scope clean.
- **Severity**: P1 — not currently gating any specific prompt, but Budgets (Prompt 2.4) will be the highest-stakes financial code in the platform to date. CI catches regressions before they reach Rhys; without it, the only quality gate is agent self-report (which has been shown to drift — see Chat 14's Future_Tasks sync gap).
- **Description**: Currently SY-Hub has no continuous integration pipeline. Five recurrences of the bootstrap chicken-and-egg during 2.3 work proved the cost of not having one — every recurrence was a manual hot-fix that took 15-30 minutes. A simple smoke test (`python -m app.bootstrap` against an ephemeral Postgres, assert `rc=0`) would have caught all five before they hit a human.

  The proposed CI scope is broader than just the smoke test:
  - **Anchor:** bootstrap smoke against ephemeral Postgres
  - **Likely:** full pytest suite (once the §2 `--ignore` flag is dropped)
  - **Maybe:** lint / type-check passes
  - **Maybe:** frontend build verification

- **Decisions to make** (none locked yet):
  - Runner choice: GitHub Actions (free for public repos / cheap for private; native to where the code lives) vs. self-hosted (cost vs. control).
  - Test-DB strategy in CI: ephemeral Postgres container per run? testcontainers-python? service container?
  - Secrets handling for `BOOTSTRAP_ADMIN_*`: GitHub Actions secrets if going that route.
  - Whether CI gates merges to main: recommended yes, but Emergent's "Save to GitHub" pushes directly to main as auto-commits — which means the gate would have to run *post-push* (revert on red) rather than *pre-merge*. Worth thinking through.
  - What other tests run alongside bootstrap smoke.
- **Sizing**: Discrete fix, not a one-line addition. Likely a half-session unit of work in its own right. The agent at end of Chat 14 suggested this as a single CI step; on review, that under-scopes the actual work involved.
- **Recommended sequencing**: After §2 lands (Chat 15), before or alongside Prompt 2.4 (Chat 16+). Most likely candidate for Chat 17 if Chat 15 and 16 stay in scope.
- **Owner / Target prompt**: Standalone Chat (likely Chat 17), or bundled into the start of Prompt 2.4 if the FK cleanup goes faster than expected.

---

## 4. (placeholder — future entries appended here)
