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
2.4B-i frontend session — **FOUR** times in a single chat: at session
boot, then again after mid-session pod rebuilds at R4+R5 ship, lineage
follow-up, and R6 ship). Cadence ~1-2h on average.

**Symptom signature on a wiped pod:**
- `supervisorctl status` → `unix:///var/run/supervisor.sock no such file`
- `sudo service supervisor start` →
  `Error: Invalid user name postgres in section 'program:postgres'`
- `id postgres` → no such user
- `ls /usr/lib/postgresql/` → not found
- `ls /tmp/` → empty (anything saved to /tmp survives 0 recycles)
- `ls /app/` → intact (this layer is the durable repo)
- Preview URL → HTTP 502 (Cloudflare → no upstream)

**Durable recovery — committed to repo at `/app/scripts/provision_postgres.sh`.**
Run once after each recycle:

```bash
bash /app/scripts/provision_postgres.sh
```

Idempotent steps:
1. `apt-get install postgresql-16` if `/usr/lib/postgresql/16` missing
2. One-shot postgres → `CREATE ROLE syhomes` / `CREATE DATABASE syhomes`
   / `CREATE EXTENSION pgcrypto` (all `IF NOT EXISTS`)
3. Stop one-shot postgres
4. Write `/etc/supervisor/conf.d/supervisord_postgres.conf` if missing
5. `service supervisor start`
6. `bash /root/.emergent/on-restart.sh` → bootstrap rc=0 → backend up

**Total runtime budget:** 60-120s on a cold pod (apt-get dominates).

### Investigation: why doesn't `on-restart.sh` catch this?

Reviewed `/root/.emergent/on-restart.sh` 2026-05-12. Finding:

**The hook has no provision-postgres step.** Its contract assumes:
1. Postgres is installed (`/usr/lib/postgresql/16/`)
2. The `postgres` system user exists
3. The `[program:postgres]` supervisor block exists and is valid
4. Supervisord is already running

When ANY of those preconditions fail (the wipe-pattern observed in
Chat 17 fails ALL FOUR simultaneously), the failure chain is:

1. Container starts. `supervisord.conf` has `[program:postgres] user=postgres`.
2. `service supervisor start` → exits with
   `Invalid user name postgres in section 'program:postgres'`. No socket
   created. Supervisord is never alive.
3. Even if the platform invokes `on-restart.sh` on boot, the script
   would (a) fail to `sudo supervisorctl reread` (no socket), and (b)
   call `python -m app.bootstrap`, whose first real step
   `wait_for_postgres` polls for 60s and exits rc=2 (pg_unreachable)
   because no postgres is running.
4. Even if the hook ran through to step 7 (`supervisorctl start backend`),
   it would fail because the socket isn't there.

**Conclusion:** the bootstrap-fix-p0 contract covers "DB is empty or
out-of-migration" but does NOT cover "Postgres install missing" or
"`postgres` system user missing". The runbook for those failures lives
only in `backend/app/bootstrap.py`'s docstring lines 72-124 — not in
any runnable script (until 2e462f2 in this session shipped one).

### Track 8 / pre-launch hardening tasks

- **P0:** Wire `provision_postgres.sh` into `on-restart.sh` as a step 0
  precondition check. If `/usr/lib/postgresql/16` is missing OR `id postgres`
  fails, invoke the provision script before continuing. This collapses
  the manual recovery into the automatic boot hook.
- **P0:** Investigate WHY the Emergent pod recycles wipe Postgres but
  preserve `/app`. Is `/var/lib/postgresql` supposed to be on a
  persistent volume? If so, why isn't it? If not, document the
  fork-restart contract explicitly so future agents/operators know.
- **P1:** Self-heal the `[program:postgres]` supervisor block the same
  way `[program:backend]` is self-healed (template at
  `/app/scripts/supervisord_postgres.conf.template`, splice idempotently
  in `ensure_postgres_program_gated()` mirror of `ensure_backend_gated()`).
- **P1:** Move the install-postgres runbook from
  `backend/app/bootstrap.py` docstring into a top-level
  `/app/RUNBOOK.md` so it's discoverable without grepping source.
- **P2:** Consider a single shell-level health check exposed on the
  on-restart hook stderr — recent operators reported the symptom is
  hard to distinguish from "frontend dev server is still compiling".
- **Cost so far in this chat:** ~30 min of session time absorbed by
  4× manual recoveries. With `provision_postgres.sh` in repo the
  recovery is now ~90s per recycle, but it still interrupts operator
  flow. The P0 work above retires this fully.

### Phase 1 cleanup carry-forwards (untouched by 2.4A)
