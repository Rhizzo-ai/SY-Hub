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

---

## Phase 1 cleanup carry-forwards (untouched by 2.4A)
- `Project.tenant_id` column does not exist (Pattern α defensive
  `hasattr` guard depends on this). When tenant model is split out,
  add the column and delete the `hasattr` no-op.
- `appraisal_scenarios.parent_scenario_appraisal_id_fkey` ON DELETE
  RESTRICT (see CHANGELOG §pre-2.4-cleanup §5).
