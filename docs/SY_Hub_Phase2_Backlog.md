# SY Hub — Phase 2 Backlog (Prompt 2.4A deferrals)

Generated 2026-05-09 from Chat 16 / Prompt 2.4A `Build Pack v3` execution.
Each item below was knowingly deferred during 2.4A execution per locked
decisions or the §R0 STOP-and-resplit triggers. Owner: Chat 17+.

---

## 1. AppraisalUnit aggregation in `create_from_appraisal`
- **Status**: deferred (locked decision C1).
- **Why**: `AppraisalUnit` model carries no `cost_code_id` linkage today.
  Phase 1 spec line 2861 ("aggregated per cost code if applicable") permits
  skip when the linkage is absent.
- **Acceptance**: when `AppraisalUnit` gains a `cost_code_id` column, extend
  the merge map in `app/services/budgets.py::create_from_appraisal` to fold
  unit-aggregate amounts into the `(cost_code_id, subcategory_id, entity_id)`
  bucket — the merge framework is already in place.
- **Test pointers**: Build Pack §R5 test #8
  `test_create_handles_appraisal_units_aggregation` and #11
  `test_create_from_appraisal_merges_cost_line_and_unit_aggregation` (B11/T21).

## 2. Per-line `entity_id` sourcing
- **Status**: deferred (locked decision D1).
- **Why**: `Project` has only `primary_entity_id`; multi-entity projects
  aren't represented in 2.4A. All budget_lines today inherit the project's
  primary entity.
- **Acceptance**: when projects support multiple entities, source
  `budget_line.entity_id` from the appraisal cost line / unit row rather
  than from `project.primary_entity_id`.

## 3. Actuals service (Prompt 2.5)
- **Status**: deferred — explicit out-of-scope per Build Pack `Out of scope`.
- **Acceptance**: `actuals_to_date`, `last_actual_posted_at`, and
  `actuals_this_period` cache columns wired to a real service.

## 4. Commitments service (Prompt 2.5)
- **Status**: deferred — explicit out-of-scope.
- **Acceptance**: `committed_value`, `invoiced_against_commitment`,
  `committed_not_invoiced` fed by a commitments service.

## 5. Budget changes (Prompt 2.6)
- **Status**: deferred.
- **Acceptance**: `approved_changes` populated by an approval-flow service;
  `current_budget = original_budget + approved_changes` keeps holding.

## 6. Cash-flow `budget_line_periods` table
- **Status**: deferred (locked decision 3 / Phase 2 detail §2.4 line 104
  is a known erratum in the spec).
- **Acceptance**: separate prompt; new table + monthly time-phasing service.

## 7. `linked_programme_task_id` FK constraint (Prompt 3.2)
- **Status**: column landed nullable, no FK. Per spec line 2781.
- **Acceptance**: add the FK to `programme_tasks.id` as part of Prompt 3.2.

## 8. Xero hooks (Track 6)
- **Status**: deferred.
- **Acceptance**: budget aggregates → Xero tracking categories.

## 9. `requires_attention` scheduler infra
- **Status**: endpoint-only this prompt (locked decision 10).
- **Acceptance**: APScheduler-driven sweep replicating the body of
  `scan_requires_attention`. Already wired to support this — just needs
  scheduler config + cron.
- **Also**: clauses 2 (stale actuals) and 3 (programme task complete +
  under-billed) — clause 2 unblocks once actuals lands; clause 3 once
  Prompt 3.2 ships the programme task FK.

## 10. `SystemConfig` variance-threshold columns
- **Status**: in-code defaults shipped (5% amber / 15% red). Per locked
  decision 11.
- **Acceptance**: `system_config.budget_variance_amber_threshold_pct` and
  `..._red_threshold_pct` columns land in a future migration; service
  helper `_load_variance_thresholds` already preferentially reads from
  SystemConfig (with `getattr` fallback to defaults), so no service
  change is required when the columns are added.

## 11. Idempotency keys on `/from-appraisal` and `/new-version`
- **Status**: deferred (locked decision 12).
- **Acceptance**: `Idempotency-Key` header + retry-safe response cache.

## 12. SOX-style separation review for `budgets.{edit, admin, approve}`
- **Status**: locked decision 9 — flagged for review with MD/Louise.
- **Why**: today PM can `activate` budgets they themselves created.
  Phase 1 spec is silent on author-cannot-activate; flagged for a
  business-process discussion not done silently in code.

## 13. HTTP-layer tenant isolation tests for budgets endpoints
- **Status**: deferred — Phase 1 `get_current_tenant_id` is single-tenant
  by design (always resolves to default tenant from email lookup).
- **Why**: Build Pack §R5 tests #15–#19 demand HTTP-layer cross-tenant
  assertions. Phase 1 cookies-only login cannot route a session to a
  non-default tenant, so `t2-admin@example.test` login returns 401 even
  though the user row exists. Service-layer tests #15 + #16 ship as a
  proxy (`TestTenantIsolation::test_cross_tenant_load_returns_404` and
  `::test_cross_tenant_list_excludes`); #17, #18, #19, #68 cannot be
  written until login is multi-tenant.
- **Acceptance**: when Prompt X.Y lands a per-request tenant resolver
  (subdomain / header / org-id JWT claim), add the four HTTP-layer tests
  for `from-appraisal`, `PATCH /budget-lines`, `POST/DELETE
  /budget-line-items`, asserting 404 (not 403 — don't leak existence)
  for cross-tenant calls.
- **Documented in**: `tests/test_budgets.py` `class TestTenantIsolation`
  docstring; `/app/CHANGELOG.md` §2.4A "Deviations" block;
  `/app/docs/chat-summaries/chat-16-closing.md` §1.

## 14. Coverage debt — 23 skipped Build Pack §R5 tests
- **Status**: acknowledged debt. Documented in
  `/app/docs/chat-summaries/chat-16-closing.md` §1d (Bucket C).
- **Why**: shipped 44 tests; Build Pack target was ≥63. The gap splits
  into 3 deferred-by-decision (#8, #51, #77 — already in entries 1, 10,
  9 of this backlog), 4 deferred-by-tenant-limitation (#17–#19, #68 —
  entry 13 above), and 23 genuine coverage gaps.
- **The 23 by Build Pack number**:
  - **Create-from-appraisal**: #6 (total cross-check), #10 (zero-cost-lines)
  - **Concurrency**: #14 (concurrent lock SELECT FOR UPDATE serialisation)
  - **State machine**: #25 (unlock from Active rejected),
    #26 (close from each non-terminal — only Active covered),
    #29 (new-version "current → original" mapping explicit assertion),
    #30 (programme task link carried), #31 (items NOT carried),
    #33 + #34 (in-memory line state consistent with DB after lock/unlock —
    `synchronize_session='fetch'` invariant)
  - **Audit**: #39 (new-version audit asserts `superseded_id` metadata)
  - **FTC math**: #41 (manual), #45 + #46 (percentage_complete + fallback),
    #49 (variance_pct=0 when current_budget=0), #53 (overflow handling)
  - **Line edits**: #55 (locked rejects description),
    #60 + #61 (Closed / Superseded parent → 409 on patch)
  - **Items**: #64 (relationship collection populated post-create),
    #65 (warns-not-blocks), #66 (delete-line cascades), #67 partial
    (terminal beyond Locked)
  - **Header rollup**: #70 (`summary_refreshed_at` advances)
  - **Permissions**: #72 (regression — `budgets.approve` still present),
    #74 (PM does NOT have `budgets.admin`)
  - **Scan**: #76 (Red-variance flagged after scan), #78 (clears when
    no longer matching)
  - **HTTP**: #81 (site_manager 403 on create), #84 (finance session
    sees sensitive), #85 (PM lock OK), #87 (director unlock specifically),
    #89 (list filters by `is_current`)
- **Acceptance**: small follow-up prompt that ships these as additional
  test functions in `tests/test_budgets.py` only — no production code
  changes anticipated. Most are 5–10 lines apiece. Suggested target:
  bring shipped function count to ≥67 to clear Build Pack v3
  "≥65 functions" gate retroactively.

---

## Phase 1 cleanup carry-forwards (untouched by 2.4A)
- `Project.tenant_id` column does not exist (Pattern α defensive
  `hasattr` guard depends on this). When tenant model is split out,
  add the column and delete the `hasattr` no-op.
- `appraisal_scenarios.parent_scenario_appraisal_id_fkey` ON DELETE
  RESTRICT (see CHANGELOG §pre-2.4-cleanup §5).

---

## Sandbox / pod-runtime stability (Track 8 — pre-launch hardening)

### Postgres + supervisor wiring does not survive Emergent fork restarts
Observed across multiple sessions (Chat 16.5 fresh-fork; Chat 17
2.4B-i frontend session — twice in a single chat: once at session
boot, once after a mid-session container rebuild that wiped
`/var/lib/postgresql/`, `/usr/lib/postgresql/`, `/tmp/*`, and the
`postgres` system user but left everything under `/app` intact).

**Symptom signature on a wiped pod:**
- `supervisorctl status` → `unix:///var/run/supervisor.sock no such file`
- `sudo service supervisor start` →
  `Error: Invalid user name postgres in section 'program:postgres'`
- `id postgres` → no such user
- `ls /usr/lib/postgresql/` → not found
- Preview URL → HTTP 502 (nginx ingress can't reach frontend)

**Expected per bootstrap-fix-p0 contract:**
- `/root/.emergent/on-restart.sh` should fire on container start,
  call `python -m app.bootstrap`, which is supposed to recover the
  DB to a known-good state. Self-heal supervisor config exists for
  the `[program:backend]` block but NOT for `[program:postgres]`.
- The runbook (PostgreSQL install + role/DB provisioning + supervisor
  wiring) lives only in `backend/app/bootstrap.py`'s docstring
  (lines 72–124), not in a runnable script. The bootstrap orchestrator
  itself assumes Postgres is already installed and running — it does
  not provision it.

**Manual recovery (used twice in chat 17):**
1. Reinstall Postgres 16 via PGDG apt repo (see bootstrap.py:77-85).
2. Recreate the `syhomes` role + DB + pgcrypto extension (bootstrap.py:88-93).
3. Write `/etc/supervisor/conf.d/supervisord_postgres.conf` from the
   template in bootstrap.py:96-110.
4. `sudo service supervisor start` → supervisord spawns all programs.
5. `bash /root/.emergent/on-restart.sh` → bootstrap rc=0, backend up.

**Track 8 / pre-launch hardening tasks:**
- Audit which container-state survives an Emergent pod restart vs.
  which doesn't. Confirm whether `/var/lib/postgresql/16/main` is
  expected to be ephemeral or if it should be in a persistent volume.
- Lift the docstring runbook into a runnable provisioning script
  (e.g. `/app/scripts/provision_postgres.sh`) that the bootstrap
  orchestrator can invoke when it detects the install is missing,
  rather than exiting rc=2 (pg_unreachable) and waiting for an
  operator to read the docstring.
- Extend `on-restart.sh` to detect the "postgres not installed"
  pre-condition and bail with a distinct exit code + actionable
  log line ("provision via `bash /app/scripts/provision_postgres.sh`")
  rather than letting supervisor refuse to start.
- Consider whether the `[program:postgres]` block should be in the
  same self-healing template pattern as `[program:backend]` (see
  `/app/scripts/README.md` ⇒ Self-healing template section).
- Document the recovery flow in a top-level `/app/RUNBOOK.md` so
  any operator (human or fork agent) can find it without grepping
  backend source docstrings.
- Cost: recurring 5–10 min interruption every time a fork is reset
  or container rebuilt. Not a launch blocker — but the next chat
  that pre-launch hardens (Track 8) should retire this manual
  workaround.
