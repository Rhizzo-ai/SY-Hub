# SY Homes Hub — Prompt 2.3 Checkpoint 2 Handoff

> **Forked at:** end of session that completed Checkpoint 1 (Migration 0021 retrofit + endpoint behaviour split option ii + frontend rename pass + 6 new acceptance tests).
> **Reason for fork:** C2 ≈ 1500–3000 LOC across 8–10 files (3 new tables, immutability triggers, 3 service modules, 7–8 new endpoints with atomicity gates, ~40–55 tests). Originating session had ~190k context remaining post-C1 — insufficient for the full breadth without quality compromise mid-execution. User explicitly approved fork.
> **Next agent's mandate:** Execute Checkpoint 2 ONLY. Stop and report after. Do NOT begin Checkpoint 3 (frontend) in the same session.

---

## 0. Verified state at fork time

### 0.1 Baseline
- alembic head: **`0021_appraisal_retrofit`**
- pytest baseline: **537 passed**, 2 warnings, ~68s
- C1 was committed to branch `prompt-2-3-checkpoint-1` (user pushed via Save to GitHub feature)

### 0.2 Schema state of `appraisals` (post-C1)
Columns: `id, project_id, version_number, previous_version_id, name, status, reference_date, appraisal_group_id, is_current, scenario, land_purchase_price, sdlt_category, developer_relief, contingency_pct, target_profit_on_cost_pct, target_profit_on_gdv_pct, project_duration_months, gdv_total, total_acquisition_cost, total_build_cost, total_professional_fees, total_statutory_cost, total_finance_cost, total_contingency, total_sales_cost, total_other_cost, total_cost, profit_total, profit_on_cost_pct, profit_on_gdv_pct, rlv_*, submitted_*, approved_*, rejection_reason, notes, computation_metadata, is_stale, created_by_user_id, created_at, updated_at`

Indexes: `appraisals_pkey`, `ix_appraisals_project`, `ix_appraisals_project_state`, `ix_appraisals_state`, `uq_appraisals_project_scenario_version` (UNIQUE composite), `uq_appraisals_current_per_project_scenario` (partial UNIQUE WHERE is_current=true)

### 0.3 Enums (post-C1)
- `appraisal_state`: Draft, Submitted, Approved, Rejected, Superseded, **Withdrawn**, **Reopened**
- `appraisal_scenario_enum`: Base, Upside, Downside, Sensitivity (created in 0021)
- `audit_action`: Create, Update, Delete, Approve, Reject, Reopen, Login, Logout, Export, Permission_Change, Stage_Change, Status_Change, Seed_Run, Submit, **Appraisal.NewVersion**, **Appraisal.ScenarioCreate**, **Appraisal.DecisionLog**, **Appraisal.Withdraw** (4 namespaced values added in 0021)
- ⚠️ Enum is named `audit_action`, NOT `audit_action_enum`. Verified both in C1 R0 and live during C1 application. New enums in 0022 should follow this convention (just `appraisal_revision_reason_enum` and `decision_type_enum` as the v6 spec names them — those names are fine, no rename needed).

### 0.4 C1 endpoint state (relevant for C2 split work)
- `/appraisals/{id}/withdraw` — **already final 2.3 form**. Don't touch in C2.
- `/appraisals/{id}/reopen` — **mixed**. Currently does:
  - Rejected → status='Reopened' (toggle, no clone). Final 2.3 form for Rejected.
  - Approved → clones new version + supersedes source + atomic is_current handover. **C2 must MOVE this into `/new-version`** and replace this branch with status='Reopened' on the source (no clone, no version bump, is_current unchanged) per Phase B.2.
  - The clone branch is marked with `# TODO 2.3 C2:` comment in `app/routers/appraisals.py` for findability.
- `/appraisals/{id}/submit`, `/approve`, `/reject` — unchanged, final form.

### 0.5 ALLOWED_TRANSITIONS (post-C1, in `app/services/appraisal_versioning.py`)
```python
ALLOWED_TRANSITIONS = {
    "Draft":      {"Submitted", "Withdrawn"},
    "Submitted":  {"Approved", "Rejected", "Draft", "Withdrawn"},
    "Approved":   {"Superseded", "Reopened"},
    "Rejected":   {"Reopened"},
    "Reopened":   {"Submitted", "Withdrawn"},
    "Withdrawn":  set(),
    "Superseded": set(),
}
```
**C2 must keep this as-is.** `/new-version` triggers Approved→Superseded as a side effect (already in the matrix). The new-version target row starts as Draft on a different (project_id, scenario, version_number) tuple — not a state transition on the source row beyond the existing Approved→Superseded.

### 0.6 Permissions (post-C1)
- `appraisals.{view, view_financials, create, edit, submit, approve, reopen, delete, view_sensitive}` — all seeded.
- **No new permissions in 2.3.** All C2 endpoints map to existing codes per Phase G:
  - `/new-version`, `/scenarios` (POST), `/decisions` (POST) → `appraisals.edit`
  - `/revisions`, `/scenarios` (GET), `/decisions` (GET), `/nudge` → `appraisals.view`

---

## 1. Verbatim v6 2.3 prompt — Checkpoint 2 portion

The full v6 prompt is in the originating C1 session's user-message thread. Critical anchors for C2:

### Phase A.10–A.12 — Migration 0022 (new tables only; renames + retrofit done in 0021)

**Three tables.** Reference the Phase A spec from the v6 prompt verbatim. Summary:

#### `appraisal_revisions`
- `id uuid PK`
- `appraisal_id uuid FK → appraisals.id ON DELETE CASCADE`
- `revision_reason appraisal_revision_reason_enum NOT NULL` — values per v6 Phase A.10 (likely: Cost_Update, Scope_Change, Market_Update, Sensitivity_Test, Approval_Conditions, Other — **verify in v6 prompt before writing migration**)
- `summary_of_changes text NOT NULL` — min 10 chars (DB CHECK + Pydantic validator)
- `previous_version_id uuid FK → appraisals.id` — the source row that this revision was cloned FROM
- `created_by_user_id uuid FK → users.id`
- `created_at timestamptz NOT NULL DEFAULT now()`
- Indexes: `ix_appraisal_revisions_appraisal (appraisal_id, created_at DESC)`, `ix_appraisal_revisions_previous (previous_version_id)`

#### `appraisal_scenarios`
- `id uuid PK`
- `project_id uuid FK → projects.id ON DELETE CASCADE`
- `appraisal_group_id uuid NOT NULL` — links to the group on `appraisals`
- `scenario appraisal_scenario_enum NOT NULL`
- `name varchar(255) NOT NULL`
- `description text`
- `created_by_user_id uuid FK → users.id`
- `created_at timestamptz`, `updated_at timestamptz`
- Indexes: `ix_appraisal_scenarios_group (appraisal_group_id, scenario)` UNIQUE if v6 says one row per (group, scenario) — **verify spec**.

#### `appraisal_decision_log`
- `id uuid PK`
- `appraisal_id uuid FK → appraisals.id ON DELETE CASCADE`
- `decision_type decision_type_enum NOT NULL` — values per v6 Phase A.12 (likely: Approval, Rejection, Withdrawal, NewVersion, ScenarioSelection, Other — **verify v6 prompt**)
- `decision_summary text NOT NULL` — min 10 chars
- `decided_by_user_id uuid FK → users.id NOT NULL`
- `decided_at timestamptz NOT NULL DEFAULT now()`
- `metadata jsonb DEFAULT '{}'`
- `created_at timestamptz`
- Indexes: `ix_appraisal_decision_log_appraisal (appraisal_id, decided_at DESC)`

**⚠️ Immutability triggers (Phase C.8)** — REPLICATE the audit_log pattern:
- Trigger function `reject_decision_log_mutation()` LANGUAGE plpgsql, raises EXCEPTION on UPDATE/DELETE
- Triggers `trg_decision_log_no_update` BEFORE UPDATE, `trg_decision_log_no_delete` BEFORE DELETE on `appraisal_decision_log`
- Reference: `/app/backend/alembic/versions/0006_audit_log.py`, `0007_audit_trigger_cascade.py`, `0010_audit_trigger_comment.py` for the exact pattern. Function NOT marked IMMUTABLE.
- Downgrade drops triggers + function.

**Two new enums in 0022** (no autocommit_block needed — these are CREATE TYPE, not ALTER):
- `appraisal_revision_reason_enum`
- `decision_type_enum`

### Phase B.3 — `/new-version` endpoint

- Path: `POST /api/v1/appraisals/{id}/new-version`
- Body: `{ revision_reason: <enum>, summary_of_changes: str (min 10 chars trimmed) }` — Pydantic validators
- Permission: `appraisals.edit` on the project
- **Single transaction** (per Phase B.2 atomicity):
  1. `SELECT … FOR UPDATE` on source.
  2. Verify source.status IN (Approved, Rejected); else 403 `APPRAISAL_NOT_VERSIONABLE`.
  3. Verify source.is_current=true; else 400 `SOURCE_NOT_CURRENT`.
  4. UPDATE source SET is_current=false **FIRST** (atomicity gate — partial unique index would otherwise see two currents).
  5. UPDATE source SET status='Superseded' if was Approved.
  6. INSERT new appraisal via `clone_as_new_version` (already exists in `app/services/appraisal_versioning.py`, post-C1 propagates group_id + scenario, starts is_current=false).
  7. UPDATE new row SET is_current=true; flush.
  8. INSERT `appraisal_revisions` row with `previous_version_id=source.id`, `appraisal_id=new.id`, `revision_reason`, `summary_of_changes`, `created_by_user_id=current.id`.
  9. Audit: action `Appraisal.NewVersion` (already in audit_action enum post-0021).
- Return: serialised new appraisal (full).
- **Remove** the Approved-clone branch from `/reopen` simultaneously. Replace with: source.status='Reopened' (no clone, no version bump, is_current unchanged). Audit action: `Reopen` (existing flat value, retained per CHANGELOG decision).

### Phase B.4 — Reopen post-C2 final form
```python
if appraisal.status not in ("Approved", "Rejected"):
    raise HTTPException(409, NOT_REOPENABLE)
if not appraisal.is_current:
    raise HTTPException(400, SOURCE_NOT_CURRENT)
appraisal.status = "Reopened"
if appraisal.status == "Rejected":
    appraisal.rejection_reason = None
# is_current unchanged.
```

### Phase B.5–B.8 — Read endpoints + scenarios

- `GET /api/v1/appraisals/{id}/revisions` — list revision history for an appraisal. Permission: `appraisals.view`. Return `[{id, revision_reason, summary_of_changes, previous_version_id, created_by, created_at}]` ordered by created_at DESC.
- `POST /api/v1/projects/{project_id}/appraisal-scenarios` — create a scenario row. Body `{ appraisal_group_id, scenario, name, description }`. Permission: `appraisals.edit`. Audit: `Appraisal.ScenarioCreate`.
- `GET /api/v1/projects/{project_id}/appraisal-scenarios` — list scenarios for a project's group. Permission: `appraisals.view`.
- `GET /api/v1/projects/{project_id}/appraisal-scenarios/compare?base=<id>&compare=<id>` — return the two scenario root appraisals' KPIs side-by-side. **Verify v6 prompt for exact comparator shape** — likely `{base: {...kpis}, compare: {...kpis}, diff: {...delta}}`.
- `POST /api/v1/appraisals/{id}/decisions` — append a decision-log row. Body `{ decision_type, decision_summary, metadata? }`. Permission: `appraisals.edit` OR `appraisals.approve` per v6 — **verify**. Audit: `Appraisal.DecisionLog`.
- `GET /api/v1/appraisals/{id}/decisions` — list decision log. Permission: `appraisals.view`.
- `GET /api/v1/appraisals/{id}/nudge` — return a nudge banner payload if the appraisal hasn't had a decision logged in the last N days (config-driven; v6 says default 90 days). Returns `{should_nudge: bool, days_since_last_decision: int|null, message: str|null}`.

### Phase C.8 — Decision log immutability (already noted above in tables section)

### Phase D — Services

Three new modules:
- `app/services/appraisal_revisions.py` — `create_revision_row(db, *, appraisal, source, revision_reason, summary, actor_id) -> AppraisalRevision`. Caller (router) is responsible for the source/new is_current ordering.
- `app/services/appraisal_scenarios.py` — `create_scenario(...)`, `list_scenarios_for_group(...)`, `compare_scenarios(...)`.
- `app/services/appraisal_decisions.py` — `record_decision(db, *, appraisal_id, decision_type, summary, actor_id, metadata=None)`. Triggers immutability check on attempted update/delete.

### Phase E — Frontend (DO NOT TOUCH IN C2)

`RevisionTimeline`, `ScenariosPanel`, `ScenarioComparator`, `DecisionsTab`, nudge banner — all Checkpoint 3.

### Phase F — Tests target

Per v6 prompt: post-C2 test count target **575–600** backend (post-C1 baseline is 537 → C2 adds ~40–55 tests). Areas to cover:
- Migration 0022 schema sanity (~3 tests)
- Immutability triggers (UPDATE raises, DELETE raises) (~2 tests)
- Revision row creation via `/new-version` (~6 tests: success, missing reason, summary too short, source not current, source not Approved/Rejected, atomic ordering)
- `/reopen` Approved post-C2 (status→Reopened, no clone, is_current unchanged) (~3 tests)
- Scenarios CRUD + compare (~10 tests)
- Decision log CRUD + immutability + audit emission (~8 tests)
- Nudge endpoint (~5 tests: has-decision-recently, no-decision, days threshold via config, permission gate, no-appraisal 404)
- State machine integration — Reopened→Submitted with revision row check (~3 tests)

---

## 2. Restart plan for Checkpoint 2 (literal sequence)

### Step R0 — Recover DB if bootstrapped wiped it again

```bash
cd /app/backend && set -a && source .env && set +a && alembic current
# Expect: 0021_appraisal_retrofit (head)
```

If wiped (alembic at 0017 or earlier), run the documented bootstrap recovery — same procedure as C1 R0:

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

Verify `pytest --tb=no` reports **537 passed**.

### Step R1 — Read v6 prompt Phase A.10–A.12 verbatim

The originating session inlined the v6 prompt content for table specs but the next agent should re-read the actual prompt text in its own conversation (the user will provide the spec or it's in the prompt history). Critical fields to confirm before writing migration:
- `appraisal_revision_reason_enum` exact value list
- `decision_type_enum` exact value list
- `appraisal_scenarios` whether `(appraisal_group_id, scenario)` is UNIQUE or just indexed
- `appraisal_decision_log` exact column list
- `/new-version` body field names and validators
- `/decisions` permission code (edit vs approve)
- Nudge endpoint default threshold and config key name (likely `appraisal.decision_nudge_days` in `system_config`)

### Step R2 — Write migration 0022

File: `/app/backend/alembic/versions/0022_appraisal_governance.py`. Operations:
1. `CREATE TYPE appraisal_revision_reason_enum AS ENUM (…)` — values from v6.
2. `CREATE TYPE decision_type_enum AS ENUM (…)` — values from v6.
3. `op.create_table('appraisal_revisions', …)` with columns + 2 indexes.
4. `op.create_table('appraisal_scenarios', …)` with columns + index(es).
5. `op.create_table('appraisal_decision_log', …)` with columns + 1 index.
6. CREATE FUNCTION `reject_decision_log_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'appraisal_decision_log is append-only'; END; $$;`
7. CREATE TRIGGER `trg_decision_log_no_update BEFORE UPDATE ON appraisal_decision_log FOR EACH ROW EXECUTE FUNCTION reject_decision_log_mutation()`.
8. Same for `trg_decision_log_no_delete BEFORE DELETE`.
9. Apply `set_updated_at` trigger to `appraisal_scenarios` (has updated_at column).
10. Downgrade reverses all (drop triggers, drop function, drop tables, drop types).

**Reference**: `/app/backend/alembic/versions/0019_appraisals_core.py` (table-creation pattern) + `0006_audit_log.py` (immutability trigger pattern). Match style.

### Step R3 — Apply 0022 + sanity check

```bash
cd /app/backend && set -a && source .env && set +a && time alembic upgrade head
PGPASSWORD=syhomes_dev psql -U syhomes -h localhost -d syhomes -c "\\dt appraisal_*"
# Expect: appraisal_cost_lines, appraisal_decision_log, appraisal_default_settings,
#         appraisal_finance_model, appraisal_revisions, appraisal_scenarios,
#         appraisal_units, appraisals
```

Verify triggers:
```bash
PGPASSWORD=syhomes_dev psql -U syhomes -h localhost -d syhomes -c \
  "SELECT trigger_name, event_manipulation FROM information_schema.triggers \
   WHERE event_object_table='appraisal_decision_log'"
```

### Step R4 — SQLAlchemy models for the 3 new tables

File: `app/models/appraisal_governance.py` (new file; or extend `app/models/appraisals.py` — pick one, prefer new file for module hygiene). Define `AppraisalRevision`, `AppraisalScenario`, `AppraisalDecisionLog` ORM classes. Match enum constants pattern from `app/models/appraisals.py`.

### Step R5 — Service layer

Three new files:
- `app/services/appraisal_revisions.py`
- `app/services/appraisal_scenarios.py`
- `app/services/appraisal_decisions.py`

Refer to existing services (`app/services/appraisal_versioning.py`, `appraisal_calc.py`) for style (pure-function, db: Session arg, no HTTPException — that's router's job).

### Step R6 — Router endpoints

In `app/routers/appraisals.py` add:
- `POST /appraisals/{id}/new-version`
- `GET /appraisals/{id}/revisions`
- `POST /projects/{project_id}/appraisal-scenarios`
- `GET /projects/{project_id}/appraisal-scenarios`
- `GET /projects/{project_id}/appraisal-scenarios/compare`
- `POST /appraisals/{id}/decisions`
- `GET /appraisals/{id}/decisions`
- `GET /appraisals/{id}/nudge`

**And** rewrite `/reopen` Approved branch per Phase B.4 (remove clone path, set status='Reopened', preserve is_current). The `# TODO 2.3 C2:` comment in C1 marks the spot.

### Step R7 — Tests

New file: `tests/test_appraisal_governance.py`. ~40-55 tests per Phase F coverage above. Reuse fixtures from `tests/test_appraisals.py` where possible.

Update `tests/test_appraisals.py::TestRetrofit23C1` if any C1 tests assumed the C1 `/reopen` Approved-clone behaviour. (Spot-check: the C1 `test_reopen_approved_creates_new_version` test in `TestAppraisalRouter` still calls `/reopen` and expects a clone — **rewrite to call `/new-version`** as part of C2.) Specifically:
- `tests/test_appraisals.py::TestAppraisalRouter::test_reopen_approved_creates_new_version` → rename to `test_new_version_from_approved_creates_clone`, switch to POST `/new-version` with body `{revision_reason: ..., summary_of_changes: ...}`. Add assertion that an `appraisal_revisions` row exists for the new appraisal.

### Step R8 — Run full suite

```bash
cd /app/backend && set -a && source .env && set +a && pytest --tb=line 2>&1 | tail -10
ruff check app/routers/appraisals.py app/services app/models
```

Targets:
- 575–600 passing (537 baseline + ~40–55 new + ~1–2 modified C1 router tests).
- Zero failures.
- Lint clean (or no NEW lint warnings vs C1 baseline — pre-existing 31 warnings in unrelated files are fine).

### Step R9 — CHANGELOG + PRD update

Append a `## 2.3 Checkpoint 2` section to `/app/CHANGELOG.md`. Update `/app/memory/PRD.md` with a new "### 2026-MM-DD — Prompt 2.3 Checkpoint 2: Governance" subsection at the top of "What's Been Implemented".

### Step R10 — Self-report and STOP

Per v6 prompt — stop after C2 self-report, await user go-ahead before C3. Template (fill the blanks):

```
## Checkpoint 2 self-report

**Migration 0022**
- Applied: yes
- ALTER TABLE lock duration: ___
- Tables created: appraisal_revisions, appraisal_scenarios, appraisal_decision_log
- Enums created: appraisal_revision_reason_enum, decision_type_enum
- Immutability triggers on appraisal_decision_log: trg_decision_log_no_update, trg_decision_log_no_delete
- All set_updated_at triggers wired

**Endpoints added**
- POST /appraisals/{id}/new-version (with revision row, atomic is_current handover)
- /reopen Approved branch rewritten to status='Reopened' (clone path moved to /new-version)
- GET /appraisals/{id}/revisions
- POST + GET /projects/{id}/appraisal-scenarios
- GET /projects/{id}/appraisal-scenarios/compare
- POST + GET /appraisals/{id}/decisions
- GET /appraisals/{id}/nudge

**Services**
- app/services/appraisal_revisions.py
- app/services/appraisal_scenarios.py
- app/services/appraisal_decisions.py

**Tests**
- pytest result: ___ passed, ___ failed (target: 575–600)
- New: ___ in tests/test_appraisal_governance.py
- Modified: 1 (test_reopen_approved → test_new_version_from_approved)
- ruff: clean / failures
- decision_log immutability verified (UPDATE raises, DELETE raises)

STOPPING. Awaiting go-ahead before Checkpoint 3 (frontend).
```

---

## 3. Critical-attention items / gotchas

1. **`/reopen` Approved branch must be REMOVED in C2.** C1 retained it with a `# TODO 2.3 C2:` comment to keep 2.2 tests passing post-rename. C2 must:
   - Delete the clone path inside `/reopen`.
   - Replace with status='Reopened' on source.
   - Move the clone+is_current+supersede semantics into `/new-version`.
   - Update `tests/test_appraisals.py::TestAppraisalRouter::test_reopen_approved_creates_new_version` to call `/new-version` instead.

2. **Atomicity gate is NOT optional.** The partial unique `uq_appraisals_current_per_project_scenario` will reject any transaction that briefly has two `is_current=true` rows for the same (project, scenario). Always: `source.is_current=false; flush; new.is_current=true; flush`. The C1 implementation in `/reopen` Approved-clone already does this correctly — port that pattern verbatim into `/new-version`.

3. **Immutability trigger pattern** — copy from `/app/backend/alembic/versions/0006_audit_log.py` exactly. Function name `reject_decision_log_mutation`. NOT marked IMMUTABLE (Postgres immutability is a different concept). Function signature `RETURNS trigger LANGUAGE plpgsql`.

4. **Nudge endpoint config dependency.** The default-days threshold lives in `system_config`. New key likely `appraisal.decision_nudge_days` (v6 spec — verify). If the key isn't seeded in 0016 or earlier, **add a seed insert in 0022 itself** (not a separate migration) — but ONLY the default value, no UPDATE on existing rows. If it's already seeded, just read it via `SystemConfig.get(...)`.

5. **Scenario comparator KPIs.** The spec likely says "compare two scenarios' top-level appraisals". The "top-level appraisal" of a scenario is the row with `is_current=true` for that (project, scenario). Don't compare the `appraisal_scenarios` row (it's a metadata anchor, not a data carrier).

6. **Decision log audit cross-reference.** Every `appraisal_decision_log` insert should ALSO emit a `record_audit(action='Appraisal.DecisionLog', ...)` row in `audit_log`. The decision_log is the canonical decision record; the audit_log entry is the cross-cutting trail. They are NOT redundant — auditors want both.

7. **Bootstrap chicken-and-egg.** Future_Tasks already promoted to P0. C2 will likely re-trigger this if the pod restarts during execution. R0 recovery procedure works; budget time for it.

---

## 4. File paths quick-ref

| Concern | File |
|---|---|
| Router (appraisals — extend) | `/app/backend/app/routers/appraisals.py` |
| Models (existing — keep) | `/app/backend/app/models/appraisals.py` |
| Models (new — create) | `/app/backend/app/models/appraisal_governance.py` |
| Services (existing — keep) | `/app/backend/app/services/appraisal_*.py` |
| Services (new — create) | `/app/backend/app/services/appraisal_revisions.py`, `appraisal_scenarios.py`, `appraisal_decisions.py` |
| Migration 0022 | `/app/backend/alembic/versions/0022_appraisal_governance.py` |
| Audit log immutability template | `/app/backend/alembic/versions/0006_audit_log.py` |
| Tests — existing | `/app/backend/tests/test_appraisals.py` (1 router test to update) |
| Tests — new | `/app/backend/tests/test_appraisal_governance.py` |
| CHANGELOG (append) | `/app/CHANGELOG.md` |
| PRD (update) | `/app/memory/PRD.md` |
| C1 handoff (historical) | `/app/docs/SY_Hub_2.3_Checkpoint1_Handoff.md` |
| Future_Tasks | `/app/docs/SY_Homes_Future_Tasks.md` |

---

## 5. Scope reaffirmation

Checkpoint 2 = **Migration 0022 + 3 services + 8 endpoints + ~40-55 tests + `/reopen` clone-path removal**.

**DO NOT** in Checkpoint 2:
- Touch frontend SummaryTab to add RevisionTimeline, ScenariosPanel, ScenarioComparator — Checkpoint 3.
- Touch DecisionsTab — Checkpoint 3.
- Add the nudge banner UI — Checkpoint 3.
- Run E2E testing agent — Checkpoint 3.
- Modify C1 retrofit acceptance tests in `TestRetrofit23C1` (they test C1-specific behaviour and should remain green throughout C2).

After R10 self-report, **stop and report**. Wait for go-ahead before starting C3.

---

## 6. Estimated context budget

For the next agent doing C2 in a fresh session: budget **220–280k tokens**. Areas of unexpected burn:
- Re-reading the v6 spec for exact enum values + comparator shape (~10–15k)
- Iterating on test failures from interaction between immutability triggers and SQLAlchemy session.flush ordering (~20–30k)
- Bootstrap recovery if pod wipes mid-execution (~10k)
- Pydantic validators + their error-format friction with the existing test conftest patterns (~10–15k)

Padding for C2 → C3 fork handoff doc: 5–10k. Keep budget visible; if you hit 30k remaining mid-execution, halt cleanly and prep a C3 handoff rather than rushing the tests.

---

**End of handoff.** Next agent: read this in full before writing any code. The v6 2.3 prompt itself (Checkpoint 2 portion) is your spec. This document is your map.
