# CHANGELOG

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
