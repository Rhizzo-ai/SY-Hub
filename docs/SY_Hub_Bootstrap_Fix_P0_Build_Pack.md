# SY Hub — Bootstrap Fix (P0 RECURRING) — Build Pack v2

> **Scope:** One-shot fix for the recurring fresh-DB / snapshot-restore cold-start failure that's hit 5/5 times during 2.3 work. Standalone session, own branch (`bootstrap-fix-p0`), straight PR to `main`. **Blocks Prompt 2.4 (Budgets).** No product surface change — this is robustness + observability.
>
> **Inherits from:** `/app/docs/SY_Hub_2.3_Checkpoint3_Handoff.md` §R0 (existing manual recovery procedure — to be made obsolete by this fix).
>
> **Quality bar:** state-of-the-art. Mutex against concurrent bootstraps; per-step timing; actionable error messages; unit-tested orchestrator; verify-invariants that catches drift, not just absence.

---

## §0 — Context

State at fork:

- Foundation track sealed. Track 2 / Prompt 2.3 (Appraisal Governance) merged to `main` end-to-end (C1 + C2 + C3). Issue #14 closed.
- alembic head: **`0022_appraisal_governance`** (at time of writing — orchestrator is version-agnostic; do not hardcode).
- Backend: **581/581 tests** passing. Frontend E2E `testing_agent_v3_fork` iter_10 PASS.
- Frontend new dep: `framer-motion@12.38.0`.
- Permissions: 81. Roles: 10. (Patch #3 removed orphans.)

The platform's named failure mode under fresh-DB or pod-restart conditions is a recurring chicken-and-egg between migrations and `seed_rbac.py`. The §R0 manual recovery (partial-seed → upgrade → re-seed) works every time but burns 15–30 minutes per occurrence. P0 threshold reached after the 5th recurrence (during the C3 Emergent fork). Project instructions require this to land before Prompt 2.4 starts.

---

## §1 — Diagnosis (the answer — do not re-derive)

The chicken-and-egg is specific:

1. `seed_rbac.py`'s `PERMISSION_CATALOGUE` references two permissions added in Prompt 2.2:
   - `appraisals.submit` (action `submit`)
   - `appraisals.view_financials` (action `view_financials`)
2. These map to values on the Postgres `permission_action` enum.
3. **Migration 0020** is what adds those values to the enum.
4. Therefore: `seed_rbac.py` only succeeds against a DB that has been migrated **to or past 0020**.

The existing §R0 recovery procedure proves the diagnosis — it monkey-patches `PERMISSION_CATALOGUE` to remove those two permissions, runs `seed.py` and a stripped `seed_rbac.py` against the partially-migrated DB, runs `alembic upgrade head`, then re-runs `seed_rbac.py` clean.

**The "wiped DB" state on Emergent is snapshot-restore, not zero-state.** The §R0 ordering (seed-with-patch first, upgrade second) reveals that the DB volume is restored at an intermediate alembic revision (schema exists, but not at head). On a true zero-state DB, `alembic upgrade head` would be needed first to create any tables at all.

The bug is **not** in either seed file. Both `seed.py` and `seed_rbac.py` are clean and idempotent.

The bug is in `/root/.emergent/on-restart.sh`. The three live failure-mode candidates:

- **(a) Seeds before `alembic upgrade head`** — most likely. seed_rbac trips on missing enum values, fails, backend boots half-seeded.
- **(b) No `set -e` / silent partial failure** — script continues past a failed seed, supervisor brings backend up against incomplete RBAC.
- **(c) Postgres readiness race** — alembic starts before pg accepts connections, fails, downstream seeds run against partial schema.

Confirm which is live in R1; the orchestrator closes all three regardless, AND handles both snapshot-restore and true-zero-state DB cases via consistent `upgrade-first → seed` ordering.

---

## §2 — Acceptance criteria

The fix is correct iff all of the following hold:

1. **Cold-start works without operator intervention.** Drop schema → run bootstrap entry-point → `pytest --tb=no` returns the current head test count without manual recovery.
2. **Idempotent.** Running the bootstrap entry-point twice consecutively is safe — the second run logs all "present" / "no-op" and exits 0. Diff between run 1 and run 2 final summary is only `elapsed` numbers.
3. **Concurrency-safe.** Two simultaneous invocations do not race. Second invocation either waits for the first to complete (preferred) or exits cleanly with a clear "already in progress" message. Implemented via Postgres advisory lock keyed on `hashtext('sy_hub_bootstrap')`.
4. **Fail-loud.** Any failure during bootstrap exits non-zero. `on-restart.sh` inherits with `set -euo pipefail` so backend does not start if bootstrap failed. Every failure log line names the likely cause and points at remediation.
5. **Per-step timing.** Each step logs `[bootstrap] step=<name> result=<ok|fail> elapsed=<s>s` in k=v form. Final summary aggregates total time + per-step breakdown.
6. **Verify-invariants step.** End of bootstrap asserts:
   - alembic current == alembic head (version-agnostic — read both, compare)
   - `permissions` row count == `len(PERMISSION_CATALOGUE)` (compute, don't hardcode)
   - `roles` row count == `len(ROLE_CATALOGUE)`
   - super_admin user exists for `BOOTSTRAP_ADMIN_EMAIL`
   - That user has an `Active` `user_roles` row pointing at the `super_admin` role
   - **Every permission code referenced in `ROLE_PERMISSIONS` resolves to a row in the `permissions` table** (catches typos / drift in role-permission mapping that `_seed_role_permissions` currently swallows as a warning)
   Failure of any assertion exits non-zero with a clear log line + likely cause.
7. **Unit-tested.** `tests/test_bootstrap.py` adds 6+ targeted tests (see R5 below) covering wait_for_postgres timeout, detect_db_state branches, verify_invariants happy + each failure mode, plus one end-to-end integration test. Backend test count moves from 581 → 587+ green.
8. **§R0 dance is obsolete.** The C1/C2/C3 handoff §R0 partial-seed → upgrade → re-seed procedure is no longer required. CHANGELOG documents the deletion. Handoff docs themselves are not edited (history is immutable).
9. **Operational docstring.** `bootstrap.py` module docstring is the canonical operational doc — includes a "when this fails" troubleshooting key for each failure log line. Ops-readable; ground-truth, not aspirational.
10. **Docs updated.** `/app/docs/SY_Homes_Future_Tasks.md` P0 entry annotated as resolved with PR reference. CHANGELOG entry under "Bootstrap & ops".

---

## §3 — R0: Establish baseline before changing anything

```bash
# Read current state — DO NOT modify yet
cat /root/.emergent/on-restart.sh
ls -la /app/backend/app/bootstrap.py 2>/dev/null   # expect: not present
ls /app/backend/scripts/ 2>/dev/null               # check seed_test_users.py exists
ls /app/backend/tests/test_bootstrap.py 2>/dev/null # expect: not present

# Confirm baseline is healthy before fix work begins (version-agnostic)
cd /app/backend && set -a && source .env && set +a
CURRENT=$(alembic current 2>&1 | tail -1)
HEAD=$(alembic heads 2>&1 | tail -1)
echo "current: $CURRENT"
echo "head:    $HEAD"
# expect: current == head (both reference same revision)

pytest --tb=no 2>&1 | grep -E "^[0-9]+ passed"  # expect: 581 passed
```

If baseline is broken (alembic current != head, or tests not passing), STOP and run the §R0 procedure from `/app/docs/SY_Hub_2.3_Checkpoint3_Handoff.md` first to establish the green baseline. Do not attempt the fix on a broken baseline.

---

## §4 — Build plan (R1–R8)

### R1 — Read on-restart.sh, identify the live failure mode

Compare current contents against the three hypotheses in §1. Record verbatim original contents — needed for the PR description and the CHANGELOG entry.

If R1 reveals the actual failure mode is **none** of (a)/(b)/(c), STOP and self-report before proceeding to R2. The fix shape may need to change.

### R2 — Create `/app/backend/app/bootstrap.py`

Single entry point. Exposes `python -m app.bootstrap`.

#### Module docstring (operational, not just descriptive)

The module docstring at the top of the file is the canonical operational doc. Structure:

```
"""SY Hub bootstrap orchestrator.

Single source of truth for cold-start sequencing. Runs as `python -m app.bootstrap`
from /app/backend with .env sourced. Holds a pg advisory lock for the duration to
prevent concurrent bootstraps. Fails loud and exits non-zero on any error.

Sequence:
  0. Env-var precheck      (BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD)
  1. Wait for Postgres     (BOOTSTRAP_PG_TIMEOUT_SECONDS, default 60)
  2. Acquire advisory lock (key=hashtext('sy_hub_bootstrap'))
  3. Detect DB state       (logs current alembic revision)
  4. alembic upgrade head
  5. seed.py               (tenant + entities)
  6. seed_rbac.py          (permissions + roles + role_perms + super_admin)
  7. seed_test_users       (if scripts/seed_test_users.py present)
  8. Verify invariants
  9. Release advisory lock + summary

When this fails — troubleshooting:
  - "BOOTSTRAP_ADMIN_EMAIL not set"
      → Set in /app/backend/.env. See the seed_rbac _seed_bootstrap_admin docstring.
  - "Could not connect to Postgres after Ns"
      → Check Postgres is running; verify DATABASE_URL in .env.
      → Increase BOOTSTRAP_PG_TIMEOUT_SECONDS if Postgres is genuinely slow to start.
  - "Could not acquire advisory lock"
      → Another bootstrap is in progress, or a previous run died holding the lock.
      → Wait, or check: SELECT pid, locktype, objid FROM pg_locks WHERE locktype='advisory';
  - "alembic upgrade failed"
      → Read the alembic stderr captured in the log. Likely a migration error.
      → Run alembic current and alembic heads to inspect state.
  - "Verify failed: expected N permissions, found M"
      → A permission_action enum value is likely missing. Run alembic current vs heads.
      → Check the most recent migration that touched permission_action.
  - "Verify failed: super_admin user_role not active"
      → BOOTSTRAP_ADMIN_EMAIL was changed without re-bootstrapping, or user was
        manually deactivated. Re-run bootstrap, or restore via SQL.
  - "Verify failed: ROLE_PERMISSIONS references unknown permission code <code>"
      → Typo in seed_rbac.ROLE_PERMISSIONS, or a permission was removed without
        updating role mappings. Fix the catalogue, re-run.

Exit codes:
  0   ok
  1   precheck failure (env vars)
  2   postgres unreachable
  3   advisory lock unavailable
  4   alembic upgrade failed
  5   seed failed
  6   verify failed
  7   unexpected
"""
```

#### Behavioural requirements

- **Step 0: env-var precheck.** Verify `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` are set before doing anything else. Exit 1 with a clear message if missing.
- **Step 1: `wait_for_postgres`.** Poll the DB connection (raw `psycopg`/`asyncpg` connect, or SQLAlchemy `engine.connect()` with `try/except OperationalError`) for up to `BOOTSTRAP_PG_TIMEOUT_SECONDS` (default 60, max 300) at 1-second intervals. Log progress every 5 seconds. Exit 2 on timeout.
- **Step 2: Acquire advisory lock.** `SELECT pg_try_advisory_lock(hashtext('sy_hub_bootstrap'))`. If it returns false, log + exit 3. Hold the lock until Step 9. Use a separate, non-pooled connection for this — must persist across sub-steps. Use `try/finally` to guarantee release on any exit path.
- **Step 3: `detect_db_state`.** Query `alembic_version` if it exists; report current revision (or `unstamped` if the table is missing). **Pure logging — does not branch behaviour.** Logged as `[bootstrap] step=detect_state result=ok current=<revision> head=<revision> elapsed=<s>s`.
- **Step 4: `alembic_upgrade_head`.** Use `alembic.config.main(["upgrade", "head"])` (not shell out — keeps stderr in the same process for capture). Exit 4 on alembic failure with the captured stderr in the log.
- **Step 5: `seed_tenant_and_entities`.** Call `app.seed.seed()`. Already idempotent. Exit 5 on failure.
- **Step 6: `seed_rbac`.** Call `app.seed_rbac.seed_rbac()`. Already idempotent. Now safe — alembic is at head, all enum values exist. Exit 5 on failure.
- **Step 7: `seed_test_users`.** Run `scripts/seed_test_users.py` if present (subprocess or import + call); log and skip if not. Failure here exits 5.
- **Step 8: `verify_invariants`.** Per §2.6 above. Each assertion logs its result individually so a failure is greppable. Exit 6 on any failure.
- **Step 9: Release advisory lock + summary.** `SELECT pg_advisory_unlock(hashtext('sy_hub_bootstrap'))`. Final log line:
  `[bootstrap] OK alembic=<rev> perms=<n> roles=<n> super_admin=<email> total_elapsed=<s>s`
  preceded by per-step timings.

#### Logging conventions

- Use `logging` (not `print`).
- Every step logs at minimum `[bootstrap] step=<name> result=<ok|fail> elapsed=<s>.<ms>s`.
- All log lines prefixed `[bootstrap]` for grep-ability.
- Format: `[bootstrap] step=<name> key=value key=value ...` (k=v structured-ish).
- Failure log lines include `cause=<short-key>` referencing the docstring troubleshooting section.

#### Implementation notes

- `if __name__ == "__main__": sys.exit(main())` so exit codes propagate to the shell.
- `main()` returns an int (the exit code).
- All step functions take a single `BootstrapContext` dataclass holding the lock-connection, logger, and timings dict. No global state.

### R3 — Replace `/root/.emergent/on-restart.sh` body

Target shape:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd /app/backend
set -a
source .env
set +a

python -m app.bootstrap

sudo supervisorctl restart backend
```

If the current `on-restart.sh` does additional work beyond migration/seed/restart (e.g. frontend builds, supervisor wiring for the frontend service, env-file copying), **preserve those bits** — but only AFTER the `python -m app.bootstrap` call so backend boot is gated on bootstrap success. If unsure whether to preserve a step, raise it in self-report rather than delete it.

### R4 — Tighten `seed_rbac.py` env-var error message

Current behaviour at `_seed_bootstrap_admin`:

```python
if not email or not password:
    raise RuntimeError("Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD ...")
```

Keep the runtime error. Adjust the message to point at the bootstrap orchestrator as the authoritative entry-point (e.g. "Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in /app/backend/.env. The bootstrap orchestrator (app.bootstrap) prechecks these before connecting to Postgres."). The bootstrap.py Step 0 precheck (R2) makes this branch unreachable in the normal cold-start path, but the seed function may still be called directly from tests or scripts, so the safety net stays.

No other changes to `seed.py` or `seed_rbac.py` unless R1 reveals a defect.

### R5 — Add `tests/test_bootstrap.py`

Minimum coverage (~6–8 tests, more if naturally arises):

1. **`test_env_precheck_missing_email`** — unset `BOOTSTRAP_ADMIN_EMAIL`, call `main()`, assert exit code 1 + log line names the missing env var.
2. **`test_wait_for_postgres_timeout`** — point `DATABASE_URL` at a closed port, set `BOOTSTRAP_PG_TIMEOUT_SECONDS=2`, assert exit code 2 within ~3 seconds.
3. **`test_detect_db_state_unstamped`** — drop `alembic_version` table, call detect_db_state, assert returns `"unstamped"` without raising.
4. **`test_detect_db_state_at_head`** — on the standard test DB, assert returns the head revision.
5. **`test_verify_invariants_happy_path`** — on a healthy seeded DB, assert passes.
6. **`test_verify_invariants_missing_super_admin`** — delete the super_admin user_role, assert verify fails with the expected cause key.
7. **`test_verify_invariants_perm_count_mismatch`** — delete one permission row, assert verify fails with `cause=perm_count_mismatch`.
8. **`test_verify_invariants_role_perm_unknown_code`** — temporarily monkey-patch `ROLE_PERMISSIONS` to include a non-existent code, assert verify fails with `cause=role_perm_unknown_code`. (Confirms the new check from §2.6.)
9. **`test_concurrent_bootstrap_lock`** (optional but valuable) — open the advisory lock from a second connection, call `main()`, assert exit code 3 within timeout.
10. **`test_end_to_end_cold_start`** (integration) — drop schema (test DB only), run `main()`, assert exit 0, assert all invariants, assert pytest can run a smoke test against the resulting DB.

Each test cleans up after itself. Use existing pytest fixtures + DB setup conventions. Place at `/app/backend/tests/test_bootstrap.py`.

Test count target: **581 → 587+** (depending on how the integration test counts). State the final number in self-report.

### R6 — CHANGELOG + Future_Tasks

**`/app/CHANGELOG.md` — append under an unreleased "Bootstrap & ops" heading:**

> **Bootstrap orchestrator (P0 RECURRING fix).** New `app/bootstrap.py` owns cold-start sequencing: env-var precheck → wait for Postgres → acquire advisory lock → detect state → `alembic upgrade head` → `seed.py` → `seed_rbac.py` → `seed_test_users.py` (if present) → verify invariants → release lock + summary. Per-step timing, structured k=v logs, actionable failure causes keyed to the module docstring's troubleshooting section. Concurrency-safe via Postgres advisory lock. `/root/.emergent/on-restart.sh` shrinks to a single `python -m app.bootstrap` call with `set -euo pipefail`. New env var `BOOTSTRAP_PG_TIMEOUT_SECONDS` (default 60). The §R0 partial-seed → upgrade → re-seed manual recovery procedure documented in C1/C2/C3 handoffs is **obsolete** — fresh-DB and snapshot-restore boots now succeed unattended. Resolves 5/5 recurrence count from 2.3 work. Backend tests: 581 → 587+ (orchestrator coverage).

**`/app/docs/SY_Homes_Future_Tasks.md` — annotate the P0 RECURRING entry:**

> **RESOLVED — `bootstrap-fix-p0` PR #&lt;n&gt;, &lt;date&gt;.** Bootstrap orchestrator landed; §R0 manual recovery dance no longer needed. Concurrency-safe; verify-invariants now catches role-permission drift.

Leave the original P0 entry in place above the annotation as historical context.

### R7 — Verification protocol

```bash
# 1. Idempotence — run twice on the healthy baseline DB
cd /app/backend && python -m app.bootstrap
cd /app/backend && python -m app.bootstrap   # second run logs all "present" / no-op

# 2. Backend tests — full suite
pytest --tb=no 2>&1 | grep -E "^[0-9]+ passed"  # expect: 587+ passed

# 3. Concurrent-bootstrap test — manually
# In one shell:
psql "$DATABASE_URL" -c "SELECT pg_advisory_lock(hashtext('sy_hub_bootstrap'));"
# Keep it open. In another shell:
cd /app/backend && python -m app.bootstrap
# expect: exit 3, log line cites lock unavailable
# Release in first shell: \q

# 4. Cold-start simulation — THE acceptance test
#    Use whatever fresh-DB mechanism Emergent's sandbox supports without
#    risking the live preview. Options in order of preference:
#    (a) Spin an ephemeral DB on the same Postgres instance, point DATABASE_URL
#        at it, run bootstrap, run pytest, restore DATABASE_URL.
#    (b) DROP SCHEMA public CASCADE; CREATE SCHEMA public; on the dev DB,
#        only if safe in the sandbox.
psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
python -m app.bootstrap   # expect: full sequence run + "OK" final log + exit 0
pytest --tb=no 2>&1 | grep -E "^[0-9]+ passed"  # expect: 587+ passed
```

If destructive verification (#4) is unsafe in the sandbox, simulate via an ephemeral DB and document the choice in self-report. The acceptance bar is "bootstrap takes a from-zero DB to a green test run end-to-end in one invocation."

### R8 — PR

Branch: **`bootstrap-fix-p0`**.
PR title: **"Bootstrap orchestrator (P0 RECURRING fix)"**.
PR body must include:
- The §1 diagnosis verbatim.
- The before/after diff of `/root/.emergent/on-restart.sh`.
- The full bootstrap.py log from the cold-start simulation (R7 step 4).
- Final pytest line from the same.
- Idempotence run-1 vs run-2 final log lines (showing the diff is just timings).
- Concurrent-bootstrap test output (R7 step 3).

PR target: `main`. Squash merge.

---

## §5 — Self-report format (paste at end)

Reply with these sections, in order:

1. **`on-restart.sh` — before:** verbatim contents.
2. **Live failure mode confirmed:** which of (a)/(b)/(c) was the live bug, or "all three" / "none — see analysis".
3. **`bootstrap.py` — created:** absolute path, line count, two-line summary of the nine-step flow.
4. **`tests/test_bootstrap.py` — created:** absolute path, test count, list of test names.
5. **`on-restart.sh` — after:** verbatim new contents.
6. **Verification log:**
   - Idempotence run 1 — final summary line + exit code.
   - Idempotence run 2 — final summary line + diff vs run 1 (should be only `elapsed` numbers).
   - Concurrent-lock test — output + exit code.
   - Cold-start simulation — full bootstrap log + final pytest line + exit code.
7. **Test count:** before (581) → after (number).
8. **CHANGELOG entry** — verbatim addition.
9. **Future_Tasks annotation** — verbatim text.
10. **PR URL + branch name.**
11. **Anything unexpected** — list, or "none".

If R1 surfaces a defect in `seed.py` or `seed_rbac.py` itself, STOP before R2 and self-report the finding for review before changing them.

---

## §6 — Out of scope

- New permissions or roles.
- Migration content changes.
- Backend test infrastructure beyond the new `test_bootstrap.py` (existing tests have their own DB lifecycle and are unaffected).
- Frontend changes.
- A `/api/healthz` or `/api/readyz` endpoint that runs verify_invariants — a real follow-up; logged for Future_Tasks but not in this PR.
- JSON-structured log output / log aggregator integration.
- Extra config env vars beyond `BOOTSTRAP_PG_TIMEOUT_SECONDS` (e.g. `BOOTSTRAP_VERIFY_ONLY`, `BOOTSTRAP_SKIP_SEEDS`) — premature.
- Snapshot mechanics on Emergent's side — we work with what they give us.
- Editing the historical §R0 sections in C1/C2/C3 handoff docs (history is immutable; obsolescence noted in CHANGELOG + Future_Tasks).
- The C3 follow-up `state=null` issue on `GET /appraisals/{id}` — separate ticket; do not bundle.
- "Optimising" bootstrap for speed. Speed is not a goal. **Per-step timing observability is mandatory** (§2.5). Sub-30s on a healthy DB is fine; longer is fine on snapshot-restore.

---

## §7 — Files in scope vs explicitly NOT in scope

**Touch:**
- `/app/backend/app/bootstrap.py` — **NEW** (orchestrator + module operational docstring)
- `/app/backend/tests/test_bootstrap.py` — **NEW** (6+ targeted tests)
- `/root/.emergent/on-restart.sh` — **REPLACE BODY** (preserve any unrelated steps after the bootstrap call)
- `/app/CHANGELOG.md` — **APPEND**
- `/app/docs/SY_Homes_Future_Tasks.md` — **ANNOTATE** the P0 RECURRING entry as resolved

**Tighten only (small message edit):**
- `/app/backend/app/seed_rbac.py` — error-message wording in `_seed_bootstrap_admin` per R4

**Do NOT touch (unless R1 reveals an actual defect — STOP and self-report first):**
- `/app/backend/app/seed.py`
- `/app/backend/app/seed_rbac.py` (beyond the R4 message tweak)
- Any alembic migration file
- Any model file
- Any existing test file
- Any frontend file

---

## §8 — Estimated context budget

Small fix in scope, slightly larger in care. Most of the work is reading two short files, writing one new Python file (~300–400 lines including the operational docstring), one test file (~150–250 lines), replacing one short shell file, and capturing verification logs. ~25–40k context tokens including the cold-start simulation logs and the concurrent-lock test output.

---

_End of Build Pack v2._
