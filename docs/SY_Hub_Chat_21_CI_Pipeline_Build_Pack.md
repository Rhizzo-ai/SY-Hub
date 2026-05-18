# Build Pack v-final — Chat 21: CI Pipeline (anchor: bootstrap smoke + backend pytest + frontend build/bundle/Jest)

**Unit of work:** `ci-pipeline-v1` (logical label; Emergent's Save-to-GitHub will land as auto-commits to `main` — no real branch will exist on `Rhizzo-ai/SY-Hub`. See chat-14-closing §11.)

**Anchor:** Future_Tasks §3 — open since Chat 14 (5 May 2026), deferred through Chats 15–20. P1 priority. Catches regressions before they reach the operator; without it, the only quality gate is agent self-report (which has been shown to drift — see Chat 14 §12 Future_Tasks gap).

**Gates:** Prompt 2.7 (Subcontractor module, ~12+ hour build). CI insurance pays off before that lands.

**Estimated size:** Half a session. One workflow YAML file (~300 lines) + README badge + CHANGELOG entry + Future_Tasks §3 annotation. No source code touched. No new migrations. No new permissions. No new tests.

**Build Pack version:** v-final (post 4-pass audit).

### Audit-pass changelog

**v1 → v2 (Pass 2, fresh-reader defect hunt):**
- **Critical 1 — Redundant seed_test_users step removed.** `python -m app.bootstrap` invokes `seed_test_users.py` as subprocess in its `seed_test_users` step (confirmed in `backend/app/bootstrap.py::seed_test_users`); the explicit second call was redundant and obscured the contract.
- **Critical 2 — Backend HTTP server start step added.** Multiple pytest test files (`test_audit_remediation_patch_2.py`, `test_ai_capture.py`, all tests using `tests.conftest::login_with_auto_enroll`) hit `BASE_URL` via `requests.post`. They require a running backend on `localhost:8001`. Workflow now starts uvicorn in background after bootstrap and waits for `/api/health` before running pytest.
- **Critical 3 — Postmark env vars added.** `POSTMARK_INBOUND_ENABLED=true` and `POSTMARK_INBOUND_SECRET=test-secret-do-not-use` (matches the test fallback in `test_ai_capture.py`) added to job-level env block. Required for the Postmark webhook tests.
- **Medium 4 — `.gitignore` defensive check added** to §R6 to confirm `.github/workflows/ci.yml` is not accidentally ignored.
- **Medium 5 — `REACT_APP_BACKEND_URL` set at job level** to `http://localhost:8001` for consistency with how tests resolve `BASE_URL`.
- **Minor 6 — Bundle-size shell pipe hardened** with `tr -d ' '` after `wc -c` (3 occurrences across baseline, frontend job, local validation).
- **Minor 7 — Validate-secrets step moved earlier**, before pip install, so misconfigured runs fail in ~5s instead of ~2 min.

**v2 → v3 (Pass 3, doc-vs-impl alignment):**
- §2 In-scope list updated to match v2 workflow (no separate seed_test_users step; added Start backend HTTP server, REACT_APP_BACKEND_URL, CI=true/false split, `tr -d ' '` pipe).
- §4 Acceptance criteria updated to include the v2 additions (Validate-secrets BEFORE pip install, Start backend with `/api/health` wait, POSTMARK_* env vars, REACT_APP_BACKEND_URL, dump-uvicorn-on-failure, `tr -d ' '`).
- §R5.2 CHANGELOG entry text updated to reflect that bootstrap handles test user seeding internally.
- §R8 file-commit expectations: removed confusing "app/CHANGELOG.md" alternative path; canonical path is `/app/CHANGELOG.md` (repo-root `CHANGELOG.md`).
- §7 Stop-gates: added R6.1b (gitignore would prevent commit).
- §R5 self-report template (R2+R3, R6) updated to include v2 additions and gitignore check.

**v3 → v-final (Pass 4, fresh-eyes review):**
- §R4 secrets table: clarified that `CI_TEST_USER_PASSWORD` MUST be the literal `TestUser-Dev-2026!` (hard requirement — pytest fixtures hardcode the literal; mismatch reds the suite).
- §R5 self-report R7: aligned `CI_TEST_USER_PASSWORD` wording to match §R4 (REQUIRED, not just suggested).
- §6 chat-end ritual: extended file checklist to include the Build Pack file itself and `docs/chat-summaries/chat-21-closing.md` (matches chat-14/15/16 commit pattern).
- §R5 self-report R8: extended file-commit checklist to include the Build Pack and closing summary.

---

## §0 — Pre-flight

Before any other action: `cd /app && git pull origin main`. The sandbox may have been forked or rebuilt; resync first.

If the container is a fresh fork (no Postgres, no `on-restart.sh`), follow the provisioning runbook in `/app/backend/app/bootstrap.py`'s module docstring before proceeding. As of Track 8 P0 (Chat 18, commit `b5ebdf3`), `provision_postgres.sh` is auto-wired into `on-restart.sh` — fresh forks should self-recover.

---

## §1 — Background, scope, and hard constraints

### Why now

CI has been deferred through six chats since first surfaced in Chat 14. The cost of running without it has been documented:

- Chat 14: 5× recurrences of the fresh-DB bootstrap chicken-and-egg, each a 15–30 min manual hot-fix.
- Chat 14 §12: agent self-report claimed `Future_Tasks.md` updates that never landed on `main`. Caught only by post-close cleanup. Spot-check ritual added to compensate, but ritual ≠ structural guard.
- Chat 16 §11 (per Pre-2.4 Cleanup Build Pack): "self-reports must be spot-checked against actual GitHub state" — explicitly flagged as a workaround, not a fix.
- Chats 17–20: 7+ pod-recycle interruptions consumed ~30 min/chat of session time before Track 8 P0 retired the worst of it.

Prompt 2.7 (Subcontractor module) is a 12+ hour build with high coupling to budgets/actuals/RBAC. Shipping it without CI means the only failure-mode catcher is the same self-report that has already drifted in production. This Build Pack ships CI before 2.7 starts.

### Operator decisions locked at chat open

1. **Runner:** GitHub Actions (Q1a).
2. **Gate model:** post-push alert + status badge; operator decides revert manually. No pre-merge gating (Q2a). Emergent's auto-commit-to-main model precludes pre-merge gating without a process change.
3. **Scope v1:** bootstrap smoke + backend pytest + frontend build + bundle-size cap + Jest unit tests (Q3 a+b+c+d). Playwright + lint deferred (Q3 e+f explicitly out of scope).
4. **Postgres in CI:** service container, not testcontainers-python (Q4a).
5. **Secrets:** GitHub Actions encrypted secrets, test-only values (Q5a). Two secrets required: `CI_BOOTSTRAP_ADMIN_PASSWORD`, `CI_TEST_USER_PASSWORD`.
6. **Trigger:** every push to `main` (Q6a).

### Hard constraints (Mandatory carry-forwards)

1. **I11 bundle hard cap is 437,000 bytes gzipped on `build/static/js/main.<hash>.js`.** CI MUST enforce this gate. Reference: chat-19c-closing.md §R8.3 STOP gate 2.
2. **Permission catalogue drift:** detected by existing pytest tests (`test_auth_rbac.py::TestAuthMe::test_me_super_admin_returns_*_permissions` and siblings). No new CI step needed — running pytest catches it.
3. **pgcrypto extension required before `alembic upgrade`.** Migrations 0011/0012/0015/0019/0022 use `gen_random_uuid()` server-defaults. The CI workflow MUST create the extension before invoking bootstrap.
4. **pytest invocation in CI:** `python -m pytest --ignore=tests/test_c3_governance_smoke.py` per backend/README.md "Running tests" section and PRD.md "How to run locally". The `--ignore` flag stays — Future_Tasks §4 (smoke test reclassification) is deferred.
5. **Migration revision names ≤ 32 chars** (varchar(32) on `alembic_version.version_num`) — not relevant in this Build Pack (no new migration) but recorded for completeness.

### Source-of-truth points

- Bootstrap orchestrator entry point: `python -m app.bootstrap` from `/app/backend` directory (chat-14 §1 final state; chat-15 §3 verified; chat-19A through chat-20 all use this invocation).
- Bootstrap env-var contract (from `/app/backend/app/bootstrap.py` module docstring + chat-18 pod-recovery preamble):
  - `DATABASE_URL` — required.
  - `BOOTSTRAP_ADMIN_EMAIL` — required.
  - `BOOTSTRAP_ADMIN_PASSWORD` — required.
  - `BOOTSTRAP_ADMIN_FIRST_NAME` — required.
  - `BOOTSTRAP_ADMIN_LAST_NAME` — required.
  - `JWT_SECRET` — required.
  - `TEST_USER_PASSWORD` — required (for seed_test_users.py downstream).
  - `MFA_ENCRYPTION_KEY` — auto-generated on first boot if absent (per backend/README "Environment setup" table).
  - `APP_ENV` — recommended (`test` for CI).
  - `SYHOMES_RATE_LIMIT_DISABLED` — recommended (`1` for CI; bypasses per-IP/email rate limits during pytest).
- Frontend build command: `yarn build` (CRA via craco; outputs to `frontend/build/`).
- Frontend Jest command: `yarn test --watchAll=false` (per craco test script).
- Yarn lockfile: `frontend/yarn.lock`, yarn version `1.22.22`.
- Backend pyproject.toml at `backend/pyproject.toml` configures `pythonpath = ["."]`, `testpaths = ["tests"]`, `addopts = "-q --tb=short"`.
- Backend requirements.txt at `backend/requirements.txt`.

### Why these are settled

Every fact in "Source-of-truth points" was verified via `project_knowledge_search` during pre-Build-Pack drafting. Do NOT re-derive from memory. Do NOT assume newer paths or invocations.

---

## §2 — In scope / Out of scope

### In scope (this Build Pack)

1. Create `.github/workflows/ci.yml`.
2. Two parallel jobs: `backend`, `frontend`.
3. Backend job:
   - Postgres 16 service container (PG16, role `syhomes`, password `syhomes_dev`, db `syhomes`).
   - `CREATE EXTENSION pgcrypto` step before bootstrap.
   - Bootstrap smoke: `python -m app.bootstrap` returns rc=0 (bootstrap itself
     seeds test users as Step 9 via subprocess; no separate seed_test_users step).
   - Start `uvicorn server:app` in background (HTTP-driven pytest tests need
     it on `localhost:8001`).
   - Wait up to 30s for `/api/health` to respond before pytest.
   - Run pytest: `python -m pytest --ignore=tests/test_c3_governance_smoke.py`.
4. Frontend job:
   - Set up Node 20 + yarn 1.22.x.
   - `yarn install --frozen-lockfile`.
   - `yarn build` (CRA via craco) with `CI=false` and `REACT_APP_BACKEND_URL=http://localhost:8001`.
   - Bundle-size gate: assert `gzip -c build/static/js/main.*.js | wc -c | tr -d ' '` ≤ 437,000 bytes.
   - Run Jest: `yarn test --watchAll=false` with `CI=true`.
5. Trigger: every push to `main`, plus `workflow_dispatch` for manual runs.
6. Concurrency control: cancel in-progress runs for the same branch when a newer commit lands.
7. README.md: add status badge linking to the workflow.
8. CHANGELOG.md: prepend new H2 entry titled "Chat 21 — CI pipeline shipped" (per-chat H2 pattern, mirrors chat-14/15/16/17/18/19A/19B/19C/20 entries).
9. `/app/docs/SY_Homes_Future_Tasks.md` §3: annotate as `RESOLVED` with date + commit reference (mirrors chat-15's treatment of §2; preserves original §3 content as historical record).
10. Operator-side documentation: §R4 below explains the two secrets the operator must add via GitHub UI before the first CI run.

### Out of scope (DO NOT bundle)

If temptation arises, log to Future_Tasks and move on.

- **Playwright E2E in CI.** Operator deferred (Q3e). Preview URLs only exist in Emergent sandbox; auth flow requires sandbox env vars not available in GHA. Separate effort.
- **Lint passes** (ruff, eslint). Operator deferred (Q3f). Low-value first iteration.
- **PR-based gating.** Operator chose post-push alert model (Q2a). Changing Emergent's git workflow is a separate process change.
- **Self-hosted runner.** Operator chose GHA-hosted (Q1a).
- **Caching strategy beyond GHA built-in.** Use `actions/setup-python@v5` cache and `actions/setup-node@v4` cache. Don't invent new caching.
- **Multi-Postgres-version matrix.** Single PG16, matching production.
- **Multi-Python-version matrix.** Single Python 3.11.
- **Coverage reporting / codecov integration.** Future_Tasks if needed.
- **Slack notifications / webhook fan-out.** GitHub's default email-on-failure handles this for v1.
- **Bundle-size assertion on chunks other than main.** I11 hard cap is on `main.<hash>.js`. Chunks (e.g. `ai-capture-costs.<hash>.chunk.js`) are off the cap per chat-20 close.
- **Removing the `--ignore=tests/test_c3_governance_smoke.py` flag.** Future_Tasks §4 work; deferred.
- **Any change to bootstrap.py, on-restart.sh, or provision_postgres.sh.** Track 8 work is complete and unchanged here.
- **Any change to backend source, frontend source, models, schemas, routers, services, migrations, seeds.** This Build Pack is infra-only.
- **Any new tests** (backend or frontend). CI runs the existing suite; no test additions.
- **Pre-2.7 prep work** (subcontractor module). Separate Build Pack.

---

## §3 — Build plan (R0–R8)

### §R0 — Baseline (STOP gate)

Run these in order. STOP and self-report if any step deviates from expected.

```bash
# 0.1 — Resync
cd /app
git pull --ff-only origin main
git rev-parse HEAD                          # record SHA
git status                                  # expect clean

# 0.2 — Confirm CI workflow does NOT exist (green-field gate)
test ! -e /app/.github/workflows/ci.yml || \
  { echo "STOP: .github/workflows/ci.yml already exists"; exit 1; }
ls -la /app/.github/ 2>/dev/null || echo "(.github directory not present — expected)"

# 0.3 — Confirm bootstrap orchestrator is healthy
cd /app/backend
python -m app.bootstrap                     # expect rc=0
alembic current                             # expect 0026_ai_capture_costs_perm
# (If alembic head differs, the workflow YAML's migration-head-printout
#  step still works — but the test count baseline expectations shift.)

# 0.4 — Capture current test counts (informational; not baked into CI as
#       hardcoded numbers — CI uses pass/fail not count assertions)
python -m pytest --ignore=tests/test_c3_governance_smoke.py -q 2>&1 | tail -3
# expect: ~790–805 passed (number floats with operator's local migrations)

cd /app/frontend
yarn test --watchAll=false 2>&1 | tail -5
# expect: ~118–151 passed (number floats with operator's local Jest additions)

yarn build 2>&1 | grep "main\." | head -1
# expect: a "main.<hash>.js" line with size ~424.16 kB gzipped

# 0.5 — Bundle size baseline (record actual gzipped bytes)
MAIN=$(ls build/static/js/main.*.js | head -1)
SIZE_BYTES=$(gzip -c "$MAIN" | wc -c | tr -d ' ')
echo "main gzipped bytes: $SIZE_BYTES"
test "$SIZE_BYTES" -le 437000 || \
  { echo "STOP: baseline bundle already over 437 kB cap"; exit 1; }

# 0.6 — Confirm secrets will be available at first run
# (Agent cannot read GitHub Secrets. Operator confirms separately in R4.
#  Agent records expected secret names: CI_BOOTSTRAP_ADMIN_PASSWORD,
#  CI_TEST_USER_PASSWORD. Workflow must reference these exact names.)
```

**Self-report and STOP if:**
- `.github/workflows/ci.yml` already exists.
- Bootstrap rc ≠ 0.
- pytest baseline not green.
- yarn build fails.
- Baseline bundle already over 437 kB (gates the whole exercise).

---

### §R1 — Confirm live-code shapes (read-only)

Before writing the workflow, read these files into context. Do NOT modify them.

```bash
# 1.1 — Bootstrap docstring (the env-var contract source of truth)
sed -n '1,150p' /app/backend/app/bootstrap.py

# 1.2 — pytest config
cat /app/backend/pyproject.toml

# 1.3 — Backend requirements pin
head -40 /app/backend/requirements.txt

# 1.4 — Frontend package scripts
python3 -c "import json; d=json.load(open('/app/frontend/package.json')); print(json.dumps(d['scripts'], indent=2))"

# 1.5 — Confirm yarn.lock is up to date (frozen-lockfile will fail otherwise)
cd /app/frontend && yarn install --frozen-lockfile --check-files 2>&1 | tail -5
```

**Self-report:**
- Bootstrap env-var list verbatim (record the required variables — should match §1 "Source-of-truth points" list).
- pyproject.toml [tool.pytest.ini_options] content verbatim.
- Confirmed scripts: `build`, `test`, `start` invocations.
- Yarn frozen-lockfile check passes.

If any of these diverge from §1's expectations, STOP and self-report — the workflow YAML in R2/R3 assumes the §1 facts.

---

### §R2 — Create `.github/workflows/ci.yml` — workflow scaffold and backend job

Create the file at `/app/.github/workflows/ci.yml`. Full file content shown below in two halves; concatenate R2 + R3 verbatim into a single YAML file.

```yaml
# .github/workflows/ci.yml
#
# SY Hub CI pipeline. Anchor: Future_Tasks §3, open since Chat 14 (5 May 2026).
# Shipped by Chat 21 (Build Pack v-final).
#
# Trigger model:
#   - Every push to main (Emergent's auto-commits land here).
#   - Manual via workflow_dispatch (operator can re-run after fixing infra).
#
# Gate model (operator decision Q2a, Chat 21):
#   - Post-push, NOT pre-merge. Red CI surfaces via:
#     (a) GitHub's default email-on-failure to repo owner (Rhys).
#     (b) Status badge on README.md.
#   - Operator decides whether to revert. CI cannot block a push because
#     Emergent's Save-to-GitHub pushes direct to main as auto-commits.
#
# Scope v1 (operator decision Q3 a+b+c+d, Chat 21):
#   backend job:  bootstrap smoke (anchor)  +  pytest
#   frontend job: yarn build  +  bundle-size gate (I11)  +  yarn test (Jest)
#
# Out of v1 scope (deferred):
#   - Playwright (Q3e — preview URL auth too fiddly for GHA).
#   - Lint (Q3f — low value first iteration).
#
# Secrets required (set via repo Settings → Secrets and variables → Actions):
#   CI_BOOTSTRAP_ADMIN_PASSWORD  — test-only password for the seeded super_admin.
#   CI_TEST_USER_PASSWORD        — test-only password for the seven test users.
# Suggested values: any 16+ char string that is NOT a production password.

name: CI

on:
  push:
    branches: [main]
  workflow_dispatch:

# Cancel in-progress runs on the same ref when a newer commit lands.
# Prevents CI queue pile-up when Emergent ships multiple auto-commits back-to-back.
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:

  # ---------------------------------------------------------------------------
  # Backend job
  # ---------------------------------------------------------------------------
  # Bootstrap smoke is the anchor — see Future_Tasks §3 history.
  # Postgres 16 service container provisions a clean DB per run.
  # pgcrypto must be created before alembic upgrade (mig 0011/0012/0015/0019/0022).
  # ---------------------------------------------------------------------------
  backend:
    name: backend (bootstrap + pytest)
    runs-on: ubuntu-latest
    timeout-minutes: 15

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: syhomes
          POSTGRES_PASSWORD: syhomes_dev
          POSTGRES_DB: syhomes
        ports:
          - 5432:5432
        # Wait for Postgres to be accepting connections before any step runs.
        options: >-
          --health-cmd "pg_isready -U syhomes -d syhomes"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 12

    env:
      # Stable across all steps in this job. JWT_SECRET varies per run to defend
      # against accidental test cross-talk; MFA_ENCRYPTION_KEY is omitted so
      # bootstrap auto-generates one (per backend/README.md "Environment setup").
      #
      # POSTMARK_* required by tests/test_ai_capture.py (per its docstring:
      # "POSTMARK_INBOUND_ENABLED=true MUST be set in backend/.env for these
      # tests"). The secret value matches the test's fallback default so
      # both backend and test agree on what to verify against.
      #
      # REACT_APP_BACKEND_URL is read by tests that hit BASE_URL via requests
      # (e.g. test_audit_remediation_patch_2.py, test_ai_capture.py). Setting
      # it explicitly is clearer than relying on the http://localhost:8001
      # fallback inside each test module.
      DATABASE_URL: postgresql://syhomes:syhomes_dev@localhost:5432/syhomes
      BOOTSTRAP_ADMIN_EMAIL: ci-admin@example.test
      BOOTSTRAP_ADMIN_PASSWORD: ${{ secrets.CI_BOOTSTRAP_ADMIN_PASSWORD }}
      BOOTSTRAP_ADMIN_FIRST_NAME: CI
      BOOTSTRAP_ADMIN_LAST_NAME: Admin
      JWT_SECRET: ci-jwt-secret-${{ github.run_id }}-${{ github.run_attempt }}
      TEST_USER_PASSWORD: ${{ secrets.CI_TEST_USER_PASSWORD }}
      APP_ENV: test
      SYHOMES_RATE_LIMIT_DISABLED: "1"
      REACT_APP_BACKEND_URL: http://localhost:8001
      POSTMARK_INBOUND_ENABLED: "true"
      POSTMARK_INBOUND_SECRET: test-secret-do-not-use

    steps:

      - name: Check out repository
        uses: actions/checkout@v4

      - name: Validate secrets are configured
        # Run BEFORE pip install so misconfigured runs fail in ~5s, not ~2 min.
        run: |
          if [ -z "${{ secrets.CI_BOOTSTRAP_ADMIN_PASSWORD }}" ]; then
            echo "::error::Secret CI_BOOTSTRAP_ADMIN_PASSWORD is not set. See workflow comments."
            exit 1
          fi
          if [ -z "${{ secrets.CI_TEST_USER_PASSWORD }}" ]; then
            echo "::error::Secret CI_TEST_USER_PASSWORD is not set. See workflow comments."
            exit 1
          fi

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip
          cache-dependency-path: backend/requirements.txt

      - name: Install backend dependencies
        working-directory: backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          # psql client used by the pgcrypto step below.
          sudo apt-get update -qq
          sudo apt-get install -y --no-install-recommends postgresql-client

      - name: Create pgcrypto extension
        # Required before alembic upgrade — migrations 0011/0012/0015/0019/0022
        # use gen_random_uuid() server-defaults from pgcrypto.
        env:
          PGPASSWORD: syhomes_dev
        run: |
          psql -h localhost -U syhomes -d syhomes \
               -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

      - name: Bootstrap smoke (anchor — Future_Tasks §3)
        # python -m app.bootstrap is idempotent. Per backend/app/bootstrap.py,
        # the orchestrator runs:
        #   env-var precheck → wait_for_postgres → pg advisory lock →
        #   detect_db_state → alembic upgrade head → seed (tenant+entities) →
        #   seed_rbac → seed_system_config → seed_test_users (subprocess call
        #   to scripts/seed_test_users.py) → verify_invariants → release lock.
        # Exit code: 0 on success, non-zero on any step failure (see EXIT_*
        # constants in bootstrap.py).
        # Test users are seeded by bootstrap's seed_test_users step; do NOT
        # re-invoke scripts/seed_test_users.py separately.
        working-directory: backend
        run: |
          python -m app.bootstrap
          echo "::notice::Bootstrap rc=0 — alembic upgraded, RBAC seeded, test users seeded, invariants verified."

      - name: Print migration head + permission count + role count
        # Informational. Failure here is non-fatal but surfaces drift.
        # Permission count drift is also caught by the existing pytest
        # test_auth_rbac.py assertions; this is for human-readable visibility.
        env:
          PGPASSWORD: syhomes_dev
        continue-on-error: true
        run: |
          cd backend
          HEAD=$(alembic current 2>&1 | tail -1)
          PERMS=$(psql -h localhost -U syhomes -d syhomes -tAc "SELECT COUNT(*) FROM permissions;" | tr -d ' ')
          ROLES=$(psql -h localhost -U syhomes -d syhomes -tAc "SELECT COUNT(*) FROM roles;" | tr -d ' ')
          echo "::notice::Alembic head: $HEAD"
          echo "::notice::Permissions: $PERMS"
          echo "::notice::Roles: $ROLES"

      - name: Start backend HTTP server (for HTTP-driven pytest tests)
        # Many pytest tests hit BASE_URL via requests.post (e.g.
        # tests/conftest::login_with_auto_enroll, test_audit_remediation_patch_2,
        # test_ai_capture's Postmark webhook 401/422/202 tests). They require
        # a running backend on http://localhost:8001.
        #
        # Operator's local sandbox satisfies this via supervisor; CI replicates
        # with a backgrounded uvicorn. The runner VM is the same across steps
        # in a job, so background processes persist (GHA does not container-
        # boundary steps within a job).
        #
        # We log uvicorn output to /tmp/uvicorn.log so pytest output stays clean
        # and the log is recoverable on failure.
        working-directory: backend
        run: |
          python -m uvicorn server:app --host 0.0.0.0 --port 8001 \
            > /tmp/uvicorn.log 2>&1 &
          echo $! > /tmp/uvicorn.pid
          echo "Backend started with PID $(cat /tmp/uvicorn.pid)"
          # Wait up to 30s for /api/health to become responsive.
          for i in $(seq 1 30); do
            if curl -fsS http://localhost:8001/api/health > /dev/null 2>&1; then
              echo "Backend health-check OK after ${i}s"
              break
            fi
            sleep 1
          done
          # Final health-check; fail fast with log dump if not up.
          if ! curl -fsS http://localhost:8001/api/health; then
            echo "::error::Backend failed to respond on /api/health after 30s"
            echo "--- /tmp/uvicorn.log (last 50 lines) ---"
            tail -50 /tmp/uvicorn.log
            exit 1
          fi
          echo ""
          echo "::notice::Backend ready on http://localhost:8001"

      - name: Run backend tests
        # python -m pytest is preferred in CI per backend/README.md "Running tests".
        # The --ignore flag stays per Future_Tasks §4 (smoke test reclassification
        # deferred; --ignore is NOT in scope for Chat 21).
        working-directory: backend
        run: |
          python -m pytest --ignore=tests/test_c3_governance_smoke.py

      - name: Dump uvicorn log on failure
        # Only fires if a prior step failed. Helps diagnose backend-side
        # exceptions raised during HTTP-driven tests.
        if: failure()
        run: |
          echo "--- /tmp/uvicorn.log ---"
          cat /tmp/uvicorn.log || echo "(no uvicorn log captured)"

  # ---------------------------------------------------------------------------
  # Frontend job
  # ---------------------------------------------------------------------------
```

---

### §R3 — Frontend CI job (continues `ci.yml`)

Continue writing the SAME file. Append after the backend job block.

```yaml
  # Build CRA bundle, enforce the I11 437 kB hard cap on main.<hash>.js
  # gzipped, run Jest unit tests.
  # ---------------------------------------------------------------------------
  frontend:
    name: frontend (build + bundle gate + jest)
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:

      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Node 20
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: yarn
          cache-dependency-path: frontend/yarn.lock

      - name: Install frontend dependencies
        working-directory: frontend
        run: yarn install --frozen-lockfile --non-interactive

      - name: Build frontend (CRA via craco)
        # CI=false: CRA treats warnings as errors when CI=true. The repo has
        # pre-existing build warnings (acknowledged through chat-20 close).
        # Failing on them is out of scope for v1 — lint pass is Future_Tasks.
        # REACT_APP_BACKEND_URL is inlined at build time; placeholder is fine
        # because the build itself doesn't call the backend.
        working-directory: frontend
        env:
          CI: "false"
          REACT_APP_BACKEND_URL: "http://localhost:8001"
        run: yarn build

      - name: Bundle-size gate (I11 hard cap 437 kB gzipped on main.*.js)
        # gzip -c | wc -c is reproducible and doesn't depend on CRA's
        # formatted summary output (which varies kB vs KB across versions).
        # 437,000 bytes ≈ 437 kB decimal (matches the cap reported in
        # chat-19c-closing §R8.3 STOP gate 2 and Engineering Invariants I11).
        working-directory: frontend
        run: |
          MAIN=$(ls build/static/js/main.*.js 2>/dev/null | head -1)
          if [ -z "$MAIN" ]; then
            echo "::error::Main bundle not found at build/static/js/main.*.js"
            ls -la build/static/js/ || true
            exit 1
          fi
          SIZE_BYTES=$(gzip -c "$MAIN" | wc -c | tr -d ' ')
          SIZE_KB=$(python3 -c "print(round($SIZE_BYTES / 1000, 2))")
          CAP_BYTES=437000
          echo "Main bundle: $MAIN"
          echo "Gzipped size: ${SIZE_KB} kB (${SIZE_BYTES} bytes)"
          echo "Cap: 437.00 kB (${CAP_BYTES} bytes)"
          if [ "$SIZE_BYTES" -gt "$CAP_BYTES" ]; then
            echo "::error::Main bundle ${SIZE_KB} kB exceeds 437 kB hard cap (I11)"
            exit 1
          fi
          HEADROOM=$((CAP_BYTES - SIZE_BYTES))
          HEADROOM_KB=$(python3 -c "print(round($HEADROOM / 1000, 2))")
          echo "::notice::Main bundle ${SIZE_KB} kB / 437 kB cap — ${HEADROOM_KB} kB headroom"

      - name: Run Jest unit tests
        # CI=true makes Jest exit after one run (equivalent to --watchAll=false
        # in CRA's test runner). yarn test invokes `craco test` per package.json.
        working-directory: frontend
        env:
          CI: "true"
        run: yarn test --watchAll=false
```

---

### §R4 — GitHub Secrets configuration (operator-side, agent records only)

The agent CANNOT add GitHub Secrets — this is operator-side configuration. Record this section in the chat-end self-report so the operator knows to do it BEFORE the first push lands on `main`.

**Two secrets are required.** Both are test-only and must NOT match any production password.

| Secret name | Required value | Rationale |
|---|---|---|
| `CI_BOOTSTRAP_ADMIN_PASSWORD` | Any 16+ char string. Example: `CI-Bootstrap-Dev-2026!` | Used by the workflow's `BOOTSTRAP_ADMIN_PASSWORD` env var. Bootstrap creates the seeded super_admin with this. Operator chooses; value only needs to be consistent within the CI environment. |
| `CI_TEST_USER_PASSWORD` | **MUST** be `TestUser-Dev-2026!` | Hard requirement. The value is set as `TEST_USER_PASSWORD` env var; bootstrap's `seed_test_users.py` hashes it and seeds the seven test-* accounts. pytest fixtures (e.g. `tests/test_audit_remediation_patch_2.py::TEST_PASSWORD`) hardcode the literal `TestUser-Dev-2026!` for login. Any other value → all HTTP-driven login fixtures fail → most of the suite reds. |

**How to set:**
1. Navigate to `https://github.com/Rhizzo-ai/SY-Hub/settings/secrets/actions`.
2. Click **New repository secret**.
3. Add both secrets with the suggested values.
4. Confirm both appear under "Repository secrets".

If the operator does not set these before the first push, the workflow will surface a clear error from the **Validate secrets are configured** step:
```
::error::Secret CI_BOOTSTRAP_ADMIN_PASSWORD is not set. See workflow comments.
```
This is intentional — failing fast with a named error is more useful than failing deep inside bootstrap with a cryptic auth error.

**Notification settings (operator-side):**

GitHub Actions sends an email to the repo owner on workflow failure by default. To confirm Rhys's account is set up:
1. Navigate to `https://github.com/settings/notifications`.
2. Under **Actions**, confirm "Send notifications for failed workflows only" is enabled (or "Only failed runs").
3. Confirm the destination email is current.

No agent action required — record in self-report for operator confirmation.

---

### §R5 — README badge + CHANGELOG + Future_Tasks §3 RESOLVED

#### R5.1 — README.md badge

The badge surfaces CI state visibly on the repo landing page. Add it as the FIRST line of README.md, on its own line, followed by a blank line, then the existing content.

**Find the current README.md root and insert the badge.** Check both `/app/README.md` and `/app/backend/README.md`:

```bash
ls /app/README.md /app/backend/README.md 2>/dev/null
```

If a repo-root `README.md` exists, the badge goes there. If only `/app/backend/README.md` exists, add `/app/README.md` with the badge as its first content (don't move the backend README).

**Badge markdown:**

```markdown
[![CI](https://github.com/Rhizzo-ai/SY-Hub/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Rhizzo-ai/SY-Hub/actions/workflows/ci.yml)
```

If `/app/README.md` is being created fresh, the full minimal content is:

```markdown
[![CI](https://github.com/Rhizzo-ai/SY-Hub/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Rhizzo-ai/SY-Hub/actions/workflows/ci.yml)

# SY Hub

SY Homes property development operations platform.

- Backend: `backend/` — FastAPI, PostgreSQL 16, Alembic. See `backend/README.md`.
- Frontend: `frontend/` — React 19, CRA via craco, TanStack Query/Table. See `frontend/`.
- Docs: `docs/` — chat summaries, build packs, future_tasks, engineering invariants.

CI runs on every push to `main`: bootstrap smoke + pytest + frontend build + bundle-size gate + Jest. See `.github/workflows/ci.yml`.
```

If `/app/README.md` already exists, prepend the badge line + blank line to its existing content — do NOT modify the rest of the file.

#### R5.2 — CHANGELOG.md entry

Append to `/app/CHANGELOG.md` (or whichever path the project uses — discover with `ls /app/CHANGELOG.md /app/backend/CHANGELOG.md`). Use the same path as chat-14, chat-15, chat-16, chat-17, chat-18, chat-19A/B/C, chat-20.

Entry text (insert at the TOP of the file, after any header line, matching the existing CHANGELOG conventions):

```markdown
## Chat 21 — CI pipeline shipped (<DATE>)

**Anchor:** Future_Tasks §3 (open since Chat 14, 5 May 2026). RESOLVED.

- New file: `.github/workflows/ci.yml`. Two jobs (backend, frontend) running
  in parallel on every push to main + workflow_dispatch.
- Backend job: Postgres 16 service container → pgcrypto extension →
  `python -m app.bootstrap` (anchor smoke test; bootstrap runs alembic
  upgrade + tenant/RBAC/system_config seeds + seed_test_users.py via
  subprocess + verify_invariants) → start uvicorn for HTTP-driven tests
  → `python -m pytest --ignore=tests/test_c3_governance_smoke.py`.
- Frontend job: Node 20 + yarn 1.22 → `yarn install --frozen-lockfile` →
  `yarn build` → bundle-size gate (≤437 kB gzipped on main.*.js per I11) →
  `yarn test --watchAll=false` (Jest).
- Gate model: post-push (Emergent ships direct to main as auto-commits, so
  pre-merge gating is not available without a workflow change). Red CI
  surfaces via GitHub's email-on-failure + README status badge.
- Secrets required (set by operator in repo Settings):
  CI_BOOTSTRAP_ADMIN_PASSWORD, CI_TEST_USER_PASSWORD. Workflow fails fast
  with a named error if either is missing.
- README.md: status badge added as the first content line.
- Future_Tasks §3: annotated RESOLVED with commit reference.
- No source code, migrations, permissions, tests, or seeds were modified
  by this Build Pack. Infra-only.
```

#### R5.3 — Future_Tasks §3 RESOLVED annotation

Open `/app/docs/SY_Homes_Future_Tasks.md`. Find section **§3. CI pipeline (anchor: bootstrap smoke test) — P1**.

Annotate the section header as RESOLVED and add a resolution note at the TOP of the section (preserve all existing content below — it's the historical record). Format:

```markdown
## 3. CI pipeline (anchor: bootstrap smoke test) — **RESOLVED (Chat 21, <DATE>)**

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
```

(Then leave all the existing §3 content underneath as historical record. Pattern mirrors chat-15's treatment of §2 historical content.)

---

### §R6 — Local validation (agent-side, pre-push)

Before declaring done, validate that the workflow YAML at least parses and references files that exist.

```bash
# 6.1 — YAML parses
python3 -c "import yaml; yaml.safe_load(open('/app/.github/workflows/ci.yml'))" \
  && echo "YAML parse: OK"

# 6.1b — Confirm .github/workflows/ci.yml is NOT gitignored (defensive)
cd /app
git check-ignore -v .github/workflows/ci.yml \
  && { echo "STOP: .github/workflows/ci.yml is gitignored — will not be committed"; exit 1; } \
  || echo ".gitignore check: OK (not ignored)"

# 6.2 — Referenced files exist
test -f /app/backend/app/bootstrap.py && echo "bootstrap.py: present"
test -f /app/backend/scripts/seed_test_users.py && echo "seed_test_users.py: present"
test -f /app/backend/requirements.txt && echo "requirements.txt: present"
test -f /app/backend/pyproject.toml && echo "pyproject.toml: present"
test -f /app/frontend/package.json && echo "package.json: present"
test -f /app/frontend/yarn.lock && echo "yarn.lock: present"
test -f /app/backend/tests/test_c3_governance_smoke.py && echo "smoke test: present (matches --ignore flag)"

# 6.3 — Bootstrap one more time locally (sanity)
cd /app/backend && python -m app.bootstrap && echo "Local bootstrap rc=0"

# 6.4 — Run pytest locally (sanity)
cd /app/backend && python -m pytest --ignore=tests/test_c3_governance_smoke.py -q 2>&1 | tail -3

# 6.5 — Build frontend locally and re-check bundle size
cd /app/frontend && yarn build > /tmp/yarn_build.log 2>&1
tail -20 /tmp/yarn_build.log
MAIN=$(ls /app/frontend/build/static/js/main.*.js | head -1)
SIZE_BYTES=$(gzip -c "$MAIN" | wc -c | tr -d ' ')
echo "Local main bundle gzipped: $SIZE_BYTES bytes"
test "$SIZE_BYTES" -le 437000 && echo "OK — within 437 kB cap" || echo "OVER CAP"

# 6.6 — Run Jest locally
cd /app/frontend && CI=true yarn test --watchAll=false 2>&1 | tail -5
```

**Self-report:**
- YAML parses without error.
- Every referenced file is present.
- Local bootstrap rc=0, local pytest green, local yarn build clean, local bundle under cap, local Jest green.
- Record the actual values: bundle size in bytes, pytest count, Jest count.

If any step fails locally, the CI run on first push will also fail — fix locally before saving to GitHub.

---

### §R7 — First-push verification (operator-side, recorded in self-report)

The agent cannot watch the GitHub Actions UI after Save-to-GitHub. Record these steps in the self-report for the operator to perform AFTER the auto-commit lands on main:

1. Open `https://github.com/Rhizzo-ai/SY-Hub/actions` within ~2 min of Save-to-GitHub.
2. Confirm a new workflow run titled "CI" is queued or running.
3. Wait for both jobs (`backend`, `frontend`) to complete.
4. Expected outcome: both jobs green; total runtime < 10 min.
5. If red: read the failed step's logs. Common first-run failures:
   - Missing secret → "Validate secrets are configured" step fails with a clear error → add the secret per R4 → re-run via workflow_dispatch.
   - YAML parse error → GitHub Actions UI surfaces the line number → fix and push.
   - Bootstrap rc≠0 → unlikely if §R6 local validation passed; check the Postgres health-check timeout.
6. Confirm the README badge renders green at `https://github.com/Rhizzo-ai/SY-Hub` (may take ~1 min to refresh after first run).

If the operator's GitHub notification settings are correctly configured, a failure will also produce an email within ~1 min of the failed run.

---

### §R8 — Documentation, CHANGELOG, Future_Tasks (already covered in R5)

Confirm all are committed in the same auto-commit batch as the workflow file:

```bash
# R8.1 — Files staged for commit
cd /app
git status --porcelain
# Expected output (new files):
#   ?? .github/workflows/ci.yml
#   ?? README.md   (only if newly created — see R5.1)
# Expected modified:
#   M  CHANGELOG.md
#   M  docs/SY_Homes_Future_Tasks.md
#   M  README.md   (if pre-existing, modified to prepend badge)
```

---

## §4 — Acceptance criteria

All of the following must be true before declaring the chat closed.

1. `.github/workflows/ci.yml` exists at the repo root, parseable YAML, ~300 lines.
2. Workflow contains exactly two top-level jobs: `backend`, `frontend`.
3. Backend job references:
   - `postgres:16` service container.
   - `actions/checkout@v4`.
   - `actions/setup-python@v5` with Python 3.11.
   - `python -m app.bootstrap` as the anchor smoke step (which itself seeds
     test users via subprocess — no separate seed_test_users step).
   - `python -m pytest --ignore=tests/test_c3_governance_smoke.py`.
   - Both `CI_BOOTSTRAP_ADMIN_PASSWORD` and `CI_TEST_USER_PASSWORD` secrets.
   - `Validate secrets are configured` step BEFORE pip install.
   - `CREATE EXTENSION IF NOT EXISTS pgcrypto` step before bootstrap.
   - `Start backend HTTP server` step (uvicorn in background) after bootstrap
     and BEFORE pytest, with `/api/health` wait loop and log capture.
   - Job-level env block includes `POSTMARK_INBOUND_ENABLED: "true"`,
     `POSTMARK_INBOUND_SECRET: test-secret-do-not-use`, and
     `REACT_APP_BACKEND_URL: http://localhost:8001`.
   - `Dump uvicorn log on failure` step with `if: failure()`.
4. Frontend job references:
   - `actions/checkout@v4`.
   - `actions/setup-node@v4` with Node 20 + yarn cache.
   - `yarn install --frozen-lockfile`.
   - `yarn build` with `CI: "false"` env override and
     `REACT_APP_BACKEND_URL: http://localhost:8001`.
   - Bundle-size gate comparing gzipped `build/static/js/main.*.js` against
     437,000 bytes; pipe hardened with `tr -d ' '` after `wc -c`.
   - `yarn test --watchAll=false` (with `CI: "true"`).
5. Trigger: `push` to `main` + `workflow_dispatch`.
6. Concurrency group: `ci-${{ github.ref }}` with `cancel-in-progress: true`.
7. README.md has the CI badge as its first content line.
8. CHANGELOG.md (repo root) has the Chat 21 entry at the top.
9. `docs/SY_Homes_Future_Tasks.md` §3 is annotated `RESOLVED` with date and reference; original §3 content preserved as historical record.
10. §R6 local validation passes end-to-end on the agent's sandbox, including the `git check-ignore` defensive check.
11. Self-report records the operator-side §R4 + §R7 work to do (secrets + first-run watch).
12. Spot-check confirms all of the above land on `main` post-Save-to-GitHub.

---

## §5 — Self-report template (fill in at chat close)

Reproduce verbatim with each placeholder filled. Pre-filled values are sanity-check expectations — deviation is a regression to investigate.

```
### R0 — Baseline
- git pull: <clean / had updates>
- repo SHA: <recorded>
- .github/workflows/ci.yml absent at start: <yes — expected / no — STOP>
- bootstrap rc (R0.3): <0 / N>
- alembic current (R0.3): <recorded>   ← expected 0026_ai_capture_costs_perm
- pytest count (R0.4): <N>             ← expected ~790–805
- jest count (R0.4): <N>               ← expected ~118–151
- baseline main.*.js gzipped (R0.5): <N> bytes  ← expected ≤437,000
- Notes:

### R1 — Live-code shapes
- Bootstrap env-var list confirmed: <yes — matches §1 / no — list deviation>
- pyproject.toml [tool.pytest.ini_options] confirmed: <yes / no>
- frontend scripts confirmed: build=craco build, test=craco test: <yes / no>
- yarn frozen-lockfile check: <pass / fail>
- Notes:

### R2 + R3 — Workflow YAML
- File path: /app/.github/workflows/ci.yml
- Backend job present: <yes / no>
- Frontend job present: <yes / no>
- Concurrency group set: <yes / no>
- Secrets referenced: CI_BOOTSTRAP_ADMIN_PASSWORD, CI_TEST_USER_PASSWORD: <yes / no>
- Validate-secrets step BEFORE pip install: <yes / no>
- pgcrypto step present and BEFORE bootstrap: <yes / no>
- Bootstrap step uses `python -m app.bootstrap`: <yes / no>
- Backend job has Start-uvicorn step BEFORE pytest with /api/health wait: <yes / no>
- Backend job env block includes POSTMARK_INBOUND_ENABLED=true: <yes / no>
- Backend job env block includes POSTMARK_INBOUND_SECRET: <yes / no>
- Backend job env block includes REACT_APP_BACKEND_URL=http://localhost:8001: <yes / no>
- pytest invocation: `python -m pytest --ignore=tests/test_c3_governance_smoke.py`: <yes / no>
- No redundant `python scripts/seed_test_users.py` step (bootstrap handles): <verified / NOT VERIFIED>
- Bundle-size gate at 437,000 bytes (uses `tr -d ' '` on wc -c pipe): <yes / no>
- Trigger: push to main + workflow_dispatch: <yes / no>
- Notes:

### R4 — Secrets (operator-side, agent records)
- Secret names confirmed: CI_BOOTSTRAP_ADMIN_PASSWORD, CI_TEST_USER_PASSWORD: <yes / no>
- Operator action listed in self-report: <yes / no>
- Notes:

### R5 — Docs
- README.md path used: <recorded>
- README badge inserted as first content line: <yes / no>
- README.md was: <newly created / pre-existing with badge prepended>
- CHANGELOG.md path used: <recorded>
- CHANGELOG Chat 21 entry added at top: <yes / no>
- Future_Tasks §3 annotated RESOLVED: <yes / no>
- Future_Tasks original §3 content preserved as historical: <yes / no>
- Notes:

### R6 — Local validation
- YAML parses: <yes / no>
- `.gitignore` check (.github/workflows/ci.yml NOT ignored): <pass / fail>
- All referenced files present: <yes / no>
- Local bootstrap rc: <0 / N>
- Local pytest count: <N> passed, <N> failed   ← expect 0 failed
- Local yarn build: <clean / N warnings — listed>
- Local main bundle bytes: <N>                   ← expect ≤437,000
- Local jest count: <N> passed, <N> failed     ← expect 0 failed
- Notes:

### R7 — Operator-side follow-ups (record only, agent cannot do)
- Operator must add CI_BOOTSTRAP_ADMIN_PASSWORD secret: yes
  Suggested value: CI-Bootstrap-Dev-2026!  (or any 16+ char test-only string)
- Operator must add CI_TEST_USER_PASSWORD secret: yes
  REQUIRED value: TestUser-Dev-2026!  (HARD — must match the literal used
  by pytest fixtures; any other value → most HTTP tests red)
- Operator must watch first CI run after Save-to-GitHub: yes
  URL: https://github.com/Rhizzo-ai/SY-Hub/actions
  Expected runtime: < 10 min, both jobs green.
- Operator must confirm README badge renders green after first run: yes

### R8 — Files committed
- .github/workflows/ci.yml: <yes / no>
- README.md badge: <yes / no>
- CHANGELOG.md entry: <yes / no>
- docs/SY_Homes_Future_Tasks.md §3 RESOLVED: <yes / no>
- docs/SY_Hub_Chat_21_CI_Pipeline_Build_Pack.md (this Build Pack): <yes / no>
- docs/chat-summaries/chat-21-closing.md (this self-report): <yes / no>
- No source code changes (backend/app/, backend/alembic/, frontend/src/): <verified / NOT VERIFIED>
- No new tests added: <verified / NOT VERIFIED>
- No new dependencies (backend/requirements.txt, frontend/package.json): <verified / NOT VERIFIED>

### Deviations from Build Pack
- <none / list each>

### Final state
- alembic head: <unchanged from R0>
- Test count: <unchanged from R0>
- Bundle size: <unchanged from R0>
- Permissions: <unchanged from R0>      ← expected 88
- Roles: <unchanged from R0>            ← expected 10
- Future_Tasks §3: RESOLVED
- New unresolved Future_Tasks entries: <list, or "none">
```

---

## §6 — Chat-end ritual (mandatory)

Per project memory: "Mandatory chat-end spot-check on GitHub before declaring chat closed."

Before declaring close: open `https://github.com/Rhizzo-ai/SY-Hub` in the browser and eye-check that the most recent auto-commits include all of:

1. `.github/workflows/ci.yml` — present at repo root, ~280–320 lines, parseable YAML.
2. `README.md` — badge line is the first content line, references `Rhizzo-ai/SY-Hub/actions/workflows/ci.yml/badge.svg`.
3. `CHANGELOG.md` — Chat 21 entry at top under "Chat 21 — CI pipeline shipped".
4. `docs/SY_Homes_Future_Tasks.md` — §3 header annotated `RESOLVED (Chat 21, <DATE>)`, original §3 content preserved as historical record below.
5. `docs/SY_Hub_Chat_21_CI_Pipeline_Build_Pack.md` — this Build Pack file, mirroring the chat-14/15/16 pattern of committing the spec alongside the implementation.
6. `docs/chat-summaries/chat-21-closing.md` — Emergent's self-report against the §5 template, including R7 operator follow-up reminders.

If any are missing → fix via GitHub web UI commit + re-spot-check before closing the chat.

Also confirm the FIRST CI run starts within ~2 min of Save-to-GitHub. The operator monitors the result; the agent's responsibility ends at spot-check.

---

## §7 — Stop-gates

STOP and self-report at any of these points; do NOT proceed:

- **R0.2:** `.github/workflows/ci.yml` already exists on `main`.
- **R0.3:** Bootstrap rc ≠ 0.
- **R0.5:** Baseline main bundle already > 437,000 bytes gzipped.
- **R1:** Bootstrap env-var contract, pyproject.toml, or yarn frozen-lockfile check diverges from §1 expectations.
- **R6.1:** YAML does not parse.
- **R6.1b:** `.github/workflows/ci.yml` is matched by `.gitignore` (would not be committed).
- **R6.3:** Local bootstrap rc ≠ 0 after the workflow is written.
- **R6.5:** Local bundle > 437,000 bytes after a clean build.
- **R6.6:** Local Jest non-zero exit.
- Scope creep: any temptation to add Playwright, lint, source code edits, new tests, new dependencies, new migrations, new permissions, new seeds — STOP and log to Future_Tasks; do NOT bundle.

---

_End of Build Pack v1._
