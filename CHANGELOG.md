# CHANGELOG

## 2.3 Checkpoint 3 — Appraisal governance frontend + E2E (2026-05-04)

### New components (under `/app/frontend/src/components/appraisal/`)
- `RevisionTimeline.jsx` — vertical lineage of versions for one (group, scenario). Mounted in SummaryTab right column (3-col grid). HoverCard with Δ chips + reason + summary on non-v1 nodes (S8). Click to navigate (G6). j/k keyboard nav (S9). Skeleton + Empty states (S1, S7).
- `ScenariosPanel.jsx` — top-level tab between Finance and Summary; conditional on `appraisal.scenario === 'Base'`. 2×2 slot grid (Base, Upside, Downside, Sensitivity). Anchor detection (F1) hides create CTAs on non-Base-v1; banner with link to anchor v1 shown instead. CreateScenarioModal validates `scenario_description ≥ 10` (trim-then-length, F2). Cmd+Enter submits (S9).
- `ScenarioComparator.jsx` — sticky-first-column table (G5) with hover row+column highlight, sortable headers (Base pinned col 0; S4), framer-motion column slide-in (S6 + S10 reduced-motion). All deltas via `decimal.js` (F4). Favourable directions per metric (positive: GDV/Profit/RLV/PoC%/PoG%/Units; negative: Total cost; bool: passes_hurdle).
- `DecisionsTab.jsx` — top-level tab after Summary. 2/3 list + 1/3 form layout. Form gate matches server: `appraisals.approve` AND `is_current === true` (Decision C — R0 read confirmed server enforces only `is_current` + version match, not `status==Approved`). Optimistic UI on submit (S2): pending card with `aria-busy=true`, ~55% opacity, replaced on 201, removed on 400. `supporting_documents` OMITTED (Decision D). Date picker uses `formatInTimeZone('Europe/London')` for default + max (Decision E). Fires `nudge-refresh` event on success (F3).
- `NudgeBanner.jsx` — mounted on `ProjectDetail.jsx` ONLY (G2 — NOT on AppraisalsList). NOT dismissible (G1). Avatar stack (S3): coloured initials circles for deciders + dashed ghost slots for remaining; tooltip shows name + decision pill + relative date. CTA hidden when actor lacks `appraisals.approve` — replaced with "Awaiting director sign-off" + tooltip. Listens for `nudge-refresh` event (F3). Framer-motion slide-down/up on enter/exit (S6 + S10).
- `NewVersionModal.jsx` — header CTA on Approved + is_current. Form: revision_reason select (8 enum values) + summary_of_changes textarea (min 10 trim-checked). On 201, navigates to new appraisal id (F5).

### Page extensions
- `AppraisalPage.jsx`:
  - +2 tabs: `Scenarios` (Base only) between Finance & Summary; `Decisions` after Summary. 7 tabs on Base, 6 on non-Base.
  - Header buttons split (Decision B): `Reopen for editing` (secondary) on Approved/Rejected + is_current + `appraisals.edit`; `New version` (primary) on Approved + is_current + `appraisals.edit` (opens NewVersionModal).
  - Reopen no longer triggers a clone-and-redirect (the C2 backend made `/reopen` a pure toggle; navigation handler simplified accordingly).
  - `?tab=decisions` URL param handler: on mount, selects Decisions tab, scrolls log-form into view, then clears the param.
  - Tab control switched to controlled (`value` + `onValueChange`) to support deep-link.
- `SummaryTab.jsx`: KPI grid wrapped in 3-col layout; RevisionTimeline mounted in right column below RLV.
- `ProjectDetail.jsx`: `<NudgeBanner projectId={id} />` mounted at top of page (G2).

### Library extensions
- `src/lib/api.js`: +9 governance route wrappers — `fetchRevisions`, `fetchProjectRevisions`, `createNewVersion`, `fetchGroupScenarios`, `fetchComparator`, `createScenario`, `fetchDecisions`, `logDecision`, `fetchNudge`.
- `src/lib/appraisalMath.js`: `formatMoney(v, {decimals=0})` (Intl.NumberFormat en-GB, S5; accepts Decimal | number | string), `computeScenarioDelta(base, compare, field)` → Decimal (F4), `formatDelta(d, {currency, percent, dp, favourable})` → `{text, className, isZero}` with sign + colour mapping.

### New dependency
- `framer-motion@12.38.0` — animations gated on `useReducedMotion()` (S10) for tab switches, modal open/close, NudgeBanner enter/exit, decision card append, comparator column slide-in.

### R0 bootstrap recovery — 5th occurrence
The DB-wipe / chicken-and-egg issue (migrations need permissions seeded before they apply) fired again on this fork. Recovery procedure (seed → upgrade → re-seed → seed test users) ran cleanly in ~12s and brought DB to head 0022. **Recurrence count: 5/5** — strong signal that the P0 backlog item to fix bootstrap ordering is overdue. Logged in handoff §3.9 for the next planning round.

### Testing
- `testing_agent_v3_fork` iteration 10: PASS. Backend governance API smoke 6/6, frontend Playwright sweep across all C3 surfaces. All five locked decisions (A–E), F1–F5, G1–G6, and SOTA hooks (S1–S10) verified live against the public preview URL. No critical issues. Two minor design observations addressed in this commit:
  - DecisionsTab empty-state copy now keys off `showForm` instead of `appraisal.status` to avoid mixed-message UX when form is visible on a Draft.
  - RevisionTimeline empty branch dropped duplicated outer `data-testid` to leave a single empty-state hook for tooling.
- One peripheral 401 noted on ProjectDetail (notifications/feed call); does NOT block governance flows. Tracked for polish-pass.

### Backend tests
- 581/581 passing (unchanged from C2 baseline). C3 was pure frontend.

---

## 2.3 Checkpoint 2 — Appraisal governance backend (2026-05-04)

### Migration 0022
- **New tables**: `appraisal_revisions`, `appraisal_scenarios`, `appraisal_decision_log`.
- **New enums**: `appraisal_revision_reason_enum` (8 values: GDV_Updated, Costs_Updated, Planning_Change, Finance_Terms_Change, Market_Change, Scope_Change, Error_Correction, Other); `decision_type_enum` (6 values: Go, No_Go, Defer, Request_Revision, Conditional_Go, Correction).
- **Triggers**:
  - `trg_scenarios_validate_parent` (BEFORE INSERT/UPDATE on `appraisal_scenarios`) — blocks any row whose `parent_scenario_appraisal_id` does not reference a Base-scenario appraisal.
  - `trg_decision_log_no_update` / `trg_decision_log_no_delete` (BEFORE UPDATE/DELETE on `appraisal_decision_log`) — append-only enforcement via `reject_decision_log_mutation()` plpgsql function. Mirrors the 1.4 `audit_log` immutability pattern.
- **Backfill**: one `Base` row inserted into `appraisal_scenarios` per distinct `appraisal_group_id` in `appraisals` (pre-2.3 row count = 0 → no-op). `DO` block asserts count = distinct group count; raises if mismatched.
- **System config seed**: `appraisal_decisions_required_threshold = 3` (value_type `Integer`, category `Appraisal`, `minimum_role_to_edit` = super_admin). Schema deviation from spec corrected — actual `system_config` columns are `config_key/config_value/value_type/category/description/is_system_locked/minimum_role_to_edit/default_value`; migration amended accordingly before apply.
- **System_config schema deviation — exact divergence from Build Pack §C.9**:
  - Build Pack assumed: `(key, value, value_type, description)` — 4 columns.
  - Actual 1.7 table (migration 0015): 13 columns. Business-critical deltas:
    - `key` → `config_key` | `value` → `config_value` (rename).
    - `value_type` enum labels are `String|Integer|Decimal|Boolean|JSON|Date` (spec used `int` — would fail enum cast).
    - `category` (NOT NULL, `system_config_category` enum) — absent in spec.
    - `description` is NOT NULL — spec implied optional.
    - `is_system_locked` (NOT NULL boolean) — absent in spec.
    - `minimum_role_to_edit` (NOT NULL FK → `roles.id`) — absent in spec.
    - `default_value` (NOT NULL text) — absent in spec.
  - Migration 0022 §C.9 INSERT corrected before apply: `value_type='Integer'::system_config_value_type`, `category='Appraisal'::system_config_category`, `minimum_role_to_edit=(SELECT id FROM roles WHERE code='super_admin')`, `default_value='3'`, and replaced `ON CONFLICT (key) DO NOTHING` with `WHERE NOT EXISTS (...)` (no UNIQUE on bare `key`; UNIQUE is on `config_key`). Fresh-DB bootstrap reads the corrected migration verbatim — no re-divergence possible on rebuild.
- **Extension pre-flight**: `pgcrypto` verified present before apply → `gen_random_uuid()` retained in drafted migration (matches 0019). No fallback to `uuid-ossp::uuid_generate_v4()` needed.

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
- **New file** `tests/test_appraisal_governance.py`: 44 tests across 8 classes (TestMigration0022, TestDecisionLogImmutability, TestScenarioParentTrigger, TestNewVersionEndpoint, TestReopenFinalForm, TestScenarios, TestDecisions, TestNudge). Covers H.2, H.4, H.5, H.6, H.7, H.8 from the Build Pack.
- **Deviation from Build Pack §R7.1–7.7 (test file layout)**: spec recommended six separate files (`test_migration_0022.py`, `test_appraisal_revisions.py`, `test_appraisal_reopen_withdraw.py`, `test_appraisal_scenarios.py`, `test_appraisal_decisions.py`, `test_appraisal_nudge.py`). Consolidated into a single `test_appraisal_governance.py` with 8 classes (one per functional area + two DB-layer trigger classes). Treated spec §H layout as granularity guidance, not a hard split. If a future prompt wants per-resource files, a one-shot class→file split is trivial.
- **Deviation from Build Pack §R7.1 (TestRetrofit23C1 relocation)**: spec recommended moving C1's `TestRetrofit23C1` from `test_appraisals.py` to `tests/test_retrofit_0021.py`. Deferred — class left in place. Move was marked "optional, recommended" in spec; all 6 C1 acceptance assertions still run as part of `test_appraisals.py`'s module-scoped appraisal cleanup.
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
