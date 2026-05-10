# SY Homes Hub — Prompt 2.3 Checkpoint 3 Handoff

> **Forked at:** end of session that completed Checkpoint 2 (migration 0022 +
> 3 services + 9 endpoints + 44 new governance tests + `/reopen` Approved-clone
> removal + system_config seed schema correction).
> **Reason for fork:** C3 = frontend (5 new components, 4 touched files)
> + full Playwright E2E sweep via `testing_agent_v3_fork`. Clean slate preferred.
> **Next agent's mandate:** Execute Checkpoint 3 ONLY. Run `testing_agent_v3_fork`
> once all UI is landed. Stop and self-report. Do NOT close the 2.3 prompt as
> "complete" until the testing agent's retest passes.

---

## 0. Verified state at fork time

### 0.1 Baseline
- alembic head: **`0022_appraisal_governance`**
- pytest baseline: **581 passed**, 2 warnings, ~88s
  - 537 C1 baseline + 44 new (`tests/test_appraisal_governance.py`) + 2 modified
    (`test_appraisals.py::test_reopen_approved_returns_to_reopened`,
    `test_system_config.py::test_seed_creates_39_keys`).
- Branch: `prompt-2-3-checkpoint-1` (C1+C2 committed). C3 continues on the
  same branch — **do NOT create a new branch**. Merge to main happens once
  C3 is green.

### 0.2 Governance schema state (post-C2)

Three new tables:
- `appraisal_revisions` — 11 cols, 3 CHECKs (summary ≥10, to_version = from_version+1, distinct endpoints), 4 indexes incl. UNIQUE on `appraisal_id_to`.
- `appraisal_scenarios` — 8 cols, 1 CHECK (Base/parent XOR), 5 indexes incl. 2 UNIQUEs: `(scenario_appraisal_id)` and `(appraisal_group_id, scenario_label)`.
- `appraisal_decision_log` — 12 cols, 4 CHECKs (rationale ≥10, Conditional_Go↔conditions XOR, Correction↔reference XOR, supporting_documents is_array), 5 indexes, self-FK for correction references.

Two new enums:
- `appraisal_revision_reason_enum`: `GDV_Updated, Costs_Updated, Planning_Change, Finance_Terms_Change, Market_Change, Scope_Change, Error_Correction, Other`
- `decision_type_enum`: `Go, No_Go, Defer, Request_Revision, Conditional_Go, Correction`

Four new triggers:
- `trg_scenarios_validate_parent` (BEFORE INSERT/UPDATE on `appraisal_scenarios`) → `validate_scenario_parent()` plpgsql.
- `trg_decision_log_no_update`, `trg_decision_log_no_delete` (BEFORE UPDATE/DELETE on `appraisal_decision_log`) → `reject_decision_log_mutation()` plpgsql.
- `set_updated_at` NOT applied to appraisal_scenarios (no `updated_at` column — scenarios are append-ish metadata; updates to description aren't tracked in 2.3; polish-pass candidate).

One system_config seed: `appraisal_decisions_required_threshold = 3` (value_type=`Integer`, category=`Appraisal`).

### 0.3 Endpoint inventory (post-C2)

All endpoints mounted under `/api/v1` via `app/routers/appraisal_governance.py`:

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/appraisals/{id}/new-version` | `appraisals.edit` | Body: `{revision_reason, summary_of_changes}`. 201. |
| GET | `/appraisals/{id}/revisions` | `appraisals.view` | Returns `{appraisals: [...], revisions: [...]}` for the (group, scenario) lineage. |
| GET | `/projects/{id}/revisions` | `appraisals.view` | Nested `{groups: [{appraisal_group_id, scenarios: [{scenario, appraisals, revisions}]}]}`. |
| POST | `/appraisals/{base_id}/scenarios` | `appraisals.edit` | Body: `{scenario_label, scenario_description}`. 201. Base v1 anchor only. |
| GET | `/appraisal-groups/{group_id}/scenarios` | `appraisals.view` | Ordered (Base → Upside → Downside → Sensitivity). |
| GET | `/appraisal-groups/{group_id}/comparator` | `appraisals.view` | Absolute-values KPI payload. Frontend computes deltas via `decimal.js`. |
| POST | `/appraisals/{id}/decisions` | **`appraisals.approve`** | Rich validation cascade (is_current, version match, rationale ≥10, XORs, Europe/London future-dated rejection, client-proxy forbidden). 201. |
| GET | `/appraisals/{id}/decisions` | `appraisals.view` | `?limit=N` (1–200, default 50). Sorted by decision_date DESC, created_at DESC. |
| GET | `/projects/{id}/nudge` | `appraisals.view` | `{should_show, threshold, distinct_decision_makers, current_appraisal_id, actor_has_decided, message}`. |

Existing endpoints touched by C2 (behavioural, not signature):
- `POST /appraisals/{id}/reopen` — Approved-clone branch removed. Both Approved and Rejected sources now toggle to `status='Reopened'` on the same row. Precondition: `is_current=true`. 409 `NOT_REOPENABLE` otherwise.
- `POST /projects/{id}/appraisals` — create now auto-inserts Base anchor row into `appraisal_scenarios` for new groups.

### 0.4 Frontend state at fork

Modular appraisal tabs (post-C1 refactor) under `/app/frontend/src/components/appraisal/`:
- `atoms.jsx` (91 lines) — STATE_BADGE, KPI atoms, field-level pills (stale/live). Extended in C1 for Withdrawn (muted gray italic) + Reopened (amber).
- `HeaderTab.jsx` (122) — header fields + status banner.
- `UnitsTab.jsx` (224) — unit mix with LIVE decimal.js transforms (GIA, GDV/sqft, per-type totals).
- `CostsTab.jsx` (218) — cost lines with auto_source pills + SDLT/Finance auto-lines.
- `FinanceTab.jsx` (175) — facilities + interest-mode cards.
- `SummaryTab.jsx` (195) — KPI cards + RLV panel (3-state: empty / calculated / non_convergence).

Wrapper at `src/pages/AppraisalPage.jsx` (232 lines) — tab shell + state-machine CTAs (Submit/Approve/Reject/Reopen/Withdraw) gated by permissions + role.

List view at `src/pages/AppraisalsList.jsx` — version list at `/projects/:id/appraisals` with state badges + gated financial KPIs.

All field reads renamed in C1 to match 2.3 retrofit (`version_number`, `status`, `gdv_total`, `profit_total`). No C3 work required on existing fields — C3 is purely additive.

### 0.5 Permissions (post-C2, unchanged from C1)

- `appraisals.view`, `appraisals.view_financials`, `appraisals.create`, `appraisals.edit`, `appraisals.submit`, `appraisals.approve`, `appraisals.reopen`, `appraisals.delete`, `appraisals.view_sensitive`.
- **No new permission codes in 2.3.** C3 UI must gate on the existing codes per §0.3 above. In particular, **`/decisions` POST is `appraisals.approve`** — director / finance_director / super_admin only. PM has `.approve` per seed_rbac (used in 2.2 for the `/approve` endpoint).

---

## 1. Verbatim v6 2.3 Phase E — Frontend anchors

Phase E of the v6 prompt introduces five UI components (four new files + one
tab extension). The originating C2 session had the v6 prompt inlined in its
user-message thread; the next agent should either be handed the v6 prompt
directly or infer the shape from this handoff + the JSON payloads the
endpoints return.

### E.1 `RevisionTimeline` (new) + SummaryTab extension

- **File**: `/app/frontend/src/components/appraisal/RevisionTimeline.jsx`
- **Mount point**: right-hand column of `SummaryTab.jsx`, below the RLV panel.
- **Data**: `GET /api/v1/appraisals/{id}/revisions` → `{appraisals, revisions}`.
- **Render**: vertical timeline, one node per appraisal in the lineage (oldest → newest). Each non-v1 node shows:
  - Version badge (`v{to_version}` pill, status-colour).
  - Revision reason (enum value as label).
  - `summary_of_changes` (truncated at 140 chars; expand on hover).
  - Delta chips: `Δ GDV £±N,NNN`, `Δ Cost £±N,NNN`, `Δ Profit £±N,NNN` (colour: green for +GDV/+Profit/-Cost; red inverse; muted zero). Use `decimal.js` for formatting — never native `parseFloat`.
  - `revised_by_user_id` → resolve to name via a `/api/users/{id}` fetch or a cached `usersById` context. If not trivially available, display the UUID truncated to 8 chars + copy button (polish pass can resolve).
  - `created_at` relative timestamp (e.g. "3 days ago").
- **Empty state**: if `revisions` is empty and `appraisals` has only one entry (v1), render muted "v1 — initial Draft created {date}". No timeline line.
- **data-testid**: `revision-timeline`, plus `revision-node-{to_version}` per node.

### E.2 `ScenariosPanel` (new)

- **File**: `/app/frontend/src/components/appraisal/ScenariosPanel.jsx`
- **Mount point**: new tab on `AppraisalPage.jsx` between Finance and Summary: tab label `Scenarios`. Only visible when `appraisal.scenario === 'Base'` AND the user holds `appraisals.view`.
- **Data**: `GET /api/v1/appraisal-groups/{group_id}/scenarios`.
- **Render**:
  - Four slots (Base, Upside, Downside, Sensitivity) rendered as a 2×2 grid of cards. Base always populated; others show either populated card or a "+ Create {label}" CTA.
  - Populated card: `scenario_description` (truncated), `current_appraisal_id` link ("Open v{version_number}"), status badge, last-modified timestamp.
  - Create CTA (visible on empty slots only when user holds `appraisals.edit`) opens a modal:
    - `scenario_label` pre-filled from slot.
    - `scenario_description` textarea (min 10 chars — client-side counter + Save disabled until valid).
    - POST `/api/v1/appraisals/{base_id}/scenarios` with `base_id = appraisal.id` (must be the Base v1 anchor — if appraisal is not the Base v1 anchor, hide the panel entirely and display an info banner on SummaryTab: "Scenarios can only be created from the Base v1 appraisal").
- **data-testid**: `scenarios-panel`, `scenario-card-{Base|Upside|Downside|Sensitivity}`, `scenario-create-{label}-btn`, `scenario-create-modal`, `scenario-description-input`, `scenario-create-submit`.

### E.3 `ScenarioComparator` (new)

- **File**: `/app/frontend/src/components/appraisal/ScenarioComparator.jsx`
- **Mount point**: below the 2×2 scenario grid inside `ScenariosPanel.jsx`. Auto-renders when ≥2 scenarios exist in the group.
- **Data**: `GET /api/v1/appraisal-groups/{group_id}/comparator`.
- **Render**: horizontal table, rows = KPI, columns = scenario.
  - Header row: `Scenario | Base | Upside | Downside | Sensitivity` (only populated cols rendered).
  - Metric rows: GDV, Total Cost, Profit, Profit-on-Cost %, Profit-on-GDV %, Residual Land Value, Total Units, Passes Hurdle.
  - **Delta column** (rightmost, only when at least one non-Base scenario present): shows `Δ vs Base` per metric. Compute with `decimal.js`: `Decimal(scenario.value).minus(Decimal(base.value))`. Colour: green = favourable, red = unfavourable, muted = zero.
  - **Passes Hurdle row**: green check icon or red cross icon based on boolean. No delta cell.
  - **Null-safe**: when `current_appraisal_id` is null (no current scenario row — shouldn't happen post-C2 but defend anyway), render `—` not a stack trace.
- **Expand-to-full-report CTA**: link opening a dedicated `/projects/{id}/scenario-comparator` route — deferred to future (2.3 closeout polish pass). In C3, keep the table inline only.
- **data-testid**: `scenario-comparator-table`, `comparator-cell-{label}-{metric}` (lowercase kebab), `comparator-delta-{label}-{metric}`.

### E.4 `DecisionsTab` (new)

- **File**: `/app/frontend/src/components/appraisal/DecisionsTab.jsx`
- **Mount point**: new tab on `AppraisalPage.jsx` between Summary and the end (final tab). Always visible when the user holds `appraisals.view`.
- **Data**:
  - Primary: `GET /api/v1/appraisals/{id}/decisions` → `{items: [...]}`.
  - Secondary: each decision's `decision_maker_user_id` → resolve name (same pattern as revision timeline — context or per-decision fetch).
- **Render**: two-column layout.
  - Left column (2/3 width): chronological list of decisions. Each card:
    - Decision type pill (colour-coded: Go=green, No_Go=red, Defer=amber, Conditional_Go=blue, Request_Revision=purple, Correction=gray).
    - `decision_date` (formatted).
    - `decision_maker_name` + timestamp.
    - `decision_rationale` (full text).
    - Conditions expander (if Conditional_Go).
    - `key_assumptions_challenged` expander (if non-empty).
    - `supporting_documents` (chips — polish pass resolves to actual document links; in C3, render as UUID chips).
    - Correction-of chip linking to the corrected decision (if type=Correction).
  - Right column (1/3 width): **Log decision form** — only rendered if user holds `appraisals.approve` AND appraisal is `is_current=true` AND appraisal.status === 'Approved' (spec: decisions are board-level commitments on the Approved Base).
    - `decision_type` select (6 enum values).
    - `decision_date` picker (defaults to today, cannot be in the future — validate in Europe/London via browser timezone heuristic, but primary validation happens server-side so UI just defaults to today).
    - `decision_rationale` textarea (min 10, counter).
    - `conditions` textarea (shown only when `decision_type === 'Conditional_Go'`).
    - `key_assumptions_challenged` textarea (optional).
    - `supporting_documents`: not in 2.3 frontend (defer to 7.x document pack); omit the field from the form for C3.
    - `correction_of_decision_id` select (shown only when `decision_type === 'Correction'`, populated from existing decisions on this appraisal).
    - Submit POST to `/api/v1/appraisals/{id}/decisions` with `appraisal_version = appraisal.version_number`.
    - On 400 with error code, surface the code's message inline; on 201, refresh the left-column list and reset the form.
- **data-testid**: `decisions-tab`, `decision-list`, `decision-card-{id}`, `log-decision-form`, `decision-type-select`, `decision-rationale-textarea`, `decision-conditions-textarea`, `decision-submit-btn`.

### E.5 Nudge banner (new, project-level)

- **File**: `/app/frontend/src/components/appraisal/NudgeBanner.jsx`
- **Mount point**: top of `ProjectDetail.jsx` (exists at `/projects/:id`) — above the existing tabs/content. Also top of `AppraisalsList.jsx` (at `/projects/:id/appraisals`) for redundancy.
- **Data**: `GET /api/v1/projects/{id}/nudge` → `{should_show, threshold, distinct_decision_makers, current_appraisal_id, actor_has_decided, message}`.
- **Render**: dismissible amber banner (not modal).
  - Render only when `should_show === true`.
  - Body: "`{distinct_decision_makers} of {threshold}` decision-makers have logged Go/No_Go/Defer on the current appraisal." (pull from `message` field directly).
  - CTA: "Log your decision →" — deep link to `/appraisals/{current_appraisal_id}?tab=decisions` (scrolls DecisionsTab log-form into view on mount).
  - Hide CTA when `actor_has_decided === true` (they've already weighed in; still show the count but swap copy to "Thanks — your decision is recorded. Waiting on {threshold - distinct_decision_makers} more.").
  - Dismiss button (X) sets a session-only flag (`sessionStorage['nudge-dismissed-{project_id}'] = '1'`) so it doesn't nag within a single session; re-appears on reload (intentional — polish pass can add longer-TTL dismiss).
- **data-testid**: `nudge-banner`, `nudge-cta-log-decision`, `nudge-dismiss-btn`.

### E.6 Library additions

- **File**: `/app/frontend/src/lib/api.js` — add wrapper functions:
  - `fetchRevisions(appraisalId)`, `createNewVersion(appraisalId, body)`.
  - `fetchProjectRevisions(projectId)`.
  - `fetchGroupScenarios(groupId)`, `fetchComparator(groupId)`, `createScenario(baseId, body)`.
  - `fetchDecisions(appraisalId)`, `logDecision(appraisalId, body)`.
  - `fetchNudge(projectId)`.
- **File**: `/app/frontend/src/lib/appraisalMath.js` — add `computeScenarioDelta(base, compare, field)` that returns a `decimal.js` Decimal, and a sibling `formatDelta(d, {sign='auto', currency=true})` helper that returns a `{text, className}` tuple. Reuse in both `ScenarioComparator` and `RevisionTimeline`.

---

## 2. Restart plan for Checkpoint 3 (R0–R10)

### R0 — Recover DB if bootstrap wiped

Same procedure as C1/C2 R0. Expected state:

```bash
cd /app/backend && set -a && source .env && set +a
alembic current  # expect: 0022_appraisal_governance
export REACT_APP_BACKEND_URL=https://sy-hub-budgets-ui.preview.emergentagent.com
pytest --tb=no 2>&1 | grep -E "^[0-9]+ passed"  # expect: 581 passed
```

If wiped (alembic < 0022), run the documented seed/upgrade/re-seed sequence:

```bash
cd /app/backend && set -a && source .env && set +a
python -c "
import sys; sys.path.insert(0,'.')
import app.seed_rbac as sr
orig = sr.PERMISSION_CATALOGUE
sr.PERMISSION_CATALOGUE = [p for p in orig if p[0] not in ('appraisals.submit','appraisals.view_financials')]
from app.seed import seed
seed()
sr.seed_rbac()
"
alembic upgrade head
python -c "import sys; sys.path.insert(0,'.'); from app.seed_rbac import seed_rbac; seed_rbac()"
python scripts/seed_test_users.py
sudo supervisorctl restart backend
```

Verify 581/581 green.

**Additional C3 pre-flight**:

```bash
# Confirm frontend compiles + dev server alive.
cd /app/frontend && yarn install --frozen-lockfile 2>&1 | tail -3
sudo supervisorctl status frontend  # expect: RUNNING

# Confirm decimal.js is present.
grep '"decimal.js"' package.json  # expect: a version string (10.6.0 from 2.2)
```

### R1 — Read v6 Phase E verbatim

Re-read the v6 prompt's Phase E section. This handoff's §1 summarises the five
components; cross-check against the prompt text for any spec details this
document omitted (component-specific data-testid lists, exact colour codes,
expand/collapse interactions, role-specific gating). Fall back to this handoff
only when the v6 prompt is ambiguous.

### R2 — Scaffold the five new component files + api/math helpers

Create in parallel:
- `src/components/appraisal/RevisionTimeline.jsx`
- `src/components/appraisal/ScenariosPanel.jsx`
- `src/components/appraisal/ScenarioComparator.jsx`
- `src/components/appraisal/DecisionsTab.jsx`
- `src/components/appraisal/NudgeBanner.jsx`
- Extend `src/lib/api.js` + `src/lib/appraisalMath.js` per §E.6.

Keep each component < 250 lines (matches the C1-era SummaryTab split
philosophy). Use Shadcn components (`Card`, `Table`, `Dialog`, `Textarea`,
`Select`, `Badge`) from `/app/frontend/src/components/ui/`. For the decision
form, use `react-hook-form` + `zod` (consistent with auth forms).

### R3 — Wire components into existing pages

- `AppraisalPage.jsx` — add two new tabs: `Scenarios` (only when appraisal.scenario === 'Base'), `Decisions`. Extend SummaryTab.jsx to render `<RevisionTimeline />`.
- `ProjectDetail.jsx` — mount `<NudgeBanner projectId={id} />` at the top.
- `AppraisalsList.jsx` — mount `<NudgeBanner projectId={id} />` at the top.

### R4 — `/reopen` vs `/new-version` CTA split on AppraisalPage

The existing "Reopen" CTA in `AppraisalPage.jsx` currently calls `/reopen`.
Post-C2:
- `/reopen` is now a toggle (no clone, no new version).
- `/new-version` is the new clone path.

Split the button into two:
- **"Reopen"** — visible when `status in (Approved, Rejected)` AND `is_current=true` AND user has `appraisals.edit`. Simple POST; refresh appraisal on 200.
- **"New version"** — visible under the SAME preconditions PLUS appraisal is Approved (nudge removes Rejected-source nag: most workflows reopen first, then decide to spin a new version). Opens a modal:
  - `revision_reason` select (8 enum values).
  - `summary_of_changes` textarea (min 10 chars + counter).
  - Submit POST to `/new-version`. On 201, redirect to the new appraisal's detail page.

Both CTAs share the same row; place "Reopen" on the left, "New version" primary-styled on the right.

### R5 — Integrate the decision-form appraisal-state gate

The Log Decision form in DecisionsTab is only rendered when all of:
- `appraisal.is_current === true`
- `appraisal.status === 'Approved'`
- user holds `appraisals.approve`

Violations should hide the form entirely. Read-only users see the decisions
list only. Double-check against the 400 error codes returned by
`/decisions` POST so client-side gate matches server enforcement (spec:
`DECISION_ON_NON_CURRENT_APPRAISAL`, `INVALID_DECISION_VERSION`).

### R6 — Nudge deep-link handler

`NudgeBanner` CTA deep-links to `/appraisals/{current_appraisal_id}?tab=decisions`.
`AppraisalPage.jsx` must read `?tab=decisions` from `useSearchParams()` and
select the Decisions tab on mount + scroll the log-form into view if user
holds `appraisals.approve`.

### R7 — Playwright fixture refresh

The `testing_agent_v3_fork` run will re-create its own test users + run fresh
fixture setup. However, any prior Playwright artifacts (screenshots, traces)
from C1's iteration_9.json run will reference the old AppraisalPage
structure (4 tabs). C3 adds 2 tabs (Scenarios + Decisions) → 6 tabs total.
Ensure:
- The testing agent knows the tab set: Header, Units, Costs, Finance, Summary,
  Scenarios (conditional), Decisions.
- E2E scenarios include: create Base → Approve → log Go decision → see
  banner count drop → create Upside scenario → comparator renders →
  `/new-version` → revision timeline renders new node.

### R8 — Run full backend suite + frontend smoke test

```bash
cd /app/backend && set -a && source .env && set +a
export REACT_APP_BACKEND_URL=https://sy-hub-budgets-ui.preview.emergentagent.com
pytest --tb=no 2>&1 | grep -E "passed|failed"  # expect: 581 passed
```

Frontend smoke test via `screenshot_tool`: hit
`{REACT_APP_BACKEND_URL}/projects/{any_id}/appraisals/{any_id}` — confirm
new tabs + RevisionTimeline + nudge banner render without blowing up the
React tree.

### R9 — Call `testing_agent_v3_fork`

Payload structure (per system prompt rules):

```json
{
  "original_problem_statement_and_user_choices_inputs": "Prompt 2.3 v6 — Appraisal Governance (Retrofit + Revisions, Scenarios, Decision Log). User approved C3 frontend implementation after C2 backend landed at 581/581 tests. Frontend components per Phase E: RevisionTimeline, ScenariosPanel, ScenarioComparator, DecisionsTab, NudgeBanner. Backend endpoints are all under /api/v1 and documented in /app/docs/SY_Hub_2.3_Checkpoint3_Handoff.md §0.3.",
  "features_or_bugs_to_test": [
    "POST /api/v1/appraisals/{id}/new-version with revision_reason + summary_of_changes body creates a new Draft + revision row (via New version modal)",
    "GET /api/v1/appraisals/{id}/revisions powers the RevisionTimeline component on SummaryTab",
    "POST /api/v1/appraisals/{base_id}/scenarios creates Upside/Downside/Sensitivity from Base v1 via ScenariosPanel modal",
    "GET /api/v1/appraisal-groups/{group_id}/comparator powers ScenarioComparator delta table",
    "POST /api/v1/appraisals/{id}/decisions logs a Go/No_Go/Defer/Conditional_Go/Correction decision via DecisionsTab form (director-only)",
    "GET /api/v1/projects/{id}/nudge powers NudgeBanner on ProjectDetail + AppraisalsList",
    "/reopen CTA now toggles status=Reopened; /new-version CTA is the new clone path",
    "Nudge banner deep-link to /appraisals/{id}?tab=decisions scrolls the log-form into view",
    "Scenario comparator delta cells colour-code favourable vs unfavourable via decimal.js",
    "Decision form hides when appraisal.is_current=false OR status != Approved"
  ],
  "files_of_reference": [
    "Frontend new: src/components/appraisal/RevisionTimeline.jsx",
    "Frontend new: src/components/appraisal/ScenariosPanel.jsx",
    "Frontend new: src/components/appraisal/ScenarioComparator.jsx",
    "Frontend new: src/components/appraisal/DecisionsTab.jsx",
    "Frontend new: src/components/appraisal/NudgeBanner.jsx",
    "Frontend extended: src/pages/AppraisalPage.jsx (2 new tabs + New version CTA)",
    "Frontend extended: src/pages/ProjectDetail.jsx + src/pages/AppraisalsList.jsx (NudgeBanner mount)",
    "Frontend extended: src/lib/api.js + src/lib/appraisalMath.js",
    "Backend endpoints: app/routers/appraisal_governance.py"
  ],
  "required_credentials": [
    "/app/memory/test_credentials.md — test-admin, test-director (both super/director perms for /approve + /decisions), test-pm (edit-only, cannot log decisions), test-readonly (view-only)"
  ],
  "testing_type": "both",
  "agent_to_agent_context_note": "C2 backend is 581/581 green. C3 is frontend-only + E2E. No backend changes expected in this iteration.",
  "prev_test_files_and_folder": "/app/test_reports/iteration_9.json (last C1-era pre-C2 frontend run; now stale — 4 tabs vs the new 6-tab layout)",
  "mocked_api": {
    "has_mocked_apis": false,
    "mocked_apis_list": []
  },
  "other_misc_info": "decimal.js is loaded at src/lib/appraisalMath.js (confirmed in package.json). All money formatting MUST go through it; parseFloat is forbidden per the strict decimal policy."
}
```

### R10 — Self-report and STOP

```
## Checkpoint 3 self-report

**Components landed**
- RevisionTimeline.jsx (___ lines)
- ScenariosPanel.jsx (___ lines)
- ScenarioComparator.jsx (___ lines)
- DecisionsTab.jsx (___ lines)
- NudgeBanner.jsx (___ lines)
- AppraisalPage.jsx extended: +2 tabs, + New version modal, /reopen CTA split
- ProjectDetail.jsx + AppraisalsList.jsx: NudgeBanner mount
- src/lib/api.js: +9 endpoint wrappers
- src/lib/appraisalMath.js: +computeScenarioDelta, +formatDelta

**Backend tests**: 581 passed (unchanged from C2 baseline — C3 is frontend-only).

**Frontend tests** (testing_agent_v3_fork): ___ scenarios passed / ___ failed. Iteration: /app/test_reports/iteration_{N}.json.

**Issues encountered** (if any): ___

**Deviations from spec** (if any): ___

**Ready for user acceptance review + merge of prompt-2-3-checkpoint-1 → main**.
```

---

## 3. Critical-attention items / gotchas

### 3.1 Decision-date timezone

Server-side validation uses `zoneinfo.ZoneInfo("Europe/London")` — NOT UTC.
A decision dated "today" in London may be "tomorrow" in UTC depending on
the hour (and vice-versa during BST). The frontend `decision_date` picker
should default to `new Date().toISOString().slice(0, 10)` (user's local
date). If the user's browser is in a non-London timezone and picks "today"
from their local perspective, the server may 400 with `FUTURE_DATED_DECISION`.

Mitigation in C3: accept the occasional 400 and surface the server message
inline. Do NOT attempt to duplicate the London-timezone check in JS —
that's a polish-pass concern and belongs in a shared helper library with
server parity testing.

### 3.2 `decimal.js` usage in ScenarioComparator

Do NOT use native JS `Number` arithmetic for the comparator deltas. Scenarios
can have GDVs in the tens of millions; floating-point drift on
`12_345_678.00 - 12_345_567.99` produces `110.009999998...` instead of
`110.01`. Use:

```js
import Decimal from 'decimal.js';
const delta = new Decimal(scenario.gdv_total).minus(new Decimal(base.gdv_total));
// Display with .toFixed(2) — that's safe on a Decimal.
```

The rest of the 2.2 codebase already enforces this via lint rules in the
CI-equivalent path; the frontend linter doesn't. Eyeball any arithmetic you
write during C3.

### 3.3 Playwright fixture refresh post-rename

The C1 retrofit renamed several fields (`version` → `version_number`,
`state` → `status`, `total_gdv` → `gdv_total`, `total_profit` →
`profit_total`). If the testing agent caches JSON fixtures from
iteration_9.json (last pre-C2 frontend run), it will send OLD field names
and get 422s.

Mitigation: the testing agent operates from live HTTP + browser inspection,
NOT from cached JSON. But some of its Playwright scripts might hardcode old
JSON payloads. If the iteration_{N}.json report shows 422s on appraisal
create/update with "field not recognised" messages, that's the cause —
update the Playwright script's payload shapes, don't touch the backend.

### 3.4 Scenario description min-length server side

Server enforces `length(trim(scenario_description)) >= 10` (DB CHECK
`ck_appraisal_scenarios_description_min_length`). Frontend form validator
should mirror this — trim before length-checking. Otherwise a user can
enter "          " (10 spaces) and the server will 400 (`SCENARIO_DESCRIPTION_TOO_SHORT`
business error before the CHECK even fires).

### 3.5 Base v1 anchor requirement for `/scenarios` POST

The scenarios-create endpoint REQUIRES `base_id` to be the **Base v1 anchor**
(the appraisal that has a row in `appraisal_scenarios` with
`scenario_label='Base'` and `scenario_appraisal_id = base_id`). Subsequent
Base versions (v2, v3, ...) created via `/new-version` are NOT anchors.

If the user is on AppraisalPage for a non-anchor Base (e.g., v3), the
ScenariosPanel should detect this condition and hide the "+ Create" CTAs,
showing instead: "Scenarios can only be created from the Base v1 appraisal.
Navigate to v1 via the version timeline."

Detection logic: fetch `/api/v1/appraisal-groups/{group_id}/scenarios`, find
the Base row, compare `scenario_appraisal_id` to the current appraisal's id.
If they differ, the current appraisal is not the anchor.

### 3.6 Nudge banner refresh on decision-log

After a user successfully POSTs to `/decisions`, the nudge count may have
changed. The banner should re-fetch `/nudge` automatically. Simplest pattern:
when DecisionsTab's log-form POST returns 201, emit a custom browser event
(`window.dispatchEvent(new CustomEvent('nudge-refresh', {detail: {projectId}}))`)
and have NudgeBanner listen for it via `useEffect`. Avoid a full page reload.

### 3.7 `/new-version` redirect UX

On successful POST to `/new-version`, the response is `{appraisal: {...new...},
revision: {...}}`. The frontend should navigate the user to the new
appraisal's detail page (`/appraisals/{new.id}`). Do NOT stay on the source
(which is now Superseded and non-editable).

### 3.8 Testing agent + preview URL freshness

The test fixture at the top of `test_*.py` reads `REACT_APP_BACKEND_URL` from
env — the preview URL changes per fork. As of this handoff it's
`https://sy-hub-budgets-ui.preview.emergentagent.com`. The testing agent
should resolve the URL at runtime via `grep REACT_APP_BACKEND_URL /app/frontend/.env`
and not hardcode it in test scripts.

### 3.9 Bootstrap chicken-and-egg (recurring)

Known recurrence count: 3 across the 2.3 work so far. C3 will likely hit it
if the DB pod restarts mid-execution. R0 recovery procedure works; budget
time for it. P0 fix (migration vs seed ordering in `/root/.emergent/on-restart.sh`)
is still pending — mark the moment the bootstrap issue fires in C3 so we
get a 4th data point before deciding on the fix approach.

---

## 4. File paths quick-ref

| Concern | File |
|---|---|
| Handoff (this doc) | `/app/docs/SY_Hub_2.3_Checkpoint3_Handoff.md` |
| C2 handoff (historical — spec OK for backend endpoints) | `/app/docs/SY_Hub_2.3_Checkpoint2_Handoff.md` |
| C2 Build Pack (spec source for backend) | `customer-assets.emergentagent.com/.../Checkpoint2_Build_Pack.md` (job assets) |
| v6 2.3 prompt (Phase E is the UI spec) | user-message thread |
| Frontend: new components | `/app/frontend/src/components/appraisal/{RevisionTimeline,ScenariosPanel,ScenarioComparator,DecisionsTab,NudgeBanner}.jsx` |
| Frontend: extended pages | `/app/frontend/src/pages/{AppraisalPage,ProjectDetail,AppraisalsList}.jsx` |
| Frontend: lib extensions | `/app/frontend/src/lib/api.js`, `/app/frontend/src/lib/appraisalMath.js` |
| Frontend: existing tab modules (reference for style + data-testid conventions) | `/app/frontend/src/components/appraisal/{atoms,HeaderTab,UnitsTab,CostsTab,FinanceTab,SummaryTab}.jsx` |
| Backend: governance router (read-only reference for C3) | `/app/backend/app/routers/appraisal_governance.py` |
| Backend: governance services (behaviour reference) | `/app/backend/app/services/{appraisal_revisions,appraisal_scenarios,appraisal_decisions}.py` |
| Test credentials | `/app/memory/test_credentials.md` |
| CHANGELOG (append C3 entry) | `/app/CHANGELOG.md` |
| PRD (append C3 entry under "What's Been Implemented") | `/app/memory/PRD.md` |
| Test report archive | `/app/test_reports/iteration_{N}.json` (next N = 10+) |

---

## 5. Scope reaffirmation

Checkpoint 3 = **5 new frontend components + 3 extended pages + 2 lib
extensions + E2E via testing_agent_v3_fork**.

**DO NOT** in Checkpoint 3:
- Add any new backend endpoints. If Phase E surfaces a capability the
  backend doesn't support, log it as a C3-closeout follow-up — do NOT
  extend the router.
- Add supporting_documents picker (deferred to 7.x document pack).
- Add decision-document PDF auto-gen (deferred to future per CHANGELOG).
- Add E-signature integration (deferred).
- Add decision proxy (log-on-behalf-of) — spec explicitly forbids in 2.3.
- Add `/api/users/{id}/name` caching layer — nice-to-have, not spec.
- Modify backend test suite beyond the minimum needed to unblock a frontend
  change (unlikely — C3 is pure frontend).
- Merge `prompt-2-3-checkpoint-1` to main. Merge happens after user review
  of the C3 self-report.

After R10 self-report, **stop and report**. Wait for go-ahead before closing
the 2.3 prompt.

---

## 6. Estimated context budget

For the next agent doing C3 in a fresh session: budget **180–240k tokens**.
Areas of unexpected burn:

- Reading the v6 prompt for Phase E spec detail (~10–15k).
- Reading existing tab modules (`atoms.jsx` through `SummaryTab.jsx`) to
  match style + testid conventions (~15k).
- Iterating on `testing_agent_v3_fork` findings — E2E tests frequently find
  copy-paste gating mismatches (e.g. form-visibility gate drift between
  UI and server) (~25–40k depending on issues).
- React Hook Form + Zod validation schemas for the decision-log form (~5k).
- decimal.js usage refresher + careful arithmetic review (~3k).
- CHANGELOG + PRD updates for C3 (~3k).

Padding for unexpected bootstrap recovery: +5–10k.

If you hit 30k tokens remaining mid-execution, halt cleanly and prep an
R11 follow-up handoff rather than rushing the final tests. Better to land
clean than pad.

---

**End of handoff.** Next agent: read this in full before writing any code.
The v6 2.3 prompt's Phase E is your spec; this document is your map + your
gotcha catalogue.
