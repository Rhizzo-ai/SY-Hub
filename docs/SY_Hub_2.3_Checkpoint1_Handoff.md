# SY Homes Hub — Prompt 2.3 Checkpoint 1 Handoff

> **Forked at:** end of session that completed Prompt 2.2 frontend refactor + ran Step 0 for 2.3 retrofit.
> **Reason for fork:** Checkpoint 1 alone (0021 retrofit migration + code rename + endpoint behaviour split + ~40 test updates) realistically requires 150–200k tokens with quality. The originating session ended with ~125k remaining — insufficient for a clean retrofit. User explicitly approved fork to preserve quality gates.
> **Next agent's mandate:** Execute Checkpoint 1 ONLY. Stop and report after. Do NOT begin Checkpoint 2 in the same session.

---

## 1. Step 0 captures (verbatim — performed in originating session)

### 1.1 Baseline & environment

| Capture | Value |
|---|---|
| **pytest baseline** | **531 passed**, 2 warnings, ~65s — confirmed twice in originating session after DB recoveries |
| **alembic current** | `0020_permission_action_submit` |
| **PostgreSQL version** | **15.16** (Debian 15.16-0+deb12u1) on aarch64-linux. → MUST use `with op.get_context().autocommit_block(): ...` for `ALTER TYPE ... ADD VALUE` because added enum values cannot be USED in the same transaction (PG 12+ rule). |
| **`/app/CHANGELOG.md`** | **DOES NOT EXIST.** Repo has no changelog file. Project has been tracking changes via `/app/memory/PRD.md` only. The 2.3 prompt's instruction to "read `CHANGELOG.md`" cannot be satisfied; PRD.md is the source of truth for what 2.2 shipped. |
| **`/app/docs/`** | Contains only `SY_Homes_Future_Tasks.md`. The Phase 1 brief paths referenced in the 2.3 prompt (`/docs/SY_Homes_Phase2_Brief_T2_T3_Detail.md` and `/docs/SY_Homes_Emergent_Brief_Phase1.md`) **do not exist** in the repo. The 2.3 v6 prompt inlined the Phase 1 spec content for this reason. |

### 1.2 `appraisals` table — current 2.2 column inventory

Confirmed via `\d appraisals`:

| Column | Type | 2.3 spec name |
|---|---|---|
| `id` | `uuid` | (unchanged) |
| `project_id` | `uuid` | (unchanged) |
| `version` | `int` | **→ rename to `version_number`** |
| `previous_version_id` | `uuid` | (unchanged) |
| `name` | `varchar` | (unchanged) |
| `state` | `appraisal_state` enum | **→ rename to `status`** |
| `reference_date` | `date` | (unchanged) |
| `land_purchase_price` | `numeric` | (unchanged) |
| `sdlt_category` | `varchar` | (unchanged) |
| `developer_relief` | `boolean` | (unchanged) |
| `contingency_pct` | `numeric` | (unchanged) |
| `target_profit_on_cost_pct` | `numeric` | (unchanged) |
| `target_profit_on_gdv_pct` | `numeric` | (unchanged) |
| `project_duration_months` | `int` | (unchanged) |
| `total_gdv` | `numeric` | **→ rename to `gdv_total`** |
| `total_acquisition_cost` | `numeric` | (unchanged) |
| `total_build_cost` | `numeric` | (unchanged) |
| `total_professional_fees` | `numeric` | (unchanged) |
| `total_statutory_cost` | `numeric` | (unchanged) |
| `total_finance_cost` | `numeric` | (unchanged) |
| `total_contingency` | `numeric` | (unchanged) |
| `total_sales_cost` | `numeric` | (unchanged) |
| `total_other_cost` | `numeric` | (unchanged) |
| `total_cost` | `numeric` | (unchanged — same name in spec) |
| `total_profit` | `numeric` | **→ rename to `profit_total`** |
| `profit_on_cost_pct` | `numeric` | (unchanged) |
| `profit_on_gdv_pct` | `numeric` | (unchanged) |
| `rlv_enabled, rlv_target_basis, rlv_target_value, rlv_computed_land_value, rlv_iterations, rlv_converged, rlv_computed_at` | various | (unchanged) |
| `submitted_by_user_id, submitted_at, approved_by_user_id, approved_at, rejection_reason, notes, computation_metadata, is_stale, created_by_user_id, created_at, updated_at` | various | (unchanged) |
| **`appraisal_group_id`** | — | **TO BE ADDED in 0021** |
| **`is_current`** | — | **TO BE ADDED in 0021** |
| **`scenario`** | — | **TO BE ADDED in 0021 (after enum exists)** |

### 1.3 Enums

| Enum | Current values | 2.3 changes |
|---|---|---|
| `appraisal_state` | `Draft, Submitted, Approved, Rejected, Superseded` | **ADD VALUE `Withdrawn`, `Reopened`** (autocommit block) |
| `audit_action` | `Create, Update, Delete, Approve, Reject, Reopen, Login, Logout, Export, Permission_Change, Stage_Change, Status_Change, Seed_Run, Submit` (14 values) | **ADD VALUE `Appraisal.NewVersion`, `Appraisal.ScenarioCreate`, `Appraisal.DecisionLog`, `Appraisal.Withdraw`** (autocommit block). Note: existing `Reopen` (no `Appraisal.` prefix) is reused; do NOT add `Appraisal.Reopen` separately. **Decision needed by next agent**: keep flat audit names (`Reopen`, `Submit`, `Withdraw`) or namespace new ones (`Appraisal.NewVersion`, `Appraisal.ScenarioCreate`, `Appraisal.DecisionLog`). Spec uses `Appraisal.*` prefix for new ones — recommend keeping spec naming and noting the inconsistency in CHANGELOG. |
| `permission_action` | includes `submit`, `view_financials` (added by 0020) | (unchanged in 0021) |
| `appraisal_revision_reason_enum` | — | **CREATE in 0022** |
| `decision_type_enum` | — | **CREATE in 0022** |
| `appraisal_scenario_enum` | — | **CREATE in 0021** with values `Base, Upside, Downside, Sensitivity` |

### 1.4 Existing indexes on `appraisals`

```
appraisals_pkey                — UNIQUE (id) — keep
uq_appraisals_project_version  — UNIQUE (project_id, version) — DROP in 0021 step A.8
ix_appraisals_project          — INDEX (project_id) — keep
ix_appraisals_state            — INDEX (state) — keep (state→status, index name retained)
ix_appraisals_project_state    — INDEX (project_id, state) — keep (compound)
```

To create in 0021 step A.8:
- `uq_appraisals_project_scenario_version` — UNIQUE (project_id, scenario, version_number)
- `uq_appraisals_current_per_project_scenario` — UNIQUE (project_id, scenario) WHERE is_current = true

### 1.5 Permissions

```
appraisals.approve         ✓ seeded
appraisals.create          ✓ seeded
appraisals.delete          ✓ seeded
appraisals.edit            ✓ seeded
appraisals.reopen          ✓ seeded
appraisals.submit          ✓ seeded (added by 0020)
appraisals.view            ✓ seeded
appraisals.view_financials ✓ seeded (added by 0020)
appraisals.view_sensitive  ✓ seeded
```

**No new permissions in 2.3.** All endpoints map to existing codes per Phase G.

### 1.6 Existing endpoint behaviour (must split)

Located at `/app/backend/app/routers/appraisals.py`:

- **`POST /appraisals/{id}/withdraw`** — line 821. Submitter-only check (current actor must equal `submitted_by_user_id`). Sets `state='Draft'` (not 'Withdrawn'). Used to "pull back" Submitted appraisals. **WILL BE REPLACED** by 2.3 spec: source must be Draft/Submitted/Reopened, sets `status='Withdrawn'`, `is_current=false`, no submitter restriction (any user with `appraisals.edit` on the project can withdraw — per spec).

- **`POST /appraisals/{id}/reopen`** — line 852. Mixed behaviour:
  - Approved source → calls `clone_as_new_version` from `app/services/appraisal_versioning.py`, marks source as `Superseded`, returns the new clone (Draft, version+1).
  - Rejected source → toggles `state='Draft'` on same row, clears `rejection_reason`.
  - Other states → 409 error.

  **WILL BE SPLIT** in 2.3: `/reopen` becomes pure status toggle to `Reopened` (Approved/Rejected only, must be `is_current=true`). The clone-on-Approved behaviour moves to a new `POST /appraisals/{id}/new-version` endpoint that requires `revision_reason` + `summary_of_changes` body fields and writes an `appraisal_revisions` row.

- **`POST /appraisals/{id}/submit, /approve, /reject`** — unchanged by 2.3.

### 1.7 Edit-gate logic

- File: `/app/backend/app/services/appraisal_versioning.py`
- Function: `is_editable(appraisal: Appraisal) -> bool` — returns `True` only when `appraisal.state == "Draft"`.
- Helper used by `_ensure_editable` in router (line 372) which raises 409 if `is_editable` returns False.

Used at router lines: 596, 662, 685, 919, 949, 982, 1014.

**2.3 retrofit MUST update `is_editable`** to also return True for `status == 'Reopened'`. Per Phase B.1 of the v6 prompt: "Reopened must be in the whitelist post-retrofit."

### 1.8 Audit log immutability mechanism

- **Pattern**: PostgreSQL trigger (NOT SQLAlchemy event listener).
- File: `/app/backend/alembic/versions/0006_audit_log.py`, `0007_audit_trigger_cascade.py`, `0010_audit_trigger_comment.py`.
- Function: `audit_log_no_modify()` — raises on UPDATE/DELETE.
- Trigger: `audit_log_no_modify_trg` (or similar) BEFORE UPDATE OR DELETE on `audit_log`.

**2.3 must replicate this exact pattern** for `appraisal_decision_log` (Phase C.8). Function name: `reject_decision_log_mutation()`. Triggers: `trg_decision_log_no_update`, `trg_decision_log_no_delete`. Function `LANGUAGE plpgsql` only — no IMMUTABLE marker.

### 1.9 Frontend file inventory (uses renamed fields)

Confirmed via grep for `total_gdv|total_profit|\.state|\.version`:

```
/app/frontend/src/pages/AppraisalPage.jsx              (shell — uses a.state, a.version, a.total_gdv etc.)
/app/frontend/src/pages/AppraisalsList.jsx             (list page — STATE_BADGE keyed on state values; renders total_gdv, profit_on_cost_pct)
/app/frontend/src/components/appraisal/UnitsTab.jsx    (uses a.total_gdv for server-GDV KPI; live-vs-saved comparison)
/app/frontend/src/components/appraisal/SummaryTab.jsx  (KPI tiles: total_gdv, total_cost, total_profit, profit_on_cost_pct, profit_on_gdv_pct)
/app/frontend/src/components/appraisal/HeaderTab.jsx   (form state, save handler — uses .name etc.; check for state usages)
/app/frontend/src/components/appraisal/CostsTab.jsx    (check)
/app/frontend/src/components/appraisal/FinanceTab.jsx  (check)
/app/frontend/src/components/appraisal/atoms.jsx       (STATE_BADGE keyed on state values: Draft, Submitted, Approved, Rejected, Superseded — needs Withdrawn + Reopened added)
/app/frontend/src/pages/ProjectDetail.jsx              (Appraisals tab link added in 2.2 — verify no state/version field reads)
```

**Frontend retrofit pass MUST update**:
- All field reads: `a.version → a.version_number`, `a.state → a.status`, `a.total_gdv → a.gdv_total`, `a.total_profit → a.profit_total`.
- `STATE_BADGE` in `atoms.jsx` adds `Withdrawn` (muted gray italic) and `Reopened` (amber) per Phase E.2 palette.
- `AppraisalPage` shell: state-machine CTAs at the top (Submit/Approve/Reject/Withdraw/Reopen) use `a.state` → `a.status`. Withdraw button currently says "Withdraw" but only visible when submitter — per 2.3 it should be visible when current user has `appraisals.edit` AND status in {Draft, Submitted, Reopened}.
- `AppraisalsList`: column headers + sort keys may reference `.version`.
- LIVE math helper `appraisalMath.js` reads `a.total_gdv` for the server-vs-live diff in UnitsTab.

### 1.10 Pre-retrofit data state

```
SELECT COUNT(*) FROM appraisals; → 0
SELECT COUNT(DISTINCT project_id) FROM appraisals; → 0
```

**No production data — DB was rebuilt twice during originating session due to bootstrap chicken-and-egg recurrence.** Backfill steps will run against zero rows; their assertions (`expected % rows`) all degenerate to 0. Tests in checkpoint must seed appraisal rows BEFORE asserting backfill semantics, or run separate fixture-DB tests.

---

## 2. Verbatim v6 2.3 prompt

> The full v6 prompt is approximately 1500 lines. Rather than reproducing inline (token cost), it is preserved in the **previous user message** in this conversation thread. The next agent will receive that message verbatim as part of the handoff summary.
>
> **Critical anchors** the next agent must NOT lose track of:
>
> - **Three checkpoints**: (1) retrofit 0021 + code rename + test updates + endpoint split; (2) new schema 0022 + services + new endpoints + new tests; (3) frontend + E2E.
> - **Stop after each checkpoint and wait for go-ahead** before the next.
> - **Test count target post-2.3**: 575–600 backend, ≥26 E2E.
> - **Phase 1 spec deviations** must be CHANGELOG-documented (see prompt acceptance criteria).
> - **Endpoint behaviour matrix** in Phase B.2 of the v6 prompt is THE source of truth for /reopen vs /new-version vs /withdraw semantics.
> - **`is_current` handover atomicity** in Phase B.2: source UPDATE precedes new INSERT, else partial unique index violates.

---

## 3. Restart plan for Checkpoint 1 (literal sequence)

Execute in order. Verify after each major step.

### Step R0 — Recover DB if bootstrapped wiped it again

Check first: `cd /app/backend && set -a && source .env && set +a && alembic current`. If not at `0020_permission_action_submit`, run the documented bootstrap recovery:

```bash
cd /app/backend && set -a && source .env && set +a && python -c "
import sys; sys.path.insert(0,'.')
import app.seed_rbac as sr
orig = sr.PERMISSION_CATALOGUE
sr.PERMISSION_CATALOGUE = [p for p in orig if p[0] not in ('appraisals.submit','appraisals.view_financials')]
from app.seed import seed
seed()
sr.seed_rbac()
"
python scripts/seed_test_users.py
alembic upgrade head
python -c "
import sys; sys.path.insert(0,'.')
from app.seed_rbac import seed_rbac
seed_rbac()
"
sudo supervisorctl restart backend
```

Then verify `pytest --tb=no` reports **531 passed**.

### Step R1 — Write migration 0021 (`alembic revision -m "appraisal_retrofit"`)

File: `/app/backend/alembic/versions/0021_appraisal_retrofit.py`. Operations in order, per Phase A of the v6 prompt:

1. **A.1** — `with op.get_context().autocommit_block(): ALTER TYPE appraisal_state ADD VALUE IF NOT EXISTS 'Withdrawn'; ADD VALUE IF NOT EXISTS 'Reopened'`. Required because PG 15.16 cannot use new enum values in same transaction.
2. **A.2** — Same autocommit_block: ADD VALUE for `Appraisal.NewVersion`, `Appraisal.ScenarioCreate`, `Appraisal.DecisionLog`, `Appraisal.Withdraw` to `audit_action` enum. Note enum is named `audit_action`, NOT `audit_action_enum` as the prompt suggests — verify in pg_type.
3. **A.3** — Renames: `RENAME COLUMN version TO version_number`, `state TO status`, `total_gdv TO gdv_total`, `total_profit TO profit_total`. `total_cost` unchanged.
4. **A.4** — Add `appraisal_group_id uuid NULL`, `is_current boolean NOT NULL DEFAULT false`. (Scenario column waits for enum in A.6.)
5. **A.5** — Backfill `appraisal_group_id`: one UUID per `project_id`. DO block raises if any NULL remains. Then `ALTER COLUMN ... SET NOT NULL`.
6. **A.6** — `CREATE TYPE appraisal_scenario_enum AS ENUM ('Base','Upside','Downside','Sensitivity'); ALTER TABLE appraisals ADD COLUMN scenario appraisal_scenario_enum NOT NULL DEFAULT 'Base'`.
7. **A.7** — Backfill `is_current=true` for the latest `version_number` per `(project_id, scenario)` where status NOT IN (Superseded, Withdrawn). DO block raises if any (project, scenario) has more than one current.
8. **A.8** — `DROP INDEX uq_appraisals_project_version; CREATE UNIQUE INDEX uq_appraisals_project_scenario_version ON appraisals (project_id, scenario, version_number); CREATE UNIQUE INDEX uq_appraisals_current_per_project_scenario ON appraisals (project_id, scenario) WHERE is_current = true`.
9. **A.9** — Downgrade reverses 1–8 (note: enum value removal is no-op with comment).

### Step R2 — Apply 0021 + sanity check

```bash
cd /app/backend && set -a && source .env && set +a && alembic upgrade head
PGPASSWORD=syhomes_dev psql -U syhomes -h localhost -d syhomes -c "\d appraisals" | grep -E "version_number|status|gdv_total|profit_total|is_current|scenario|appraisal_group_id"
```

All 7 columns/renames must appear.

### Step R3 — Backend code rename pass

Files to edit (search-replace `version`→`version_number`, etc., **ONLY where they reference the appraisals model**, NOT generic Python `version` strings):

```
/app/backend/app/models/appraisals.py              — ORM column attrs + relationships
/app/backend/app/routers/appraisals.py             — ~40 references; serialisers, validators, queries
/app/backend/app/services/appraisal_calc.py        — recompute pipeline
/app/backend/app/services/appraisal_versioning.py  — clone + state machine + is_editable
/app/backend/tests/test_appraisals.py              — 40 tests; updated assertions, new endpoint targets
/app/backend/app/seed.py                           — if it references appraisal columns (unlikely)
```

**Critical attention points:**
- `Appraisal.state == "Draft"` checks → `Appraisal.status == "Draft"` AND add `or status == "Reopened"` for `is_editable`.
- Field selection in `_serialise_header` and `_serialise_full` in router: keys returned to frontend MUST use new names. Frontend will be updated in matching pass.
- `ALLOWED_TRANSITIONS` in versioning service:
  - `"Draft": {"Submitted"}` — unchanged
  - `"Submitted": {"Approved", "Rejected", "Draft"}` — keep but also add `{"Withdrawn"}`. Note: spec says Withdraw allowed from `(Draft, Submitted, Reopened)` so add Draft→Withdrawn AND Reopened→Withdrawn.
  - `"Approved": {"Superseded"}` — extend with `{"Reopened"}` (toggle) — but this is the new /reopen toggle behaviour, not a clone.
  - `"Rejected": {"Draft"}` — replace with `{"Reopened"}` (status toggle).
  - `"Reopened": {"Submitted", "Withdrawn"}` — NEW key.
  - `"Withdrawn": set()` — NEW key (terminal).
  - `"Superseded": set()` — unchanged (terminal).

### Step R4 — Endpoint behaviour split

In `/app/backend/app/routers/appraisals.py`:

- **`/withdraw`** (currently line 821) — rewrite per Phase F.
  - Remove submitter-only check.
  - Allowed source statuses: Draft, Submitted, Reopened. Else `400 NOT_WITHDRAWABLE`.
  - Set `status='Withdrawn'`, `is_current=false`. Do NOT clone.
  - Audit action: `Appraisal.Withdraw`.

- **`/reopen`** (currently line 852) — rewrite per Phase F + B.5.
  - SELECT FOR UPDATE on source.
  - Allowed: Approved or Rejected, AND `is_current=true`. Else `400 NOT_REOPENABLE`.
  - Set `status='Reopened'`. Leave `is_current=true`. NO clone, NO revision row.
  - Audit action: `Appraisal.Reopen` (existing enum value, retained — note: existing audit value is just `Reopen` without `Appraisal.` prefix; retain that or migrate, document choice in CHANGELOG).

- **`/new-version`** — NEW endpoint, add to router + service per Phase B.3.
  - Body: `revision_reason` (enum), `summary_of_changes` (str, min 10 chars after trim).
  - Single transaction:
    1. SELECT FOR UPDATE on source.
    2. Verify source.status IN (Approved, Rejected); else 403 APPRAISAL_NOT_VERSIONABLE.
    3. UPDATE source SET is_current=false **FIRST** (atomicity gate).
    4. UPDATE source SET status='Superseded' if was Approved.
    5. INSERT new appraisal: clone units/cost lines/finance facilities (reuse `clone_as_new_version` from versioning service, refactored to NOT mark source as Superseded — that's now this endpoint's job).
    6. INSERT `appraisal_revisions` row (table created in 0022 — for now this endpoint just stores enough that 0022 backfill works, OR deferred to Checkpoint 2).

  **DECISION FOR NEXT AGENT**: `appraisal_revisions` table is created in 0022 (Checkpoint 2). Three options:
  - (i) Build `/new-version` in Checkpoint 1 WITHOUT writing the revision row (TODO comment), wire it in C2.
  - (ii) Defer `/new-version` entirely to Checkpoint 2.
  - (iii) Move 0022's `appraisal_revisions` table into 0021 so revisions exists at end of C1.

  Recommendation: **(ii) defer entire `/new-version` to Checkpoint 2.** Keeps Checkpoint 1 as pure retrofit. The existing `/reopen` Approved-clone behaviour stays available temporarily during C1 — flagged with a `# TODO 2.3 C2: split into /new-version` comment but functionally preserved so 2.2 tests pass after rename. C2 then removes the clone path from `/reopen` and writes `/new-version` with revision row creation in single transaction.

### Step R5 — Frontend retrofit pass

Per Phase E.1 + E.2 of v6 prompt. Files (from inventory in 1.9):

1. `atoms.jsx` — extend `STATE_BADGE` with `Withdrawn` and `Reopened`.
2. `AppraisalPage.jsx` — `a.state → a.status`, `a.version → a.version_number`. Add Withdraw CTA visibility logic per spec; update Reopen CTA messaging to "Reopen for editing" (not "Reopen (new version)" since it's now a toggle).
3. `AppraisalsList.jsx` — same field renames; verify column headers + sort keys.
4. `UnitsTab.jsx` — `a.total_gdv → a.gdv_total` in server-GDV KPI display.
5. `SummaryTab.jsx` — `a.total_gdv → a.gdv_total`, `a.total_profit → a.profit_total`. KPI tiles update.
6. `HeaderTab.jsx`, `CostsTab.jsx`, `FinanceTab.jsx` — verify no field references; safe-grep first.
7. `lib/appraisalMath.js` — verify no string literals reference old names.

### Step R6 — Update existing 2.2 tests

`tests/test_appraisals.py` has ~40 tests. The originating session counted them in the spec. Update pattern:

- Field access: `r.json()["state"]` → `r.json()["status"]`; `r.json()["version"]` → `r.json()["version_number"]`; `r.json()["total_gdv"]` → `r.json()["gdv_total"]`; `r.json()["total_profit"]` → `r.json()["profit_total"]`.
- DB-direct queries: `select(Appraisal.state)` → `select(Appraisal.status)` etc.
- `/reopen` Approved-clone tests:
  - **If R4 took option (ii) defer**: tests still pass against `/reopen` Approved-clone (legacy retained); just rename fields.
  - **If R4 took option (i) or (iii)**: tests rewrite to call `/new-version` with `revision_reason` + `summary_of_changes` body.
- `/reopen` Rejected-toggle tests: assert `status == "Reopened"` (was `"Draft"`).
- `/withdraw` tests: update permission expectation (any `appraisals.edit` user, not just submitter). Remove submitter-only assertion. Update target status to `Withdrawn` (was `Draft`).
- Tests asserting state machine: extend ALLOWED_TRANSITIONS expectations (test_state_machine in TestStateMachine class).

**Self-report metric**: count of tests modified. Prompt expected ~30+; Step 0 estimated ~40.

### Step R7 — Run full suite + verify Checkpoint 1 acceptance

```bash
cd /app/backend && set -a && source .env && set +a && python -m pytest --tb=line 2>&1 | tail -20
```

Targets:
- All originally-passing 531 tests still green (after retrofit updates).
- Possibly fewer net tests if some `/reopen` Approved-clone tests rewrote into single tests; possibly more if state-machine matrix expanded.
- No test count target for Checkpoint 1 (target is post-Checkpoint 2: 575–600).

Lint clean: `ruff check /app/backend/app/routers/appraisals.py /app/backend/app/services /app/backend/app/models/appraisals.py`.

Frontend lint clean.

### Step R8 — Self-report and STOP

Per v6 prompt build sequencing — Checkpoint 1:
> Self-report: pre/post-retrofit test counts, backfill counts (groups, is_current rows), captured 2.2 reality vs spec divergences resolved, count of updated 2.2 tests, ALTER TABLE lock duration observation, edit-gate updated for Reopened.
> **Stop and wait for go-ahead before checkpoint 2.**

DO NOT begin Checkpoint 2 in the same session. The user explicitly required this in the v6 prompt and re-confirmed it in the fork instructions.

---

## 4. Bootstrap chicken-and-egg — third occurrence noted

**Recurrence count: 3** (originally 0017, again at 0018/0019 in 2.2 build, and twice during 2.3 Step 0 in the originating session — fresh-DB wipe between the post-2.2-fork start and Step 0 mid-checks).

**Action**: raise this entry's priority at the top of `/app/docs/SY_Homes_Future_Tasks.md` from P1 to **P0**. The pattern is now reliably reproduceable on pod restarts; production restore-from-backup will fail the same way.

Suggested update text:

> ### 1. Fresh-DB bootstrap ordering — **P0 (RECURRING)**
>
> Surfaced at 0017, recurred at 0018/0019 (2.2), and recurred TWICE during Prompt 2.3 Step 0 (May 2026). Three confirmed pod-restart triggers in two months. Documented runbook works (manual sequence: seed → seed_rbac partial → seed_test_users → alembic upgrade → seed_rbac full) but it's a manual hot-fix every time.
>
> **Mandatory fix before next Track 2 prompt**: split inline INSERT seeds out of migrations 0018, 0019, 0020 into a dedicated post-migration data-seed module that runs at the lifespan phase AFTER `alembic upgrade head` AND `seed()` + `seed_rbac()`. Add a CI smoke test that drops the DB, runs cold-start, and asserts pytest passes.

The Step 0 portion of v6 prompt already names this as a Future_Tasks reaffirmation. Next agent should land that bump as part of Checkpoint 1's Phase I writeups (CHANGELOG + Future_Tasks).

---

## 5. Scope reaffirmation

Checkpoint 1 = **0021 retrofit migration ONLY**. Specifically:
- (R1) Migration 0021 written and applied.
- (R3) Backend code rename pass complete; tests pass.
- (R4) Endpoint behaviour split — recommended option (ii) defers `/new-version` to Checkpoint 2.
- (R5) Frontend retrofit pass complete.
- (R6) Existing 2.2 tests updated for renames + endpoint splits.
- (R7) Full pytest suite green.
- (R8) Self-report.

**DO NOT** in Checkpoint 1:
- Create the three new tables (`appraisal_revisions`, `appraisal_scenarios`, `appraisal_decision_log`) — that's 0022 in Checkpoint 2.
- Build `appraisal_scenarios.py`, `appraisal_decisions.py` services — Checkpoint 2.
- Build the new GET/POST endpoints for revisions/scenarios/decisions/nudge — Checkpoint 2.
- Touch frontend SummaryTab to add RevisionTimeline, ScenariosPanel, ScenarioComparator — Checkpoint 3.
- Touch DecisionsTab — Checkpoint 3.
- Add the nudge banner — Checkpoint 3.
- Run E2E testing agent — Checkpoint 3.

After Checkpoint 1, **stop and report**. User reviews, gives go-ahead, fork to Checkpoint 2 in a new session if context budget requires it (likely will — Checkpoint 2 is the largest of the three).

---

## Appendix — file paths quick-ref

| Concern | File |
|---|---|
| Router | `/app/backend/app/routers/appraisals.py` |
| Models | `/app/backend/app/models/appraisals.py` |
| Versioning service | `/app/backend/app/services/appraisal_versioning.py` |
| Calc pipeline | `/app/backend/app/services/appraisal_calc.py` |
| RLV solver | `/app/backend/app/services/rlv_solver.py` |
| Finance engine | `/app/backend/app/services/finance_engine.py` |
| 2.2 tests | `/app/backend/tests/test_appraisals.py` |
| Audit log immutability source-of-truth | `/app/backend/alembic/versions/0006_audit_log.py` |
| Future tasks | `/app/docs/SY_Homes_Future_Tasks.md` |
| PRD (status of record) | `/app/memory/PRD.md` |
| Test credentials | `/app/memory/test_credentials.md` |
| Atoms (badge palette) | `/app/frontend/src/components/appraisal/atoms.jsx` |
| Appraisal shell | `/app/frontend/src/pages/AppraisalPage.jsx` |
| Appraisal list | `/app/frontend/src/pages/AppraisalsList.jsx` |
| Per-tab files | `/app/frontend/src/components/appraisal/{Header,Units,Costs,Finance,Summary}Tab.jsx` |

---

**End of handoff.** Next agent: read this in full before writing any code. The v6 2.3 prompt itself (in the previous user message of this thread) is your spec. This document is your map.
