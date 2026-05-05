# Chat 14 — Closing Summary

**Session:** Chat 14 — Bootstrap Fix P0 (RECURRING)
**Date:** 5 May 2026
**Outcome:** ✅ Complete. Bootstrap orchestrator landed. PR `bootstrap-fix-p0` → `main`. Two new P1s registered (FK cascade migration + CI pipeline). Ready for Chat 15.

---

## 1. What got done

### Primary deliverable: bootstrap orchestrator (PR `bootstrap-fix-p0`)

- **`/app/backend/app/bootstrap.py`** (NEW, ~1,130 lines incl. operational docstring + sandbox provisioning notes). Single entry-point at `python -m app.bootstrap`. Nine-step flow: env-var precheck → wait_for_postgres → acquire pg advisory lock → detect_db_state → alembic upgrade head → seed → seed_rbac → seed_test_users (if present) → verify_invariants → release lock + summary.
- **`/app/backend/tests/test_bootstrap.py`** (NEW, ~510 lines, 15 tests). Coverage: env precheck, Postgres timeout, detect_state branches, verify_invariants happy + 5 failure modes (`super_admin_user_missing`, `perm_count_mismatch`, `role_count_mismatch`, `role_perm_unknown_code`, `alembic_drift`), concurrent-lock test, end-to-end integration. Test count moved **581 → 596**.
- **`/app/backend/app/seed_rbac.py`** — error-message tightening in `_seed_bootstrap_admin` per Build Pack §R4. No behavioural change.
- **`/etc/supervisor/conf.d/supervisord.conf`** — `[program:backend]` now has `autostart=false` AND `autorestart=false` with inline contract comment. Frontend NOT gated (CRA decoupled, degrades gracefully when API down).
- **`/app/scripts/supervisord_backend.conf.template`** (NEW) — checked-in template for the `[program:backend]` block. Source of truth for the gating contract.
- **`/app/scripts/on-restart.sh`** (NEW canonical at `/app/scripts/`, mirrored to live `/root/.emergent/on-restart.sh`). Idempotently applies the supervisor template at the top of the hook (self-healing on container rebuild), then runs `python -m app.bootstrap`, then `sudo supervisorctl start backend` only on `rc=0`. Non-zero rc logs `[on-restart] skipping supervisorctl start backend (bootstrap rc=N)` and propagates the rc.
- **`/app/scripts/README.md`** (NEW) — install instructions for fresh forks; "Supervisor backend gating" section; explains the readonly-banner deviation; documents the self-healing template-apply pattern.
- **`/app/docs/SY_Hub_Bootstrap_Fix_P0_Build_Pack.md`** (Build Pack v2 verbatim, 378 lines) — committed alongside code per the same `/app/docs/` pattern as the C2/C3 Build Packs.
- **`/app/CHANGELOG.md`** — appended under "Bootstrap & ops" heading.
- **`/app/docs/SY_Homes_Future_Tasks.md`** — P0 entry annotated as resolved with PR reference. Two new P1 entries added (see §3 below).
- **`/app/memory/PRD.md`** — bootstrap-fix-p0 implementation status section appended (Emergent's working memory artefact).

### Acceptance criteria — all met

| Build Pack §2 | Status |
|---|---|
| 1. Cold-start works without operator intervention | ✅ §R7.4 |
| 2. Idempotent (run-1 vs run-2 diff = elapsed only) | ✅ §R7.1 (3× consecutive: 1.42 / 1.41 / 1.41 s) |
| 3. Concurrency-safe (pg advisory lock) | ✅ §R7.2 (one rc=0, one rc=3 `cause=lock_unavailable`) |
| 4. Fail-loud (non-zero exit + named cause) | ✅ §R7.3 (5 failure causes exercised) |
| 5. Per-step timing in k=v logs | ✅ |
| 6. Verify-invariants (5 checks + role-perm drift) | ✅ |
| 7. Unit-tested (581 → 587+ floor) | ✅ Achieved 596 |
| 8. §R0 dance is obsolete | ✅ CHANGELOG documents |
| 9. Operational docstring with troubleshooting key | ✅ |
| 10. Docs updated (CHANGELOG + Future_Tasks) | ✅ |

### Verification additions (beyond Build Pack v2)

| Check | Result |
|---|---|
| **§R7.5 snapshot-restore simulation** — DB built to 0019, enum lacks `submit`/`view_financials`, run bootstrap | ✅ rc=0; alembic advances to head; both enum values present after. The actual production failure mode is now provably self-healing. |
| **§R7.7 supervisor gating** — failure path: postgres stopped → bootstrap rc=2 → backend STOPPED, hook exit=2 | ✅ |
| **§R7.7 supervisor gating** — happy path: cold start → bootstrap rc=0 → backend RUNNING, `/api/health` 200 | ✅ |

---

## 2. Decisions locked this session

These are now part of the SY-Hub canonical record. Don't re-litigate.

1. **Failure mode (d) — fresh-fork-with-no-orchestrator — added to the canonical list.** Beyond the original (a)/(b)/(c) in Build Pack §1, fresh Emergent forks come up as bare FastAPI+Mongo templates with no Postgres, no `on-restart.sh`, no orchestrator. The bootstrap orchestrator now handles this case as a first-class scenario, not an exception.
2. **Postgres 16 (PGDG) is pinned for SY-Hub.** Debian 12 / bookworm default is PG15; we explicitly install PG16 via the PGDG apt repo. Documented in `bootstrap.py`'s "Sandbox provisioning notes" section. Future forks must match.
3. **`pgcrypto` extension is required before `alembic upgrade`.** Migrations 0011/0012/0015/0019/0022 use `gen_random_uuid()` server-defaults. The provisioning runbook creates the extension as a mandatory step.
4. **Supervisor `[program:backend]` requires BOTH `autostart=false` AND `autorestart=false`.** `autorestart` matters too — without it, supervisor cycles backend back up after the first stop.
5. **Supervisor wiring is self-healing via the template-apply pattern in `on-restart.sh`.** README-documented manual edits are too fragile (we proved this within the same session — container rebuild stripped Postgres + supervisor config). The template at `/app/scripts/supervisord_backend.conf.template` is the source of truth; `on-restart.sh` re-applies it idempotently at the top of every hook fire.
6. **The §R0 manual recovery dance from C1/C2/C3 handoffs is obsolete.** Documented as such in CHANGELOG. Historical handoff docs are not edited (history is immutable); CHANGELOG is the canonical "this is no longer required" record.
7. **CI pipeline deferred to a discrete P1, not bundled into bootstrap-fix-p0.** Single-line CI smoke test was tempting but under-scopes the real work (runner choice, secrets, test-DB strategy, merge-gating policy). Logged as Future_Tasks §3.
8. **Frontend service is NOT gated on bootstrap success.** CRA dev server is decoupled from the backend at startup and degrades gracefully when API is down. Confirmed in this session.

---

## 3. Open P1 tech debt registered (NOT FIXED — gates Prompt 2.4)

Both items must be resolved before Prompt 2.4 (Budgets) starts. Logged in `/app/docs/SY_Homes_Future_Tasks.md`.

### §2 — `appraisal_scenarios` FK ON DELETE RESTRICT

**Defect:** `appraisal_scenarios.scenario_appraisal_id_fkey` is `ON DELETE RESTRICT` (introduced in migration 0022). Blocks the cascade from `DELETE FROM projects → appraisals → scenarios` in test teardown — currently mitigated by `--ignore=tests/test_c3_governance_smoke.py` in the test invocation.

**Sub-issues:**
- **2a:** `tests/test_c3_governance_smoke.py` has no teardown (test infrastructure bug). Smoke-probe test that should run post-deploy, not as part of the unit regression suite.
- **2b:** FK should be `ON DELETE CASCADE`, not `RESTRICT` (data-model bug). Migration 0023 needed: `0023_appraisal_scenarios_fk_cascade`.

**Resolution gate:** Both fixed and `--ignore` flag dropped from pytest invocation; full suite green at whatever count emerges.

### §3 — CI pipeline (anchor: bootstrap smoke test)

**Need:** Catch the cold-start failure mode in CI before it hits a human. Five recurrences during 2.3 prove the cost of not having it.

**Decisions to make:**
- Runner choice (GitHub Actions vs. self-hosted)
- Test-DB strategy in CI (ephemeral container? testcontainers-python?)
- Secrets handling for `BOOTSTRAP_ADMIN_*`
- Whether CI gates merges to main (recommended: yes)
- What other tests run alongside bootstrap smoke (likely: full pytest suite once §2 is resolved)

**Sizing:** Discrete fix, not a one-line addition. Likely a half-session unit of work in its own right.

**Recommended sequencing:** After §2 lands, before Prompt 2.4 OR alongside Prompt 2.4 (Budgets is high-stakes financial code; CI insurance pays off there).

---

## 4. Process learnings — for the record

1. **Emergent forks do NOT inherit sandbox state.** Postgres pods, supervisor wiring, on-restart.sh scripts — none of this is in git, none of it copies across forks. The first-time-setup is real. The bootstrap orchestrator's runbook docstring is now the canonical fresh-fork bootstrap doc.
2. **The container can be rebuilt mid-session.** Happened in this session — Postgres binaries, user, data dir all gone between previous agent's work and final supervisor template work. The orchestrator's runbook recovered it. This is a confirming demo of the fix's value, not a regression.
3. **Supervisor's exit-code semantics for `on-restart.sh` are non-obvious and need to be verified explicitly, not assumed.** Initial agent report quietly mentioned that supervisor "starts backend regardless" of the script's rc — a P0 hole framed as an FYI. Catch was made by audit, not by initial review. Future bootstrap-equivalent fixes need supervisor-gating verification baked into acceptance criteria from the start.
4. **README-documented manual edits are too weak.** The supervisor edit was initially landed only in the live config + README ("do this thing"). Self-healing template-apply ("this happens automatically") is structurally stronger. Pattern: anything that needs to be re-applied across forks should be a checked-in artefact applied by `on-restart.sh`, not a README instruction.
5. **STOP gates work.** Build Pack v2's R0 baseline-check STOP gate caught the missing-Postgres state at the start of the session. Without it, the agent would have charged ahead and either (a) failed loudly later or (b) silently invented credentials. STOP gates pay for themselves.
6. **Build Pack v1 → v2 audit was worth it.** Ten improvements landed via the pre-paste audit (advisory lock, per-step timing, role-perm drift check, etc.) — all of which would have been gaps in production. The "audit before paste" discipline should be a permanent step in the workflow.

---

## 5. Project instructions v1.5 — patch notes (for Rhys to action directly)

These changes need to land in the project instructions document. Rhys edits this directly per the established pattern.

**Version bump:** v1.4 → v1.5

**Changes to apply:**

### "Current state (as of project instructions creation)" section

Replace the `Track 2 (Commercial Engine) in progress` paragraph with:

> **Track 2 (Commercial Engine) in progress.** Prompts 2.1, 2.2, 2.3 shipped. 2.3 Appraisal Governance complete end-to-end (C1 retrofit + C2 backend + C3 frontend/E2E). Merged to main. **Bootstrap orchestrator landed (PR `bootstrap-fix-p0`).** 596 backend tests passing (with `--ignore=tests/test_c3_governance_smoke.py` workaround pending P1 §2 resolution). testing_agent_v3_fork iter_10 PASS. framer-motion@12.38.0 added as new frontend dep. **Next: P1 §2 (appraisal_scenarios FK cascade + smoke-test teardown), then Prompt 2.4 (Budgets).**

Update the auth/RBAC line:
> Multi-tenant-ready but single-tenant-live, auth complete with Argon2id + TOTP MFA + JWT, 10 seeded roles, **83 permissions** (was 81; two added during 2.2 — `appraisals.submit` + `appraisals.view_financials`).

### NEW section: "Fresh-fork provisioning"

Insert after "Where the current build state lives". Suggested wording:

> **Fresh-fork provisioning.** Emergent forks come up as bare FastAPI+Mongo templates with the SY-Hub repo layered on top. Postgres, supervisor wiring for Postgres, and the `on-restart.sh` orchestrator hook are NOT in the repo and do NOT carry across forks — they live in the live container's filesystem only. On a fresh fork, the first agent action is to run the provisioning runbook documented in `/app/backend/app/bootstrap.py`'s module docstring. Once provisioned, `python -m app.bootstrap` is the canonical pod-restart owner. The container can also be rebuilt mid-session (it has happened); the orchestrator's runbook handles that case identically.
>
> **The supervisor `[program:backend]` gating contract** (`autostart=false`, `autorestart=false`) is self-healing: `on-restart.sh` applies `/app/scripts/supervisord_backend.conf.template` idempotently at the top of every hook fire. Manual edits to `/etc/supervisor/conf.d/supervisord.conf` are not required and not recommended — change the template instead.

### "How each build session runs" section

Add a new step 0 before the existing step 1:

> 0. **On fresh fork only:** verify Postgres is provisioned + supervisor is wired + `on-restart.sh` is in place. If not, run the provisioning runbook from `bootstrap.py`'s docstring before proceeding. Skip on continuing sessions where the sandbox is already healthy.

### "Hard constraints" section — minor addition

Optional but worth adding to constraint #5 ("Must never lose financial data"):

> Cold-start and snapshot-restore must be self-healing without operator intervention. The bootstrap orchestrator owns this; do not regress.

---

## 6. Backlog (carried forward, not actioned this chat)

Logged for visibility, no action required:

- **C3 cosmetic:** `GET /api/v1/appraisals/{id}` returns `state=null` instead of `status` (frontend already reads from POST responses, so non-blocking). Polish-pass material.
- **C3 peripheral:** 401 on ProjectDetail (notifications/feed call). Doesn't block governance flows. Polish-pass material.
- **C3 SOTA enhancement:** "What-if I approve?" preview on Scenarios panel — one-click promote a Scenario to Base before final Go decision. Closes the loop between upside/downside modeling and sign-off pressure. Genuinely good idea; revisit during a polish pass or as a focused mini-prompt.
- **Backlog (long-standing):** IRR/ROCE on appraisals · Optimistic concurrency control · Live SONIA tracking · Decision PDF auto-generation · E-signature integration · Decision proxy ("log on behalf of").

---

## 7. State at chat close

- **Branch:** `bootstrap-fix-p0` pushed to `Rhizzo-ai/SY-Hub` via Save to GitHub. PR open against `main`.
- **Test count:** 596 passing (with `--ignore=tests/test_c3_governance_smoke.py` workaround).
- **alembic head:** `0022_appraisal_governance` (unchanged this session).
- **Permissions:** 83 (computed from `len(PERMISSION_CATALOGUE)`, not hardcoded).
- **Roles:** 10.
- **Bootstrap status:** Self-healing on cold start, snapshot-restore, container rebuild, AND supervisor config drift.

---

## 8. Verbatim opener for Chat 15

Copy the block below into Chat 15's first message. Pre-decides the structural choices so they're not re-litigated mid-session.

```
# Chat 15 — Pre-2.4 Cleanup (FK Cascade + Smoke Test Teardown)

Picking up Future_Tasks §2 — both sub-issues — as the gate before Prompt 2.4 (Budgets).

## Status at chat start

- bootstrap-fix-p0 merged to main (PR from Chat 14). Bootstrap orchestrator + supervisor self-healing template + 15 new tests live.
- Test count: 596 passing (with --ignore=tests/test_c3_governance_smoke.py workaround).
- alembic head: 0022_appraisal_governance.
- Permissions: 83. Roles: 10.

## Pre-decided structural choices (do NOT re-litigate)

1. Both sub-issues land in ONE PR/branch (branch: `pre-2.4-cleanup`). They're tightly linked — the FK fix removes the cascade-blocker, the test-teardown fix is the test that exposes the issue. Splitting creates artificial coupling between two PRs.
2. Migration is 0023_appraisal_scenarios_fk_cascade. Mechanical pattern: drop the FK, recreate with ON DELETE CASCADE. Proper downgrade() that recreates the original RESTRICT behaviour. Verify both up and down with explicit tests.
3. test_c3_governance_smoke.py teardown is a pytest fixture, not inline cleanup. Use the same conftest patterns the rest of the suite uses; do not invent new infrastructure.
4. The --ignore=tests/test_c3_governance_smoke.py flag is DROPPED from the pytest invocation as part of this PR. Full suite must be green at the new count.
5. CI work is NOT bundled here. Future_Tasks §3 is a separate effort — flag if temptation arises.

## Plan

1. Read /app/docs/SY_Homes_Future_Tasks.md §2 in full to confirm scope.
2. Diagnose: read migration 0022 to understand current FK definition; read test_c3_governance_smoke.py to understand the teardown gap.
3. Write migration 0023 with up + down. Test both directions.
4. Refactor test_c3_governance_smoke.py with proper teardown.
5. Drop the --ignore flag. Run full suite. Expect: green at the new count (596 + however many smoke tests are in that file).
6. Verify cascade actually works end-to-end: create project → appraisal → scenario → DELETE project → confirm scenario row is gone.
7. PR pre-2.4-cleanup → main. CHANGELOG entry under "Test infrastructure" or similar.

## Acceptance criteria

- Migration 0023 applies cleanly forward and reverses cleanly backward (test both).
- test_c3_governance_smoke.py runs to completion without polluting downstream tests.
- pytest invocation no longer requires --ignore=tests/test_c3_governance_smoke.py.
- Full suite green at the new count, stated explicitly in self-report.
- Cascade verified end-to-end (not just "the FK has CASCADE in pg_constraint").
- Future_Tasks §2 annotated as RESOLVED with PR reference.

## Out of scope (do not bundle)

- CI pipeline (Future_Tasks §3 — separate effort).
- Any other test infrastructure changes beyond the smoke test teardown.
- Prompt 2.4 (Budgets) work — that's Chat 16.
- Any other migration content.
- Frontend changes.

Begin with reading Future_Tasks §2 in full, then proceed with the diagnosis. Use the same Build Pack-style self-report format as Chat 14 (R0 baseline, R1-R7 build plan, §5 self-report). If baseline isn't green, STOP and self-report — do not attempt the fix on a broken baseline.
```

---

## 9. Chat 15 chat name

**`Chat 15 — Pre-2.4 Cleanup (FK Cascade + Smoke Test Teardown)`**

Discrete, gates 2.4, paired-but-tight. Estimated 1 focused session. Chat 16 then is **`Chat 16 — Prompt 2.4 (Budgets)`** assuming clean execution here.

---

## 10. Anything else to flag

- **PR review checklist for `bootstrap-fix-p0` before merge** (you, eye-check):
  1. `/app/docs/SY_Hub_Bootstrap_Fix_P0_Build_Pack.md` exists, ~378 lines.
  2. `/app/scripts/supervisord_backend.conf.template` exists.
  3. `/app/scripts/on-restart.sh` contains both the template-apply block AND the gated `supervisorctl start backend` call.
  4. `/app/scripts/README.md` "Supervisor backend gating" section reflects the self-healing template model (not the old README-edit instruction).
  5. CHANGELOG entry under "Bootstrap & ops" is present.
  6. Future_Tasks §2 and §3 entries present.
  7. Branch is `bootstrap-fix-p0`, no surprise commits, target is `main`.
- **Operational note for next session:** if you spin a new fork tomorrow, expect to re-provision Postgres. The runbook in `bootstrap.py` has the steps. This is now well-documented and should take ~5 minutes, not the 30+ it took this session.

---

_End of Chat 14 closing summary._
