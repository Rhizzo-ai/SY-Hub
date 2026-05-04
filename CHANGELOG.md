# CHANGELOG

## 2.3 Checkpoint 2 — Appraisal governance backend (2026-05-04)

### Migration 0022
- **New tables**: `appraisal_revisions`, `appraisal_scenarios`, `appraisal_decision_log`.
- **New enums**: `appraisal_revision_reason_enum` (8 values: GDV_Updated, Costs_Updated, Planning_Change, Finance_Terms_Change, Market_Change, Scope_Change, Error_Correction, Other); `decision_type_enum` (6 values: Go, No_Go, Defer, Request_Revision, Conditional_Go, Correction).
- **Triggers**:
  - `trg_scenarios_validate_parent` (BEFORE INSERT/UPDATE on `appraisal_scenarios`) — blocks any row whose `parent_scenario_appraisal_id` does not reference a Base-scenario appraisal.
  - `trg_decision_log_no_update` / `trg_decision_log_no_delete` (BEFORE UPDATE/DELETE on `appraisal_decision_log`) — append-only enforcement via `reject_decision_log_mutation()` plpgsql function. Mirrors the 1.4 `audit_log` immutability pattern.
- **Backfill**: one `Base` row inserted into `appraisal_scenarios` per distinct `appraisal_group_id` in `appraisals` (pre-2.3 row count = 0 → no-op). `DO` block asserts count = distinct group count; raises if mismatched.
- **System config seed**: `appraisal_decisions_required_threshold = 3` (value_type `Integer`, category `Appraisal`, `minimum_role_to_edit` = super_admin). Schema deviation from spec corrected — actual `system_config` columns are `config_key/config_value/value_type/category/description/is_system_locked/minimum_role_to_edit/default_value`; migration amended accordingly before apply.
- **Schema deviation resolved**: Build Pack specified generic `system_config (key, value, value_type, description)`; corrected INSERT against actual 1.7 schema. Extension `pgcrypto` verified present → `gen_random_uuid()` retained (matches 0019).

### New endpoints
- `POST /appraisals/{id}/new-version` — canonical Approved/Rejected → new Draft clone. Body `{revision_reason, summary_of_changes(min 10)}`. Permission `appraisals.edit`. Runs in single transaction: source.is_current=false (flush) → mark_superseded (Approved only) → clone_as_new_version → new.is_current=true (flush) → insert `appraisal_revisions` row → recompute. Atomic handover satisfies partial unique `uq_appraisals_current_per_project_scenario`.
- `GET /appraisals/{id}/revisions` — lineage for this (group, scenario) pair: appraisals by version_number ASC + revisions by to_version ASC.
- `GET /projects/{project_id}/revisions` — nested per-group per-scenario lineage.
- `POST /appraisals/{base_id}/scenarios` — spawn Upside/Downside/Sensitivity from the Base v1 anchor. Body `{scenario_label, scenario_description(min 10)}`. Permission `appraisals.edit`. Both Base and new scenario coexist with `is_current=true` (different (project, scenario) tuples).
- `GET /appraisal-groups/{group_id}/scenarios` — ordered metadata list (Base → Upside → Downside → Sensitivity).
- `GET /appraisal-groups/{group_id}/comparator` — absolute-values KPI comparator payload; frontend computes deltas.
- `POST /appraisals/{id}/decisions` — permission `appraisals.approve`. Rich validation: `is_current` gate, version match, rationale min 10, Conditional_Go↔conditions XOR, Correction↔correction_of_decision_id XOR, future-dated rejection via Europe/London zoneinfo, server-set `decision_maker_user_id` (client cannot proxy — payload `extra='forbid'`). Audit action `Appraisal.DecisionLog`.
- `GET /appraisals/{id}/decisions` — paginated list (limit 1–200, default 50) ordered by decision_date DESC, created_at DESC.
- `GET /projects/{project_id}/nudge` — nudge state for current Approved Base. Counts distinct deciders logging Go/No_Go/Defer (Conditional_Go/Request_Revision/Correction excluded). Threshold read fresh from system_config per call. Returns `{should_show, threshold, distinct_decision_makers, current_appraisal_id, actor_has_decided, message}`.

### Endpoint behaviour changes
- `/reopen` Approved-clone branch **removed**. Approved sources now toggle to `status='Reopened'` on the same row (no clone, no version bump, is_current unchanged) — same semantics as the Rejected branch. The clone behaviour moved entirely to `/new-version`.
- `/reopen` additional precondition: source must be `is_current=true`. Non-current (stale) versions return 400 `NOT_REOPENABLE`.
- Appraisal create endpoint now also auto-inserts an anchor row in `appraisal_scenarios` (scenario_label=`Base`) when the group is new. DB UNIQUE on (group_id, scenario_label) makes this no-op-safe.

### Services
- `app/services/appraisal_revisions.py` — `create_new_version` (single-transaction orchestrator) + `RevisionError`.
- `app/services/appraisal_scenarios.py` — `create_scenario`, `list_group_scenarios`, `get_group_comparator`, `_passes_hurdle`.
- `app/services/appraisal_decisions.py` — `log_decision` (full validation cascade), `list_for_appraisal`, `get_nudge_state` (Europe/London for today comparison).
- `app/services/appraisal_calc.py` — 9th pipeline step `_recompute_revision_deltas` appended; idempotent (no-op for v1-of-any-scenario rows). Deltas populate `delta_gdv`, `delta_total_cost`, `delta_profit` on every save of a `to` appraisal.

### Routers
- New file `app/routers/appraisal_governance.py` (module hygiene — `appraisals.py` already at ~1200 lines). Mounts under `/api/v1`, alongside the existing appraisals router.

### Tests
- **New file** `tests/test_appraisal_governance.py`: 44 tests across 7 classes (TestMigration0022, TestDecisionLogImmutability, TestScenarioParentTrigger, TestNewVersionEndpoint, TestReopenFinalForm, TestScenarios, TestDecisions, TestNudge). Covers H.2, H.4, H.5, H.6, H.7, H.8 from the Build Pack.
- **DB-layer trigger verification**: raw SQL UPDATE/DELETE against `appraisal_decision_log` raises; raw SQL INSERT with non-Base parent against `appraisal_scenarios` raises.
- **Modified test in `test_appraisals.py`**: `test_reopen_approved_creates_new_version` → `test_reopen_approved_returns_to_reopened` (asserts toggle, not clone; same id, same version_number, still current).
- **Modified test in `test_system_config.py`**: `test_seed_creates_38_keys` → `test_seed_creates_39_keys` (added nudge threshold row).
- Full suite **581/581 passing** (was 537 post-C1 → +44 new, 0 removed, 2 modified).

### Phase 1 spec deviations documented in CHANGELOG (not new, but carried forward)
- `scenario_appraisal_id` column present on `appraisal_scenarios` per spec (needed for "which scenario describes appraisal X" lookup).
- `correction_of_decision_id` is a real self-FK on `appraisal_decision_log`.
- `decision_maker_user_id` is server-set; no client proxy in 2.3.
- Decisions permitted only on `is_current=true` appraisals.
- No DB CHECK on `decision_date <= CURRENT_DATE` (CURRENT_DATE not IMMUTABLE in PG); enforced at service layer via `zoneinfo("Europe/London")`.
- Withdraw status restrictions: only Draft/Submitted/Reopened withdrawable.
- Reopen requires `is_current=true` source.
- One-of-each non-Base label per group (UNIQUE on `(appraisal_group_id, scenario_label)`).

### Schema state
- alembic head: `0022_appraisal_governance`
- Migration apply time: 0.44s on the dev pod.
- Backend tests: 581 passing (0 failing, 2 warnings).
- E2E: NOT RUN in C2 (deferred to C3 per spec sequencing).



## 2.3 Checkpoint 1 — Appraisal retrofit (2026-05-03)

### Migration
- **0021_appraisal_retrofit** applied. Renames `version`→`version_number`, `state`→`status`, `total_gdv`→`gdv_total`, `total_profit`→`profit_total` on `appraisals`. Adds `appraisal_group_id` (uuid NOT NULL, default uuid_generate-style Python `uuid.uuid4` on the model), `is_current` (bool NOT NULL DEFAULT false, backfilled to latest non-terminal version per project+scenario), `scenario` (`appraisal_scenario_enum` NOT NULL DEFAULT 'Base').
- Extends `appraisal_state` enum with `Withdrawn` and `Reopened`.
- Extends `audit_action` enum with `Appraisal.NewVersion`, `Appraisal.ScenarioCreate`, `Appraisal.DecisionLog`, `Appraisal.Withdraw`. Existing flat values (`Reopen`, `Submit`, etc.) untouched.
- Drops `uq_appraisals_project_version` UNIQUE CONSTRAINT (originally captured as constraint, not bare index — corrected from drafted migration). Creates `uq_appraisals_project_scenario_version` (UNIQUE composite) and `uq_appraisals_current_per_project_scenario` (partial UNIQUE WHERE is_current=true).

### Backend
- `is_editable` whitelist extended to include `Reopened` per Phase B.1.
- `ALLOWED_TRANSITIONS` extended for new states:
  - `Draft → {Submitted, Withdrawn}`
  - `Submitted → {Approved, Rejected, Draft, Withdrawn}`
  - `Approved → {Superseded, Reopened}`
  - `Rejected → {Reopened}` (was `{Draft}` in 2.2)
  - `Reopened → {Submitted, Withdrawn}` (new)
  - `Withdrawn`, `Superseded` terminal.
- `/appraisals/{id}/withdraw` rewritten:
  - Allowed sources: Draft, Submitted, Reopened (was Submitted-only).
  - Sets `status='Withdrawn'`, `is_current=false` (was `Draft`).
  - **Submitter-only restriction removed** — any user with `appraisals.edit` on the project may withdraw.
  - Audit action emitted: `Appraisal.Withdraw` (new namespaced enum value).
- `/appraisals/{id}/reopen` partial rewrite (option ii):
  - Rejected source: status now flips to `Reopened` (was `Draft`); rejection_reason cleared.
  - Approved source: legacy clone-into-new-Draft path retained for C1 with `# TODO 2.3 C2:` comment. C2 will move clone behaviour to a dedicated `/new-version` endpoint with revision_reason + summary_of_changes body and `appraisal_revisions` row write.
  - is_current handover ordering applied: source flipped false BEFORE new row flipped true (Phase B.2 atomicity, partial-unique safe).
- `clone_as_new_version` now propagates `appraisal_group_id` + `scenario` from source; new row starts with `is_current=false` (caller flips to true after demoting source).
- Appraisal create endpoint now writes `appraisal_group_id` (reusing existing for project, else minted), `scenario='Base'`, `is_current=true` (after demoting any prior current row for the same project+scenario).
- `next_version_for_project` now scenario-aware: scopes max version per (project, scenario).

### Phase 1 spec deviations
- **audit_action enum naming inconsistency.** New 2.3 values use `Appraisal.*` namespace per Phase 1 spec. Existing values (`Reopen`, `Submit`, `Approve`, etc.) remain flat. Decision: preserve spec naming for new values; do not retroactively rename existing values (would require data migration of `audit_log` rows). Inconsistency accepted.
- **audit_action_enum vs audit_action naming.** Phase 1 spec and v6 prompt reference `audit_action_enum`; actual PostgreSQL type is `audit_action`. Migration uses actual name. Confirmed via R0 `\dT+` capture.
- **Original unique was a CONSTRAINT, not bare index.** Drafted migration referenced `DROP INDEX`; R0 capture showed it as `UNIQUE CONSTRAINT, btree`. Corrected to use `ALTER TABLE … DROP CONSTRAINT IF EXISTS`. Downgrade uses `op.create_unique_constraint` to mirror.
- **`/reopen` mixed behaviour temporarily retained.** Phase 1 spec splits `/reopen` (status toggle only) from `/new-version` (clone + revision row) per Phase B.2. C1 retains the Approved-clone path under `/reopen` to keep 2.2 tests passing post-rename. C2 will introduce `/new-version` and remove the clone branch from `/reopen`. Tracked via `# TODO 2.3 C2:` comment in router.
- **Withdraw permission scope.** 2.2 restricted `/withdraw` to the appraisal's submitter; 2.3 broadens to any user holding `appraisals.edit` on the project. Spec-aligned.
- **Reopen target status.** 2.2 set Rejected→Draft on reopen; 2.3 sets Rejected→Reopened (new enum value). Spec-aligned.

### Frontend
- `STATE_BADGE` (in both `atoms.jsx` and the inline copy in `AppraisalsList.jsx`) extended with `Withdrawn` (muted gray italic) and `Reopened` (amber).
- `AppraisalPage.jsx`: all field reads renamed to `a.status`, `a.version_number`. Edit-gate broadened to Draft+Reopened. Withdraw CTA now visible to any `appraisals.edit` holder when status ∈ {Draft, Submitted, Reopened} (was: only submitter on Submitted). Approved-source Reopen button still labelled "Reopen (new version)" — temporary inconsistency; Reopen-for-Rejected says "Reopen for editing". New banners for Withdrawn and Reopened states.
- `AppraisalsList.jsx`: column "State" → "Status"; field reads renamed; testids carry the new `version_number` semantics (now `appraisal-row-${a.version_number}`, etc.).
- `SummaryTab.jsx` + `UnitsTab.jsx`: KPI tiles read `a.gdv_total`, `a.profit_total`.

### Bootstrap chicken-and-egg
- Recurred twice during 2.3 Step 0. Future_Tasks entry promoted from P1 to P0 (recurring). Mandatory fix before next Track 2 prompt. Original P1 entry retained as 1a for context.

### Schema state
- alembic head: `0021_appraisal_retrofit`
- ALTER TABLE lock duration: 0.45s (zero rows; recorded for future reference)
- Backend tests: **537 passing** (was 531; +6 new C1 retrofit acceptance tests in `TestRetrofit23C1`)
- E2E: not run in C1 (deferred to Checkpoint 3)

---
