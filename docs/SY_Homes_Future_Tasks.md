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

## 2. `appraisal_scenarios` FK ON DELETE RESTRICT — **PARTIALLY RESOLVED (Chat 15, 7 May 2026)**

**Status: PARTIALLY RESOLVED.** Chat 15 landed the narrow FK fix (§2b) on `main` (work tracked under logical label `pre-2.4-cleanup`; landed via Emergent auto-commits, see chat-14-closing §11 for the convention). Migration `0023_appraisal_scenarios_cascade` flipped `appraisal_scenarios_scenario_appraisal_id_fkey` from `ON DELETE RESTRICT` to `CASCADE`; new regression test `tests/test_appraisal_scenarios_cascade.py` proves the cascade actually fires through a real ORM session. Test count moved 596 → 597.

The **gate for Prompt 2.4 (Budgets) is now cleared.** Pre-paste audit during Chat 15 reclassified §2a from "ship-blocker bug" to an architectural classification question that does not share infrastructure with Budgets work — see new entry §4 below for the full reclassification prose. The remaining four RESTRICT FKs in 0022 are deferred to §5 below (no current use case, debt-with-no-pressure).

**What did NOT land in Chat 15 (split out for clarity):**
- Smoke test (`tests/test_c3_governance_smoke.py`) classification or rebuild — see §4.
- The other four `ON DELETE RESTRICT` FKs in 0022 (`parent_scenario_appraisal_id`, both `appraisal_revisions` FKs, `appraisal_decision_log.appraisal_id`) — see §5.
- The `--ignore=tests/test_c3_governance_smoke.py` flag in the pytest invocation — stays in place; removal is part of §4 work, not §2b.

**Reference docs:** `chat-15-closing.md` (when written); `SY_Hub_Pre_2_4_Cleanup_Build_Pack.md` (the spec the fix was built against).

(Original entry retained below for historical context.)

## 2 (historical — pre-Chat 15). `appraisal_scenarios` FK ON DELETE RESTRICT — P1 (gates Prompt 2.4)

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

## 3. CI pipeline (anchor: bootstrap smoke test) — **RESOLVED (Chat 21, 2026-05-18)**

**Resolution:** Shipped `.github/workflows/ci.yml` per Chat 21 Build Pack v-final.
Two-job pipeline (backend + frontend) on every push to main. Backend job
anchors on `python -m app.bootstrap` (Future_Tasks §3 anchor item).
Frontend job enforces I11 bundle hard cap. See CHANGELOG Chat 21 entry
and `docs/chat-summaries/chat-21-closing.md`.

**Decisions locked at Chat 21 open** (operator answers, plain-English version of Q1–Q6):

1. Runner: GitHub Actions (hosted).
2. Gate model: post-push alert + status badge; operator decides revert.
   Pre-merge gating not available without changing Emergent's auto-commit
   workflow; that's a separate process change.
3. Scope v1: bootstrap smoke + backend pytest + frontend build + bundle
   gate + Jest. Playwright + lint deferred.
4. Postgres: service container (postgres:16), not testcontainers-python.
5. Secrets: GitHub Actions encrypted secrets, test-only values.
6. Trigger: every push to main + workflow_dispatch.

**Open follow-ups (not blocking v1):**
- Playwright in CI — needs preview URL auth strategy. Logged separately.
- Lint passes (ruff + eslint) — Future_Tasks polish pass.
- PR-based gating — depends on Emergent supporting feature-branch workflow.
- Codecov / coverage reporting — Future_Tasks polish pass.

(Original entry retained below for historical context.)

---

## 3 (historical — pre-Chat 21). CI pipeline (anchor: bootstrap smoke test) — P1

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

## 4. Smoke test (`test_c3_governance_smoke.py`) classification — **P2 (architectural)**

- **Surfaced in**: split out of §2 during Chat 15 pre-paste audit (7 May 2026).
- **Severity**: P2 — not a bug, an architectural classification question. Currently masked by `--ignore=tests/test_c3_governance_smoke.py` in the pytest invocation; doesn't gate any prompt.
- **Description**: `tests/test_c3_governance_smoke.py` runs against the public preview URL via HTTP, uses module-scoped persistent data, and has no DB-side teardown path (no `DELETE /api/v1/projects/{id}` endpoint exists; the test never touches the DB directly). Currently masked by `--ignore=tests/test_c3_governance_smoke.py` in the pytest invocation.

  **Reclassified during Chat 15 pre-paste audit.** The original §2 entry coupled this with the FK fix and stated "Hard gate: must be resolved before Prompt 2.4 (Budgets)." That gate language was based on the assumption that the smoke test had a teardown bug that would compound risk in Budgets work. The audit revealed:
  - The smoke test runs HTTP-only against the preview URL by design (not the DB).
  - It has `scope="module"` persistence as a deliberate choice, not a bug.
  - It does not share infrastructure with Budgets work.
  - There is no actionable "teardown bug" to fix — the question is architectural: keep it in `tests/` or move it to a deploy-time probe stage.

  The original §2 gate logic for Prompt 2.4 therefore collapses to §2b alone (the FK fix, resolved in Chat 15). **This entry is no longer a gate for 2.4.**

- **Decision still needed**: classify as a deploy-time probe (move out of `tests/`, run as a separate stage) OR rebuild with DB-side teardown (would require a new `DELETE /api/v1/projects/{id}` endpoint and admin-only RBAC). Likely paired with §3 (CI pipeline) since the test belongs in CI's deploy-probe stage anyway.
- **Owner / Target prompt**: Bundle with §3 (CI), or take as a standalone half-session.

---

## 5. Remaining ON DELETE RESTRICT FKs in migration 0022 — **P2 (debt, no pressure)**

- **Surfaced in**: split out of §2 during Chat 15 pre-paste audit (7 May 2026).
- **Severity**: P2 — debt-with-no-pressure. No current use case requires `DELETE FROM appraisals` to cascade.
- **Description**: Migration 0022 created **5** FKs against `appraisals` with `ON DELETE RESTRICT`. Chat 15 fixed only `appraisal_scenarios.scenario_appraisal_id`. Remaining four (deferred until a use case requires `DELETE FROM appraisals` to cascade):

  - `appraisal_scenarios.parent_scenario_appraisal_id` → `appraisals`
  - `appraisal_revisions.appraisal_id_from` → `appraisals`
  - `appraisal_revisions.appraisal_id_to` → `appraisals`
  - `appraisal_decision_log.appraisal_id` → `appraisals`

  **Hard ceiling on cascade-based teardown of decision-log rows:** `appraisal_decision_log` has `BEFORE DELETE` trigger `trg_decision_log_no_delete` that `RAISE EXCEPTION`s on any DELETE (regulatory append-only). Even with FK cascade, any appraisal with logged decisions cannot be deleted. Cascade for that FK is therefore only useful in a "purge unsigned-off appraisals" workflow.

  Currently no use case exists for `DELETE FROM appraisals` in product flows. Test infrastructure works around RESTRICT via explicit DELETE ordering in the `_wipe()` helper in `test_appraisal_governance.py`. This is debt-with-no-pressure; revisit when an actual workflow needs it.

- **Proposed resolution**: When a use case surfaces (most likely "admin: purge unsigned-off appraisals" or a project-level cascade), bundle into a single migration `00NN_appraisal_chain_cascade.py` that flips all four. Each will need a regression test mirroring `test_appraisal_scenarios_cascade.py`. The decision-log FK is the trickiest — flipping it to CASCADE is mostly cosmetic given the `RAISE EXCEPTION` trigger; might be cleaner to leave that one as RESTRICT and document the asymmetry.
- **Owner / Target prompt**: Open. No target prompt — pull when needed.

---

## 6. Test function names with stale literal numbers — polish

- **Surfaced in**: Chat 22 (CI hardening, 2026-05-18)
- **Severity**: P3 (cosmetic — assertions are correct; only the function
  names are misleading)
- **Description**: Three permission-count test function names carry literal
  numbers that have drifted from their assertions:
  - `tests/test_auth_rbac.py::TestAuthMe::test_me_super_admin_returns_87_permissions`
    (asserts 86 as of Chat 22).
  - `tests/test_auth_rbac.py::TestRoles::test_roles_returns_10_seeded_roles`
    is fine (role count is stable at 10) — listed here only as the sibling
    test class.
  - `tests/test_migration_0025_actuals.py::TestMigration0025Schema::test_alembic_head_is_0025_actuals`
    (asserts `0026_ai_capture_costs_perm` as of Chat 22).
  - `tests/test_patch_3.py::TestPatch3Permissions::test_total_permission_count_is_81`
    (asserts 86 as of Chat 22).

  Chat 22 fixed every assertion but deliberately did not rename functions
  (out of scope per Chat 22 Build Pack §2). Pytest discovers by file, not
  by function name, so the divergence is purely cosmetic — but it makes the
  test file harder to skim and future drift even harder to spot.

- **Proposed resolution**: Single polish pass that does two things in
  lockstep:
  1. Rename each function to a count-agnostic style, e.g.
     `test_me_super_admin_returns_seeded_permission_count`,
     `test_total_permission_count_matches_catalogue`,
     `test_alembic_head_is_current`.
  2. Swap each hard-coded `assert total == 86` for
     `assert total == len(PERMISSION_CATALOGUE)` (and analogous for the
     alembic head, e.g. read from `alembic heads` via
     `B._alembic_heads()`) so the assertions become self-updating and
     don't drift again next time a migration or permission lands.

  Touches no production code, no migrations, no seeds — only test files.
  Single short prompt, half-session work.

- **Owner / Target prompt**: Open. Pull when next test-drift episode
  surfaces (cheap to absorb at the same time).

---

## 7. Replace 19 cosmetic `load_dotenv("/app/backend/.env")` hardcodes — polish

- **Surfaced in**: Chat 22 follow-up (CI run #5 diagnosis, 2026-05-18)
- **Severity**: P3 (cosmetic — does not break CI; calls silently no-op when
  the path is absent, and CI sets env vars via the workflow env block
  anyway)
- **Description**: 19 test files do `load_dotenv("/app/backend/.env")` at
  module import. The literal `/app/backend` is sandbox-specific (Emergent
  container layout) and won't resolve on any other host (GitHub Actions
  runners use `/home/runner/work/SY-Hub/SY-Hub/backend`, fork previews
  vary, real developers' laptops vary). The calls work in the sandbox by
  coincidence and silently no-op everywhere else.

  Affected files (from `grep -rln 'load_dotenv(.*/app' backend/tests/`):
  `test_audit_log.py`, `test_audit_remediation.py`,
  `test_audit_remediation_patch_2.py`, `test_entities_api.py`, `test_mfa.py`,
  `test_notifications.py`, `test_password_complexity.py`,
  `test_reference_data.py`, `test_retro_wires.py`, `test_scheduler_jobs.py`,
  `test_sessions_history_reset.py`, `test_system_config.py`,
  `test_user_edit.py`, plus ~6 more.

  Chat 22 follow-up §B already migrated the two BREAKING hardcodes
  (`BACKEND_DIR` in `test_bootstrap.py:40` and `cwd` in
  `test_migration_0025_actuals.py:298`) to
  `Path(__file__).resolve().parents[1]`. These 19 are the cosmetic
  remainder — same pattern, same fix, no urgency.

- **Proposed resolution**: Single sed-style pass across the 19 files
  replacing:
  ```python
  load_dotenv("/app/backend/.env")
  ```
  with:
  ```python
  from pathlib import Path  # if not already imported
  load_dotenv(Path(__file__).resolve().parents[1] / ".env")
  ```
  Touches only test files, no production code, no migrations, no
  permissions, no seeds. Half-session work.

- **Owner / Target prompt**: Open. Pull when next test-hygiene episode
  surfaces.

---

## 8. Decide explicit `COLLATE` for entity name `ORDER BY` (production deployment)

- **Surfaced in**: Chat 22 follow-up (CI run #5 diagnosis, 2026-05-18)
- **Severity**: P3 (product decision, not a bug — deferred until production
  deployment lands)
- **Description**: `app/routers/entities.py:194` does
  `.order_by(Entity.name.asc())` with no explicit `COLLATE` clause, so
  the sort uses the Postgres cluster's default collation. The sandbox
  cluster is on `C.UTF-8` (codepoint sort) and tests use Python's
  `sorted()` as the oracle (also codepoint). CI was failing on
  `postgres:16`'s glibc `en_US.utf8` (linguistic sort, treats parentheses
  as low-weight tiebreakers) — Chat 22 follow-up §A fixed this by pinning
  the CI postgres container to `C.UTF-8` via `POSTGRES_INITDB_ARGS`. That
  keeps CI green and matches sandbox bit-for-bit, but the question of
  what production should use was deliberately deferred.

  The deferred question: when SY Homes' production Postgres is
  provisioned (cloud-managed PG, self-hosted, etc.), should the entity
  name ORDER BY be:
  1. **Deterministic codepoint** (`.order_by(func.collate(Entity.name, "C").asc())`)
     — same order everywhere regardless of cluster locale; matches test
     expectations on any cluster; mildly unusual UX (parentheses sort
     distinctly from spaces).
  2. **Linguistic** (default; whatever the production cluster collation
     is) — humans see locale-appropriate sort (e.g. en_GB.utf8 ignores
     punctuation at primary level); tests would need to relax to a
     subset-membership assertion rather than codepoint-equality, or the
     production cluster would need to be initdb'd with `C.UTF-8` to
     match (the CI approach extended to prod).

- **Proposed resolution**: Discuss at deployment-planning time. If
  option 1 is chosen: one-line source change in
  `app/routers/entities.py:194` + drop the `POSTGRES_INITDB_ARGS` pin
  from CI (no longer needed). If option 2 + match-prod-to-test: keep
  the CI pin and document the production initdb args in a runbook.

- **Owner / Target prompt**: Open. Triggered by first production
  deployment work, not by ongoing CI/test polish.

---

## 9. P3 polish — dead `_admin_user` helper in `tests/test_budgets.py`

- **Status**: Open (P3 cleanup)
- **Anchor**: Chat 22 CI hardening Follow-up 6 (CHANGELOG `2026-05-18`).
  When fixing 2 stale-literal lookups (lines 2404-2406, 2657-2660) we
  noted `_admin_user(db)` at `tests/test_budgets.py:489-491` is never
  called — `grep _admin_user(` across `tests/` returns zero matches
  outside the def itself. Safe to delete (5 lines including the
  function signature + the `from app.models.user import User` import
  inside it).

- **Why deferred**: out of scope for run-#6 CI hardening fix (strict
  test-only-no-other-test-files rule). Bundle with the next polish
  pass over `tests/test_budgets.py`.

- **Owner / Target prompt**: Next time anyone touches the file.

---

## 10. MFA-on-test-users runbook is operational debt — **P2 (debt)**

- **What.** Synthetic test users (`test-*@example.test`) have MFA enforced by their role-permission policy. Live-browser smoke testing (Playwright / preview env walkthroughs) currently requires a manual SQL `UPDATE` to clear `mfa_enabled`/`mfa_secret_encrypted` etc. — runbook recorded in `/app/memory/test_credentials.md`.
- **Why this exists.** `conftest.py::engine` already disables MFA for the pytest fixtures, but the FastAPI 2FA-enforcement middleware checks `users.mfa_enabled` on every request regardless of the role's `requires_mfa` flag, so the browser path can't reach `/projects/*` without TOTP enrolment.
- **Why it's debt.** Production MFA enforcement shouldn't depend on a per-environment workaround. The right fix is either (a) a `--test-fixture` flag on the auth middleware that scope-skips MFA for `*@example.test` emails when `ENV != production`, or (b) a `dev_mode_skip_mfa` setting that the bootstrap runner toggles for synthetic users only.
- **Severity.** P2. Doesn't block any agent work — runbook keeps Chat 23 / 24 unblocked. But the divergence between pytest-OK and live-browser-OK is a footgun for the next agent who doesn't read `test_credentials.md` carefully.
- **Where.** `backend/app/middleware/mfa_enforcement.py` (or wherever the enforcement gate lives) + `backend/app/bootstrap.py::seed_test_users`.

## 11. `/api` vs `/api/v1` path-prefix drift audit — **P1 (silent-correctness risk)**

- **What.** During the §R7 spot-check, the operator hit "every line rendered as Uncategorised" against a freshly-seeded budget. Root cause: `frontend/src/hooks/costCodes.js::fetchCostCodes` was calling `/v1/projects/${projectId}/cost-codes` but `cost_codes_router` is mounted under `api_router` (server.py:140), NOT `v1_router` (server.py:148-158). The hook silently 404'd, returned an empty array, the cost-code Map was empty, and `groupLinesByCategory` collapsed everything to `— Uncategorised —`. **The bug shipped with §R3 (Chat 23) and was undetected through R3/R4/R5/R6 + 223 Jest tests because every component test either mocks `useCostCodes` directly or routes through an MSW handler that normalises the path.**
- **Why this exists.** The backend has two parallel mount conventions:
  - `api_router` directly under `/api/...` — auth, users, roles, perms, sessions, projects, entities, **cost-codes**, meta, audit, login_history.
  - `v1_router` under `/api/v1/...` — appraisals, appraisal_governance, budgets, actuals, ai_capture, inbound, notifications, reference_data, system_config, user_preferences.
  Frontend axios `baseURL = ${REACT_APP_BACKEND_URL}/api`, so callers must explicitly include `/v1/` for the v1 mount and explicitly omit it for the `/api`-only mount. There's no compile-time check, no runtime route table — a typo silently 404s.
- **Fixes landed Chat 23 §R7.5 (this entry).**
  - `hooks/costCodes.js`: corrected path to `/projects/${projectId}/cost-codes` AND fixed `buildCostCodeMap` to key by `cost_code_id` (FK) instead of `id` (join-table PK). The keying bug would have masked any future correct path fix until both were addressed together.
  - `hooks/__tests__/costCodes.test.jsx` — 4 regression pins: path assertion (positive + hard negative on `/v1/`), FK-keyed map lookups, fallback to `id` for minimal test fixtures, defensive skip for malformed rows.
- **What still needs auditing (P1, before next agent ships).** Sweep every `api.*(/...)` call in `frontend/src/` against the backend mount table. Pass criteria: each path either matches an `api_router.include_router(...)` mount (no `/v1/` prefix on the call) OR matches a `v1_router.include_router(...)` mount (`/v1/` prefix on the call). Initial survey already done:
  - Confirmed correct under `/v1/`: `actuals.js`, `aiCapture.js`, `budgets.js`, `NotificationBell.jsx`, `NotificationsPage.jsx`, `SdltRatesPage.jsx`, `ConfigPage.jsx`, `AppraisalDefaultsPage.jsx`, `PromoteForm.jsx::useEntities` (matches `/api/v1/entities` from reference_data), `ProjectPicker.jsx::useProjects` (NB: `/v1/projects` collides with `/projects` — needs explicit verification).
  - Confirmed correct under `/api` (no v1): `AuthContext.jsx::/auth/*`, `RoleAssignmentModal.jsx::/roles + /entities`, `MfaEnrollDialog.jsx::/auth/mfa/*`, `useTenant.js::/meta/*`, `UsersList.jsx::/users`, `RolesAndPermissions.jsx::/roles + /permissions`, `ProjectsList.jsx::/projects`, `ProjectNew.jsx`, `ProjectDetail.jsx`, `CostCodesList.jsx`, `CostCodeDetail.jsx::/cost-code-sections`.
  - **Inconsistencies to verify**: `PromoteForm.jsx:36` uses `/v1/entities` while `CreateActualSheet.jsx:38` uses `/entities`. One of these must be wrong — same as the cost-codes bug, just less visible because the entities list is short and most rendered data comes from a different field. Audit + reconcile before R8.
- **Proposed permanent resolution.** Introduce a typed API client surface (`lib/api/{module}.js` per existing pattern) where the route literal lives ONCE per endpoint and is exercised by a dedicated `__tests__/{module}.url-contract.test.js` pin per endpoint. Bonus: a backend smoke endpoint `/api/internal/route-table` returning the canonical mount table that a once-per-CI Jest test cross-checks against. Cost ~1 day, eliminates the entire class of bug.
- **Severity.** P1. This bug class produces silent 404s with empty-fallback semantics — exactly the kind of failure that ships to operator without triggering a test failure. The audit MUST land before R8 to avoid another spot-check derailment.
- **Surfaced in.** Chat 23 §R7 operator spot-check (this session).

## 12. (placeholder — future entries appended here)
