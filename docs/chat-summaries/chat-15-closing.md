# Chat 15 — Closing Summary

**Session:** Chat 15 — Pre-2.4 Cleanup (narrow FK cascade fix)
**Date:** 7 May 2026
**Outcome:** ✅ Complete. Migration `0023_appraisal_scenarios_cascade` landed on `main` (via Emergent auto-commits — chat-14 §11 convention). Test count moved 596 → 597. Future_Tasks §2 split into PARTIALLY RESOLVED + two new entries (§4 smoke test, §5 remaining FKs). Gate for Prompt 2.4 (Budgets) is cleared.

---

## 1. What got done

### Primary deliverable: narrow FK cascade fix

- **`/app/backend/alembic/versions/0023_appraisal_scenarios_cascade.py`** (NEW). Mechanical migration: `op.drop_constraint` + `op.create_foreign_key` with `ondelete="CASCADE"`. Constraint name `appraisal_scenarios_scenario_appraisal_id_fkey` preserved byte-for-byte. Proper `downgrade()` restores `RESTRICT`. Verified both directions explicitly (`pg_constraint.confdeltype`: `'r'` → `'c'` on upgrade, `'c'` → `'r'` on downgrade, `'r'` → `'c'` on re-upgrade).
- **`/app/backend/tests/test_appraisal_scenarios_cascade.py`** (NEW, 1 test). Pure-DB regression: insert minimal `projects` → `appraisals` → `appraisal_scenarios` chain via raw SQL, `DELETE FROM appraisals`, assert the linked scenario row is cascade-deleted. Cleans up after itself in `finally`. Follows the direct-DB pattern from `test_appraisal_governance.py` (outcome (b) per Build Pack §R1.3).
- **`/app/backend/tests/test_bootstrap.py`** — updated two hardcoded `"0022_"` head sentinels to `"0023_"`. Mechanical bookkeeping any new migration needs; recorded as a Build Pack v5 §4 deviation.
- **`/app/docs/SY_Homes_Future_Tasks.md`** — three updates per Build Pack §R6 step 1:
  - §2 annotated **PARTIALLY RESOLVED**; original prose retained as "§2 (historical)".
  - New **§4** — Smoke test classification (the `--ignore`'d `test_c3_governance_smoke.py`). Records the gate-language reconciliation explicitly.
  - New **§5** — Remaining 4 RESTRICT FKs in 0022. Notes the `trg_decision_log_no_delete` immutability ceiling.
- **`/app/CHANGELOG.md`** — new top-level entry `pre-2.4-cleanup — appraisal_scenarios FK cascade, narrow fix (2026-05-07)`. Path used: `/app/CHANGELOG.md` (single match in repo root).
- **`/app/docs/SY_Hub_Pre_2_4_Cleanup_Build_Pack.md`** (NEW) — Build Pack v5 verbatim, committed as the first file action per chat-14 pattern.

### Acceptance criteria — all met

| Build Pack §2 | Status |
|---|---|
| 1. 0023 applies forward AND reverses backward | ✅ §R4 (3 explicit transitions verified) |
| 2. `confdeltype = 'c'` after upgrade; matches recorded baseline after downgrade | ✅ §R4 |
| 3. New regression test passes; lives in regression suite | ✅ `test_deleting_appraisal_cascades_to_scenarios` |
| 4. Full test suite green at 596 + 1 = 597 | ✅ §R5 (`pytest --ignore=tests/test_c3_governance_smoke.py` → 597 passed) |
| 5. Bootstrap-from-0023 spot-check passes | ✅ §R4.6 (rc=0, perms=83, roles=10) |
| 6. Future_Tasks updated (§2 PARTIALLY RESOLVED + 2 new entries) | ✅ §R6.1 |
| 7. CHANGELOG entry added | ✅ §R6.2 |

---

## 2. Self-report (Build Pack v5 §5 template, filled)

```
### R0 — Baseline
- git pull: clean (already up to date with origin/main)
- bootstrap rc: 0
- alembic current: 0022_appraisal_governance     ← expected
- pytest --ignore=...: 596 passing               ← expected
- R0.5 FK row 1: conname=appraisal_scenarios_parent_scenario_appraisal_id_fkey, confdeltype=r
- R0.5 FK row 2: conname=appraisal_scenarios_scenario_appraisal_id_fkey, confdeltype=r
- R0.6 source-vs-pg_constraint match: yes
- Notes: Sandbox was a fresh fork — no Postgres installed. Followed the
  provisioning runbook in app/bootstrap.py (PGDG PG16, syhomes role + DB,
  pgcrypto extension, [program:postgres] supervisor block) before running
  bootstrap. This is the same provisioning Chat 14 first added; doc was
  authoritative.

### R1 — Diagnose
- 0022 revision string: 0022_appraisal_governance ← expected
- 0022 FK source line 132: scenario_appraisal_id uuid NOT NULL REFERENCES appraisals(id) ON DELETE RESTRICT,
- 0022 FK source line 133: parent_scenario_appraisal_id uuid REFERENCES appraisals(id) ON DELETE RESTRICT,
- Auto-named constraint matches R0.5: yes
- alembic.ini file_template: commented out (default %(rev)s_%(slug)s)
- Conftest discovery outcome: (b) — direct DB-session pattern via
  create_engine(DATABASE_URL) + engine.begin() context manager.
- Fixtures or imports the regression test will use:
  `from sqlalchemy import create_engine, text; eng = create_engine(DATABASE_URL, future=True)`
  Template: tests/test_appraisal_governance.py.
- Notes: tests/conftest.py is HTTP-only (login_with_auto_enroll, plain_login).
  The DB-direct test files (test_appraisal_governance.py, test_appraisals.py)
  use module-scoped engine fixture. Regression test goes one step purer —
  function-local engine, raw-SQL inserts, no fixtures.

### R2 — Migration 0023 forward
- File path: /app/backend/alembic/versions/0023_appraisal_scenarios_cascade.py
- revision: 0023_appraisal_scenarios_cascade   ← DEVIATION from Build Pack
  (Build Pack §R2 specified `0023_appraisal_scenarios_fk_cascade` — 35 chars.
  alembic_version.version_num is varchar(32). First upgrade attempt failed
  with StringDataRightTruncation. Shortened by dropping `_fk_` segment.
  See "Deviations" below.)
- down_revision: 0022_appraisal_governance     ← expected
- Constraint name preserved byte-for-byte: yes
  (`appraisal_scenarios_scenario_appraisal_id_fkey` in both drop_constraint
   and create_foreign_key calls.)
- Notes: not generated via `alembic revision -m` (would have used a random
  hex prefix because file_template is commented out); created the file
  directly to match the existing 0022 / 0021 / 0020 numbered convention.

### R3 — Migration 0023 reverse
- downgrade() ondelete value: "RESTRICT", matching R0.5: yes (R0.5 recorded 'r')
- Notes:

### R4 — Verify both directions + bootstrap
- After upgrade, scenario_appraisal_id_fkey confdeltype: c
- After upgrade, parent_scenario_appraisal_id_fkey confdeltype: r (untouched ✓)
- After downgrade -1, scenario_appraisal_id_fkey confdeltype: r
- After re-upgrade, head: 0023_appraisal_scenarios_cascade ✓
- R4.6 bootstrap-from-0023 rc: 0 (perms=83, roles=10)
- Notes:

### R5 — Regression test
- File: /app/backend/tests/test_appraisal_scenarios_cascade.py
- Conftest path used: outcome (b) per R1.3 — pure raw-SQL via create_engine
- Test passes in isolation: yes
- Full-suite test count: 597 ← expected (596 baseline + 1 new)
- Notes: Initial draft missed `entity` and `created_by_user_id` bind params;
  fixed in second edit. No fixture infrastructure changes required.

### R6 — Documentation
- Future_Tasks updated: yes
  - Existing §2 marked PARTIALLY RESOLVED: yes (with full reclassification prose)
  - New entry: smoke test classification: yes (§4)
  - New entry: remaining 4 RESTRICT FKs: yes (§5)
- CHANGELOG path used: /app/CHANGELOG.md (single match in repo)
- CHANGELOG entry added: yes (top-of-file under "Entries", per existing convention)
- Notes:

### Deviations from Build Pack
- Revision string shortened from `0023_appraisal_scenarios_fk_cascade` (35 chars,
  Build Pack §R2 spec) to `0023_appraisal_scenarios_cascade` (32 chars). Forced
  by `alembic_version.version_num` being `varchar(32)` — the spec value didn't
  fit. Drop is `_fk_` only; the meaning is preserved (file content makes the
  FK context unambiguous). File name follows revision string for consistency.
  Documented in CHANGELOG and migration's module docstring.
- `tests/test_bootstrap.py` had two assertions hardcoded to `head.startswith("0022_")`
  (lines 199, 216). Bumped to `"0023_"` — mechanical bookkeeping that any new
  migration needs; the Build Pack §4 "no other code changes" clause didn't
  anticipate this sentinel. Logged in CHANGELOG.

### Final state (sanity-check expectations pre-filled)
- alembic head: 0023_appraisal_scenarios_cascade   ← (renamed from spec — see Deviations)
- Test count: 597 passing (with --ignore=tests/test_c3_governance_smoke.py)
- Permissions: 83  ← matches expected
- Roles: 10        ← matches expected
- Bootstrap status: still self-healing on cold start (verified rc=0)
- Smoke test --ignore flag: still in place (deferred work, per spec §4)
- Future_Tasks §2: PARTIALLY RESOLVED + §4 (smoke test) and §5 (remaining FKs) split off
- Future_Tasks §3 (CI): still open, not touched this session
```

---

## 3. Files committed (Build Pack §6 chat-end ritual checklist)

Eye-checked at chat close (and after Save-to-GitHub):

1. ✅ `/app/backend/alembic/versions/0023_appraisal_scenarios_cascade.py` (NEW)
2. ✅ `/app/backend/tests/test_appraisal_scenarios_cascade.py` (NEW)
3. ✅ `/app/docs/SY_Homes_Future_Tasks.md` (§2 annotated + §4, §5 added)
4. ✅ `/app/CHANGELOG.md` (Chat 15 entry)
5. ✅ `/app/docs/SY_Hub_Pre_2_4_Cleanup_Build_Pack.md` (NEW — Build Pack v5 verbatim)
6. ✅ `/app/docs/chat-summaries/chat-15-closing.md` (this file)

Plus:
- ✅ `/app/backend/tests/test_bootstrap.py` (deviation: head sentinel bumped 0022→0023)

---

## 4. Decisions locked this session

1. **Build Pack revision name vs. alembic_version column width is a known constraint.** `alembic_version.version_num` is `varchar(32)` (Postgres default). Future Build Packs that prescribe revision names should keep the slug ≤ 32 chars total, including the `00NN_` prefix. Long-term fix (bumping to `varchar(64)`) is out of scope until the next migration name pushes against the limit.
2. **`appraisal_scenarios_scenario_appraisal_id_fkey` is now CASCADE.** This is now part of the SY-Hub canonical schema. The decision to leave the parent_scenario sibling as RESTRICT is recorded in Future_Tasks §5; revisit when a use case surfaces.
3. **Smoke test classification is no longer a gate for Prompt 2.4.** Documented in Future_Tasks §2 (PARTIALLY RESOLVED) and §4 (architectural classification). The `--ignore=tests/test_c3_governance_smoke.py` flag stays.
4. **Test-bootstrap head sentinels are part of any migration's bookkeeping.** When the next migration lands, the agent must update these too. Recorded here so it isn't a surprise.

---

## 5. Risks / watch-fors carried into Chat 16

- The four other RESTRICT FKs in 0022 remain unchanged. Budgets work probably won't trip on them (Budgets builds on `projects` + new `budgets`, not appraisals chain), but if any Budgets test needs `DELETE FROM appraisals` to cascade, it'll hit `parent_scenario_appraisal_id_fkey` first. Future_Tasks §5 covers this.
- The smoke test is still `--ignore`'d. Anyone reading the test count needs to know the 597 baseline excludes the smoke test — same as the 596 baseline did.
- `alembic_version.version_num` width constraint (varchar(32)). Document for future Build Packs.

---

## 6. Ready for next chat

**Chat 16:** Prompt 2.4 (Budgets). All gates clear:
- Bootstrap orchestrator self-healing (Chat 14 §1 RESOLVED).
- FK cascade for `appraisal_scenarios.scenario_appraisal_id` fixed (Chat 15 §2 PARTIALLY RESOLVED with §2b done; §2a → §4 reclassified to non-gate).
- Test suite at 597 passing.
- Future_Tasks tidy: §1 RESOLVED, §2 PARTIALLY RESOLVED, §3 (CI) open, §4 (smoke), §5 (4 FKs) — all P2 / non-gate.

_End of chat-15 closing summary._
