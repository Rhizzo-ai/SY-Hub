# Build Pack v5 — Chat 15: Pre-2.4 Cleanup (Narrow FK Cascade)

**Unit of work:** `pre-2.4-cleanup` (logical label; Emergent's Save-to-GitHub will land as auto-commits to `main` — no real branch will exist on `Rhizzo-ai/SY-Hub`. See chat-14-closing §11.)
**Gates:** Prompt 2.4 (Budgets).
**Estimated size:** Half a session. One mechanical migration + one pure-DB regression test + Future_Tasks bookkeeping.
**Build Pack version:** v5. Scope narrowed from v2 after pre-paste audit of the live files (`0022_appraisal_governance.py`, `tests/test_c3_governance_smoke.py`, `tests/conftest.py`) revealed the v1/v2 framing rested on misdiagnoses. v4 tightened §R1 step 3 with confirmed pointer files. v5 addresses the gate-language deviation surfaced by post-sync audit of Future_Tasks §2 — explicit prose now reclassifies §2a from "ship-blocker bug" to "architectural classification question" so the gate logic for Prompt 2.4 collapses to §2b (the FK fix) alone. See §9 for the full audit history.

---

## §0 — Pre-flight

Before any other action: `cd /app && git pull origin main`. The sandbox may have been forked or rebuilt; resync first.

If the container is a fresh fork (no Postgres, no `on-restart.sh`), follow the provisioning runbook in `/app/backend/app/bootstrap.py`'s module docstring before proceeding. Do NOT begin diagnosis on an unprovisioned sandbox.

---

## §1 — Background and scope

Future_Tasks §2 originally bundled two sub-issues:

- **§2a** — `tests/test_c3_governance_smoke.py` test-infrastructure problem (currently masked by `--ignore`).
- **§2b** — `appraisal_scenarios.scenario_appraisal_id` FK was created `ON DELETE RESTRICT` in migration 0022.

Pre-paste audit of the live files revealed §2a and §2b are NOT tightly coupled and NOT a single unit of work:

- The smoke test runs against a public preview URL via HTTP, not the DB. It uses `requests.Session` with cookie auth, not a `db_session` fixture. Its data-creation is idempotent at the HTTP level (re-uses `TEST_C3_E2E` if found). It has `scope="module"` fixtures by deliberate design — not "missing teardown" but "intentionally persistent within a module run."
- Even with the FK changed to CASCADE, the smoke test has no path to delete data — there's no `DELETE /api/v1/projects/{id}` endpoint, and the smoke test never touches the DB directly.
- 0022 contains FIVE `ON DELETE RESTRICT` FKs against `appraisals`, not one. Plus immutability triggers (`trg_decision_log_no_update`, `trg_decision_log_no_delete`) that put a permanent ceiling on cascade-based teardown of any test creating decision-log rows.

This Build Pack therefore scopes to **§2b ONLY**, narrowed further: the single FK the opener names. The other four RESTRICT FKs and the smoke-test classification question are recorded as new Future_Tasks entries for separate sessions.

**Gate-language reconciliation.** Future_Tasks §2 (as it currently stands on `main`) states: "Hard gate: must be resolved before Prompt 2.4 (Budgets)." That language was written when §2a was thought to be a teardown bug that would compound risk in Budgets work. The pre-paste audit revealed §2a is actually an architectural classification question (smoke test runs HTTP-only against the public preview URL by design — there is no DB-side teardown bug to fix; the question is whether to keep it in `tests/` or move it to a deploy-time probe stage). It does NOT share infrastructure with Budgets and does NOT compound risk in 2.4 work. Therefore the operational gate for Prompt 2.4 is §2b alone (the FK fix). §6 below records this reclassification explicitly in the Future_Tasks update so the gate logic is auditable from the doc itself, not just from this Build Pack.

**Out of this Build Pack's scope (recorded for future work):**
- Smoke test reclassification or teardown rebuild → new Future_Tasks entry (was §2a, now its own).
- The other 4 `ON DELETE RESTRICT` FKs in 0022 (`parent_scenario_appraisal_id`, both `appraisal_revisions` FKs, `appraisal_decision_log.appraisal_id`) → new Future_Tasks entry, deferred until an actual use case requires the chain.
- The `--ignore=tests/test_c3_governance_smoke.py` flag → STAYS in place; removing it is part of the smoke-test work, not the FK work.

---

## §2 — Acceptance criteria

All must hold at chat close:

1. Migration `0023_appraisal_scenarios_fk_cascade` applies cleanly forward AND reverses cleanly backward (both directions tested explicitly).
2. After upgrade, `pg_constraint.confdeltype` for `appraisal_scenarios_scenario_appraisal_id_fkey` = `'c'` (CASCADE). After downgrade, value matches what §R0 step 5 recorded (expected `'r'` based on 0022 source — but record then verify, do not presume).
3. New regression test passes: deleting an appraisal cascades to delete the linked `appraisal_scenarios` row. Lives in the regression suite (NOT in the smoke test file), runs on every pytest invocation forever.
4. Full test suite green at `596 + 1` (one new regression test). The `--ignore=tests/test_c3_governance_smoke.py` flag stays — full pytest invocation is unchanged from chat-14 close except for the new test count.
5. Bootstrap-from-0023 spot-check passes (`python -m app.bootstrap` rc=0 with alembic at 0023).
6. `/app/docs/SY_Homes_Future_Tasks.md` updated:
   - §2 (the original combined entry) annotated `PARTIALLY RESOLVED` — explain the split.
   - New entry: smoke test classification / teardown rebuild (was §2a).
   - New entry: remaining 4 RESTRICT FKs in 0022 (`parent_scenario_appraisal_id`, `appraisal_revisions.appraisal_id_from`, `appraisal_revisions.appraisal_id_to`, `appraisal_decision_log.appraisal_id`) — deferred until a use case requires cascade.
7. CHANGELOG entry added at the path discovered in §R8.

---

## §3 — Build plan

### §R0 — Baseline (STOP gate)

1. `cd /app && git pull origin main` — confirm clean.
2. `python -m app.bootstrap` — confirm rc=0.
3. `cd /app/backend && alembic current` — expect `0022_appraisal_governance` (head).
4. `cd /app/backend && pytest --ignore=tests/test_c3_governance_smoke.py -q` — expect exactly **596 passing**.
5. **Record** the FK current state — record verbatim, do not presume:
   ```sql
   SELECT conname, confdeltype, conrelid::regclass, confrelid::regclass
   FROM pg_constraint
   WHERE conrelid = 'appraisal_scenarios'::regclass
     AND confrelid = 'appraisals'::regclass;
   ```
   Two rows expected (one for `scenario_appraisal_id`, one for `parent_scenario_appraisal_id`). Identify which `conname` corresponds to `scenario_appraisal_id` — the auto-named one will be `appraisal_scenarios_scenario_appraisal_id_fkey`. Record both `conname` values and both `confdeltype` values. Legend: `'r'` = RESTRICT, `'a'` = NO ACTION (default), `'c'` = CASCADE, `'n'` = SET NULL, `'d'` = SET DEFAULT.
6. Confirm 0022's source matches what's in the DB. Read `/app/backend/alembic/versions/0022_appraisal_governance.py` lines 132–133 — confirm both FKs are written as `REFERENCES appraisals(id) ON DELETE RESTRICT`. If source and pg_constraint disagree, STOP and self-report — schema has drifted.

**Self-report and STOP if:**
- Test count differs from 596.
- alembic head is not 0022.
- Step 5 query returns ≠ 2 rows.
- Source vs. pg_constraint disagrees in step 6.

---

### §R1 — Diagnose

1. Read `/app/backend/alembic/versions/0022_appraisal_governance.py` — confirm:
   - Revision string: `revision = "0022_appraisal_governance"` (line 42).
   - The `appraisal_scenarios` table is created via `op.execute("""CREATE TABLE...""")` raw SQL (line 127), NOT via `op.create_table()`. This means the FK is auto-named by Postgres using its `__fkey` convention. Expected name: `appraisal_scenarios_scenario_appraisal_id_fkey`. Confirm against §R0 step 5's recorded `conname`.
   - The downgrade pattern at line 372: 0022 doesn't `op.drop_constraint` the FK explicitly — it just `op.drop_table("appraisal_scenarios")` at line 406, which drops the FK as part of dropping the table.
2. Read `/app/backend/alembic.ini` — record the `file_template` value. Confirms the naming convention for the new migration.
3. **Search for fixture infrastructure** the regression test in §R5 will use. Pre-paste audit confirmed there is exactly ONE `conftest.py` (at `/app/backend/tests/conftest.py`) and it is HTTP-oriented (`login_with_auto_enroll`, `plain_login`). Test files in `/backend/tests/` that don't use those helpers must be using direct DB access — these are the templates to match.

   **Specifically read** the following files as templates (in order — first match wins):
   - `/app/backend/tests/test_appraisal_governance.py` — most likely the closest template (parallels the C2 governance work the smoke test mirrors via HTTP; almost certainly DB-direct).
   - `/app/backend/tests/test_appraisals.py` — second-closest (same `appraisals` table the regression test will exercise).
   - `/app/backend/tests/test_audit_log.py` — fallback if the two above don't reveal a clean DB-session pattern.

   For each, record:
   - Imports used to obtain a DB session (e.g. `from app.db import SessionLocal`, `from app.database import get_db`, fixture-injected, etc.).
   - How a project / appraisal / scenario row is created (raw SQL via `session.execute(text(...))`, ORM model construction, or a helper).
   - Cleanup / teardown pattern (transactional rollback, explicit DELETE, or none).

   Three possible outcomes:
   - **(a)** Reusable factory fixtures discovered in one of the template files (e.g. `@pytest.fixture` returning a project/appraisal) → use them in §R5.
   - **(b)** No fixtures, but a consistent direct-DB pattern → §R5 mimics that exact pattern with raw SQL using the same imports.
   - **(c)** Neither — every test is HTTP-only against the preview URL → STOP and self-report (extremely unlikely given file names; if this happens something is wrong with the read).

   Outcome (b) is expected based on the pre-paste audit. Record which outcome applies and which template file's pattern the regression test will follow.

**Self-report deliverable in §5:**
- 0022 FK source line (verbatim).
- Auto-named constraint matched against pg_constraint: yes/no.
- alembic.ini `file_template` value.
- Conftest discovery result: (a), (b), or (c). With specific fixture names or import path the regression test will use.

---

### §R2 — Migration 0023 forward

1. `cd /app/backend && alembic revision -m "appraisal_scenarios_fk_cascade"`. Rename the file if needed to match 0022's convention: `0023_appraisal_scenarios_fk_cascade.py`.
2. Set `revision = "0023_appraisal_scenarios_fk_cascade"` and `down_revision = "0022_appraisal_governance"`.
3. `upgrade()` body — use the **exact** constraint name recorded in §R0 step 5:

   ```python
   def upgrade() -> None:
       op.drop_constraint(
           "appraisal_scenarios_scenario_appraisal_id_fkey",  # confirm matches R0.5
           "appraisal_scenarios",
           type_="foreignkey",
       )
       op.create_foreign_key(
           "appraisal_scenarios_scenario_appraisal_id_fkey",  # MUST match the dropped name byte-for-byte
           "appraisal_scenarios",
           "appraisals",
           ["scenario_appraisal_id"],
           ["id"],
           ondelete="CASCADE",
       )
   ```

**Critical:** The constraint name must be preserved byte-for-byte across drop and recreate. If §R0 step 5 recorded a different name from the expected `appraisal_scenarios_scenario_appraisal_id_fkey`, use the recorded value, not this assumption.

---

### §R3 — Migration 0023 reverse

1. `downgrade()` body — restore 0022's prior behaviour as recorded in §R0 step 5:
   ```python
   def downgrade() -> None:
       op.drop_constraint(
           "appraisal_scenarios_scenario_appraisal_id_fkey",
           "appraisal_scenarios",
           type_="foreignkey",
       )
       op.create_foreign_key(
           "appraisal_scenarios_scenario_appraisal_id_fkey",
           "appraisal_scenarios",
           "appraisals",
           ["scenario_appraisal_id"],
           ["id"],
           ondelete="RESTRICT",  # adjust if R0.5 recorded a different value
       )
   ```
2. Adjust `ondelete` to match §R0 step 5's recorded value:
   - `'r'` → `ondelete="RESTRICT"` (expected per 0022 source line 132).
   - `'a'` → omit `ondelete` parameter entirely (Postgres default = NO ACTION).
   - Other values: STOP and self-report.

---

### §R4 — Verify migration both directions + bootstrap

1. `alembic upgrade head` → confirm head = 0023.
2. SQL check (same query as §R0 step 5) — expect `confdeltype = 'c'` for `scenario_appraisal_id_fkey`. The `parent_scenario_appraisal_id_fkey` row should still show its original value (we're not touching it).
3. `alembic downgrade -1` → confirm head = 0022.
4. SQL check — `scenario_appraisal_id_fkey` `confdeltype` matches §R0 step 5's recorded value exactly.
5. `alembic upgrade head` → leave at 0023 for the rest of the session.
6. **Bootstrap-from-0023 spot-check.** Run `python -m app.bootstrap`. Expect rc=0 and no surprises in invariants. Closes the snapshot-restore loop chat-14 cared about.

Self-report records all `confdeltype` reads verbatim plus the bootstrap rc.

---

### §R5 — Regression test

**Goal:** A permanent regression test that proves the FK cascade actually works through the ORM session and surrounding code, not just that pg_constraint says it should.

1. Create `tests/test_appraisal_scenarios_cascade.py`. (Or extend an existing migration / data-model test file if §R1 step 3 reveals an established home for cascade tests.)
2. Test logic — adapt to the conftest discovery outcome from §R1 step 3:

   **If outcome (a) — reusable fixtures exist:**
   ```python
   def test_deleting_appraisal_cascades_to_scenarios(
       <fixtures from R1.3>,
       <db_session>,
       <appraisal_factory>,
   ):
       appraisal = <create via factory>
       scenario = <create scenario referencing appraisal.id>
       scenario_id = scenario.id

       <db_session>.execute(text("DELETE FROM appraisals WHERE id = :id"), {"id": appraisal.id})
       <db_session>.commit()

       result = <db_session>.execute(
           text("SELECT 1 FROM appraisal_scenarios WHERE id = :id"),
           {"id": scenario_id},
       ).scalar()
       assert result is None
   ```

   **If outcome (b) — no fixtures but consistent DB-session pattern:**
   ```python
   from app.db import SessionLocal  # or whatever pattern R1.3 found
   from sqlalchemy import text
   import uuid

   def test_deleting_appraisal_cascades_to_scenarios():
       session = SessionLocal()
       try:
           # Insert a minimal project/appraisal/scenario chain via raw SQL.
           # Use unique names to avoid collisions with pre-existing data.
           # Read 0022's CREATE TABLE statements to know which columns are NOT NULL.
           project_id = ...
           appraisal_id = ...
           scenario_id = ...

           session.execute(text("DELETE FROM appraisals WHERE id = :id"), {"id": appraisal_id})
           session.commit()

           result = session.execute(
               text("SELECT 1 FROM appraisal_scenarios WHERE id = :id"),
               {"id": scenario_id},
           ).scalar()
           assert result is None

           # Clean up the project we created.
           session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
           session.commit()
       finally:
           session.close()
   ```

   **If outcome (c) — no DB pattern at all:**
   STOP and self-report. Writing one from scratch is out of scope for this Build Pack; the regression test depends on infrastructure existing somewhere. Surface this as a finding and propose a smaller scope (the migration alone, with manual one-shot verification documented in self-report).

3. The test MUST clean up after itself — DELETE everything it created at the end. The cascade test verifies deletion works; abandoning rows that you just demonstrated CAN be deleted would be sloppy.

4. Run the new test in isolation: green.
5. Run the full suite (`pytest --ignore=tests/test_c3_governance_smoke.py -q`) with the new test: green at 597.

**Constraint:** Do NOT touch `tests/test_c3_governance_smoke.py`. Do NOT remove the `--ignore` flag. The smoke test work is deferred to a separate session.

---

### §R6 — Documentation

1. **`/app/docs/SY_Homes_Future_Tasks.md`** — three updates:

   a. **Existing §2 entry** — annotate as `PARTIALLY RESOLVED`. Briefly explain that §2b (the FK on `scenario_appraisal_id`) is fixed; §2a (smoke test) and the other 4 RESTRICT FKs split into new entries below.

   b. **New entry — Smoke test classification & teardown:**
   ```
   ### Smoke test (test_c3_governance_smoke.py) classification
   `tests/test_c3_governance_smoke.py` runs against the public preview URL
   via HTTP, uses module-scoped persistent data, and has no DB-side teardown
   path (no DELETE endpoint exists). Currently masked by
   --ignore=tests/test_c3_governance_smoke.py in the pytest invocation.

   **Reclassified during Chat 15 pre-paste audit.** The original §2 entry
   coupled this with the FK fix and stated "Hard gate: must be resolved
   before Prompt 2.4 (Budgets)." That gate language was based on the
   assumption that the smoke test had a teardown bug that would compound
   risk in Budgets work. The audit revealed:
   - The smoke test runs HTTP-only against the preview URL by design
     (not the DB).
   - It has scope="module" persistence as a deliberate choice, not a bug.
   - It does not share infrastructure with Budgets work.
   - There is no actionable "teardown bug" to fix — the question is
     architectural: keep it in tests/ or move it to a deploy-time probe.
   The original §2 gate logic for Prompt 2.4 therefore collapses to §2b
   alone (the FK fix, resolved in Chat 15). This entry is no longer a
   gate for 2.4.

   Decision still needed: classify as a deploy-time probe (move out of
   tests/, run as a separate stage) OR rebuild with DB-side teardown
   (would require a new DELETE endpoint and admin-only RBAC). Likely
   paired with Future_Tasks §3 (CI pipeline) since the test belongs in
   CI's deploy-probe stage anyway.
   ```

   c. **New entry — Remaining RESTRICT FKs in 0022:**
   ```
   ### Other ON DELETE RESTRICT FKs in migration 0022
   Migration 0022 created 5 FKs against `appraisals` with ON DELETE RESTRICT.
   Chat 15 fixed only `appraisal_scenarios.scenario_appraisal_id`. Remaining
   four (deferred until a use case requires DELETE FROM appraisals to cascade):
   - appraisal_scenarios.parent_scenario_appraisal_id → appraisals
   - appraisal_revisions.appraisal_id_from → appraisals
   - appraisal_revisions.appraisal_id_to → appraisals
   - appraisal_decision_log.appraisal_id → appraisals

   Note the hard ceiling: appraisal_decision_log has BEFORE DELETE trigger
   `trg_decision_log_no_delete` that RAISE EXCEPTIONs on any DELETE
   (regulatory append-only). Even with FK cascade, any appraisal with logged
   decisions cannot be deleted. Cascade for that FK is therefore only useful
   in a "purge unsigned-off appraisals" workflow.

   Currently no use case exists for DELETE FROM appraisals. This is debt-
   with-no-pressure; revisit when an actual workflow needs it.
   ```

2. **CHANGELOG.** Locate via `find /app -name "CHANGELOG.md" -not -path "*/node_modules/*"`. If found at one path, use it. If multiple, use the closest to repo root. If none, create at `/app/CHANGELOG.md`. State the path used in §5.

   Append entry:
   ```
   ## Chat 15 — FK cascade fix (narrow) (<DATE>)
   - Migration 0023: appraisal_scenarios_scenario_appraisal_id_fkey
     changed ON DELETE RESTRICT → CASCADE.
   - New regression test: tests/test_appraisal_scenarios_cascade.py
     (test_deleting_appraisal_cascades_to_scenarios) — proves cascade
     works end-to-end through the ORM session, not just at the constraint
     definition level.
   - Test count: 596 → 597.
   - Future_Tasks §2 split: smoke test classification and remaining 4
     RESTRICT FKs deferred to separate sessions (see Future_Tasks).
   ```

3. **DO NOT** edit this Build Pack document once committed alongside the code. It's a contemporaneous artefact.

---

## §4 — Out of scope

Do NOT bundle. If temptation arises, log to Future_Tasks and move on.

- ANY work on `tests/test_c3_governance_smoke.py` (including its `--ignore` flag).
- The other 4 RESTRICT FKs in 0022.
- CI pipeline (Future_Tasks §3).
- Prompt 2.4 (Budgets) — Chat 16.
- Frontend changes.
- New permissions, roles, models, or seeds.
- Refactors to the bootstrap orchestrator.
- Auth / RBAC / governance behavioural change.

---

## §5 — Self-report template (fill in at chat close)

Reproduce verbatim with each placeholder filled. Pre-filled values are sanity-check expectations — deviation is a regression to investigate.

```
### R0 — Baseline
- git pull: <clean / had updates>
- bootstrap rc: <0 / N>
- alembic current: <recorded>     ← expected 0022_appraisal_governance
- pytest --ignore=...: <N> passing  ← expected 596
- R0.5 FK row 1: conname=<recorded>, confdeltype=<recorded>
- R0.5 FK row 2: conname=<recorded>, confdeltype=<recorded>
- R0.6 source-vs-pg_constraint match: yes / no
- Notes:

### R1 — Diagnose
- 0022 revision string: 0022_appraisal_governance ← expected
- 0022 FK source line (132–133): <verbatim>
- Auto-named constraint matches R0.5: yes / no
- alembic.ini file_template: <recorded>
- Conftest discovery outcome: (a) reusable fixtures / (b) DB-session pattern / (c) HTTP-only
- Fixtures or imports the regression test will use: <recorded>
- Notes:

### R2 — Migration 0023 forward
- File path: <recorded>
- revision: 0023_appraisal_scenarios_fk_cascade ← expected
- down_revision: 0022_appraisal_governance ← expected
- Constraint name preserved byte-for-byte: yes / no
- Notes:

### R3 — Migration 0023 reverse
- downgrade() ondelete value: <recorded>, matching R0.5: yes / no
- Notes:

### R4 — Verify both directions + bootstrap
- After upgrade, scenario_appraisal_id_fkey confdeltype: <recorded>
- After upgrade, parent_scenario_appraisal_id_fkey confdeltype: <recorded>
- After downgrade -1, scenario_appraisal_id_fkey confdeltype: <recorded>
- After re-upgrade, head: <0023 expected>
- R4.6 bootstrap-from-0023 rc: <0 expected>
- Notes:

### R5 — Regression test
- File: <path>
- Conftest path used: outcome (a/b/c) per R1.3
- Test passes in isolation: yes / no
- Full-suite test count: <N>  ← expected 597
- Notes:

### R6 — Documentation
- Future_Tasks updated: yes / no
  - Existing §2 marked PARTIALLY RESOLVED: yes / no
  - New entry: smoke test classification: yes / no
  - New entry: remaining 4 RESTRICT FKs: yes / no
- CHANGELOG path used: <path>
- CHANGELOG entry added: yes / no
- Notes:

### Deviations from Build Pack
- <none / list>

### Final state (sanity-check expectations pre-filled)
- alembic head: 0023_appraisal_scenarios_fk_cascade ← expected
- Test count: 597 passing (with --ignore=tests/test_c3_governance_smoke.py)
- Permissions: 83 ← expected (deviation = regression)
- Roles: 10 ← expected (deviation = regression)
- Bootstrap status: still self-healing on cold start
- Smoke test --ignore flag: still in place (deferred work)
- Future_Tasks §2: PARTIALLY RESOLVED + 2 new entries split off
- Future_Tasks §3 (CI): still open, not touched this session
```

---

## §6 — Chat-end ritual (mandatory)

Before declaring close: open `https://github.com/Rhizzo-ai/SY-Hub` in the browser and eye-check that the most recent auto-commits include all of:

1. `/app/backend/alembic/versions/0023_appraisal_scenarios_fk_cascade.py` (new)
2. `/app/backend/tests/test_appraisal_scenarios_cascade.py` (new)
3. `/app/docs/SY_Homes_Future_Tasks.md` (existing §2 annotated + 2 new entries)
4. CHANGELOG at the path identified in §R6 step 2 (Chat 15 entry)
5. `/app/docs/SY_Hub_Pre_2_4_Cleanup_Build_Pack.md` (this document)
6. `/app/docs/chat-summaries/chat-15-closing.md` (closing summary)

The chat-14 agent's self-report claimed Future_Tasks updates that hadn't actually landed; commit `51fc53d` was needed post-close to fix it. Do not repeat. If any of the above six items are missing from `main` after Save-to-GitHub, fix BEFORE declaring closed.

---

## §7 — Risks and watch-fors

1. **Constraint name preservation.** The FK is auto-named by Postgres (0022 uses raw `op.execute("""CREATE TABLE...""")`, not `op.create_foreign_key`). Auto-name convention is `<table>_<column>_fkey` → `appraisal_scenarios_scenario_appraisal_id_fkey`. If §R0 step 5 records a different name, use the recorded value.
2. **`confdeltype` baseline.** Expected `'r'` (RESTRICT — 0022 source line 132 is explicit). If the recorded value differs, the downgrade must match what was recorded, not what was expected.
3. **The other RESTRICT FK on the same table.** `appraisal_scenarios.parent_scenario_appraisal_id` is also RESTRICT. This Build Pack does NOT touch it — verify it's untouched in §R4 step 2.
4. **Conftest discovery may surface outcome (c) — no infrastructure.** §R5 has guidance for this case (STOP and propose smaller scope) — don't invent infrastructure.
5. **Trigger interaction.** 0022 line 197 creates `trg_scenarios_validate_parent` which fires BEFORE INSERT/UPDATE on `appraisal_scenarios`. The cascade DELETE shouldn't fire it (DELETE isn't in the trigger's event list), but worth knowing if anything weird happens.
6. **Migration locks ACCESS EXCLUSIVE briefly.** `op.drop_constraint` + `op.create_foreign_key` acquires ACCESS EXCLUSIVE on `appraisal_scenarios` for the duration of the transaction. Doesn't matter for the dev DB but worth noting.
7. **Self-report drift.** Chat 14 had it; Chat 15 must not. §6 is the antidote.

---

## §8 — Notes for the pre-paste auditor (Rhys)

Items flagged for explicit audit before paste:

- **Scope is deliberately narrow** (one FK, one regression test, three Future_Tasks entries). The pre-paste audit revealed the v1/v2 framing was mis-scoped; v3 corrects that. If you want broader scope (the other 4 RESTRICT FKs, smoke test rebuild), say so and I'll produce v4 — but my recommendation is to land v3 cleanly first and revisit the broader work as separate sessions.
- **§R5 outcome (c)** is a STOP path. If the conftest discovery finds no DB infrastructure at all, the agent stops rather than inventing. Probability is low (596 backend tests must use SOMETHING) but the path exists.
- **§R6 Future_Tasks edits** create two new entries plus annotate the existing §2. If you'd rather use a different format for the split (e.g. completely replace §2 with a backreference, or move it to a "RESOLVED" archive), say so.
- **CHANGELOG path discovery** runs at the start of §R6 step 2 — path is not pre-assumed. If you have a fixed path in mind (and remember chat-14 §12 flagged this as uncertain), state it now.

---

## §9 — Audit changelog (v1 → v2 → v3 → v4 → v5)

For traceability.

**v1 → v2** (post-structural-audit):
- Integrated B1 (confdeltype baseline), B2 (constraint name placeholder), B3 (fixture name placeholder), S1 (R7 split into narrow + broad), S2 (--ignore enumeration), S3 (row-count baseline), S4 (audit log FK check), S5 (function-scoped fixture), S6 (alembic file_template), S7 (collection-error detection), S8 (N>0 verification), S9 (acceptance criterion tightening), S10 (CHANGELOG path discovery), N1 (lock note), N2 (bootstrap-from-0023 check), N4 (smoke test classification framing), N5 (sanity-check expectations), C2 (prose tightening). Skipped N3 (alembic idempotency).

**v2 → v3** (post-live-file audit; structural rescope):
- **F1** — Constraint name corrected: actual name is `appraisal_scenarios_scenario_appraisal_id_fkey` (auto-named by Postgres because 0022 uses raw `op.execute("""CREATE TABLE...""")` not `op.create_foreign_key`). Not the opener's `scenario_appraisal_id_fkey`.
- **F2** — Acknowledged: 0022 contains 5 RESTRICT FKs against `appraisals`, not 1. Scope narrowed to ONE FK; remaining 4 deferred to new Future_Tasks entry.
- **F3** — Acknowledged: `trg_decision_log_no_delete` puts a permanent ceiling on cascade-based teardown of any test creating decision rows. Recorded in the new Future_Tasks entry for §F2.
- **F4** — Acknowledged: smoke test is HTTP-based against public preview URL with module-scoped persistent data BY DESIGN. The teardown problem the opener describes is not what the smoke test has. Smoke test work entirely removed from scope.
- **F5** — Acknowledged: conftest.py contains no DB-session/factory fixtures. R1 step 3 expanded to discovery across nested conftests + DB-import patterns; R5 has three branches based on outcome.
- **F6** — Acknowledged: §2a and §2b are orthogonal, not coupled. Build Pack now scopes to §2b only; §2a becomes a separate Future_Tasks entry.
- **Scope**: from "FK fix + smoke test refactor + drop --ignore + 1–2 cascade tests" to "FK fix + 1 cascade test + Future_Tasks bookkeeping."
- **R5 (smoke test refactor)** removed entirely.
- **R6 (drop --ignore)** removed entirely.
- **R7 broad test** removed (we're not fixing the chain, just one link).
- **R0 step 6 (probe appraisals→projects)** removed (no chain test means no need to gate on it).
- **R0 step 7 (row count baseline)** removed (no smoke test teardown to assert against).
- **Audit log mitigations** removed (no test-time DELETE through the app).
- **R4 step 6 (bootstrap-from-0023)** kept (closes loop on chat-14 work).

**v3 → v4** (post-directory-listing audit):
- Confirmed: only one `conftest.py` exists at `/app/backend/tests/conftest.py` (no nested conftests). HTTP-only — provides `login_with_auto_enroll` and `plain_login` helpers, no DB fixtures.
- Confirmed: `/backend/tests/` contains DB-direct test files (`test_appraisal_governance.py`, `test_appraisals.py`, `test_audit_log.py`, etc.) which don't use the conftest's HTTP helpers, implying a direct DB-session pattern.
- §R1 step 3 tightened: agent now reads three specific template files in priority order (most likely → fallback) rather than searching broadly. Outcome (a) effectively ruled out by pre-paste audit; outcome (b) flagged as expected.

**v4 → v5** (post-Future_Tasks-sync audit):
- Surfaced gate-language deviation: live Future_Tasks §2 says "Hard gate: must be resolved before Prompt 2.4 (Budgets)" — referring to BOTH §2a and §2b. v4's narrowed scope only resolves §2b, technically leaving 2.4 still gated.
- Reconciliation chosen (per Rhys's Option 1 call): the gate language was written under a misdiagnosis of §2a as a teardown bug. Pre-paste audit revealed §2a is an architectural classification question, not a bug, and does not share infrastructure with Budgets. Therefore the gate logic for 2.4 collapses to §2b alone.
- §1 background expanded with explicit "Gate-language reconciliation" prose explaining this.
- §R6 step 1b (the new smoke-test Future_Tasks entry) expanded to record the reclassification verbatim — so the doc on disk is auditable, not just this Build Pack.
- No code or scope changes from v4. The agent does the same work; the documentation update is more thorough.

---

_End of Build Pack v5._
