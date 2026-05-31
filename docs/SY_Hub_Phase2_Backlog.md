# SY Hub — Phase 2 Backlog (Prompt 2.4A deferrals)

Generated 2026-05-09 from Chat 16 / Prompt 2.4A `Build Pack v3` execution.
Each item below was knowingly deferred during 2.4A execution per locked
decisions or the §R0 STOP-and-resplit triggers. Owner: Chat 17+.

---

## P1 — Backend variance attention-flag asymmetry (Chat 17 E12 follow-up)

`backend/app/services/budgets.py:155-166` (`_classify_variance`)
returns Green for any `variance_pct ≤ 0` by design. The frontend now
re-derives the band symmetrically (E12) so display is consistent, BUT
the backend still uses `line.variance_status == 'Red'` to drive the
`requires_attention` flag (see
`backend/app/services/budget_lines.py:467`). This means under-budget
anomalies (e.g. a line £399k under current_budget — likely a stale
FTC or missing commitment) currently never trigger attention scans.

**Tasks:**
- Decide product intent: should under-budget swings flag attention?
  Operator's intent surfaced in Chat 17: yes — a line ≤-10% likely
  indicates data quality issue (wrong FTC method, stale commitment),
  not "we saved money".
- If yes: change `_classify_variance` to `abs(variance_pct)`, write
  an Alembic data-migration to re-classify existing rows, regenerate
  attention flags via `refresh_attention` endpoint.
- Estimated effort: 2-3 h backend + 1h re-test (existing frontend
  tests cover the symmetric semantic already).

Tracked under Chat 19 hardening pass or as a stand-alone P1 commit
before launch.

---


## HIGH-PRIORITY — Chat 18 dedicated build

### BudgetLinesGrid v2 (BT-style) — replace flat R6 grid

Operator surfaced Buildertrend Job Costing Budget view at the end of
Chat 17 as the state-of-the-art target for this surface. The 2.4B-i
flat 6-column grid is sufficient for ship but represents a fraction
of what finance / contracts will use day-to-day. **One of the most-used
surfaces in the entire platform — must be state-of-the-art.**

Required features (BT-aligned):

- **Cost-code grouping** with expand/collapse + per-group subtotals
- **11+ money columns** with column visibility toggle: Original /
  Revised / Pending / Committed / Actual / Builder variance / Projected /
  Projection reference / Cost to complete / Revised vs projected /
  Projected profit / Projected margin %
- **Per-line status pills** — Completed / Budgeted / Current costs
- **Heat-mapped variance cells** — pink for overrun, green for underrun
- **Indented hierarchy** — group → cost code → line item
- **Sticky cost-code column** on horizontal scroll
- **Top-level view tabs** — e.g. Job Costing / others

**Operator-implied features (not in BT screenshot but worth speccing):**

1. **Bulk select + bulk actions** — apply % complete to a cost-code
   root; bulk reassign cost codes; bulk delete
2. **Filtering** — by cost-code root, variance band, status,
   % complete range

**Data model:** 2.4A backend already supports most of this. The
`budget_lines` table has `original_budget`, `current_budget`,
`actuals_to_date`, `committed_not_invoiced`, `forecast_to_complete`,
`forecast_final_cost`, `variance_status` per line, plus `cost_code_id`
for grouping. **UI rework only — no backend changes expected.**
Confirm during specification.

**Chat 18 plan:** dedicated Build Pack with full audit cycle.
Reference screenshot in operator's Chat 17 attachments.
Push Playwright E2E plan to Chat 19 to make room.

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

---

## Chat 19A additions (2026-02-15)

Added at chat-end per Prompt 2.5A §R8. Verbatim from Build Pack v1 front matter.

- **B19** — Unbudgeted-cost director sign-off escape route. Design pass needed: column-on-actual vs auto-create "Unbudgeted" budget_line vs separate override table. Block on Track-2 wrap (Chat 21 review with MD/Louise).
- **B20** — Subcontract module (`SC_Valuation` source wiring). Activates the reserved enum value once subcontract module ships. Depends on Track-4 subcontractor portal.
- **B21** — Xero connector (Track 6). Will wire `Xero_Bill` source_type and populate `external_id` from Xero invoice IDs; idempotency-protected by the partial unique index on `(external_id, source_type)`.
- **B22** — Document module integration (Track 5). Backfill `actuals.document_ids` JSONB from `actual_attachments` table; deprecate the local-filesystem path.
- **B23** — Email forwarding cutover runbook. When Postmark is provisioned, configure `bills@syhomes.co.uk` forwarding rule in Outlook → Postmark inbound address. Parallel run with PC system until matched on 100 invoices, then deprecate PC system. Per Q10.
- **B24** — AI capture cost dashboard. Track per-extraction tokens + cost (already stored in `ai_capture_jobs`). Surface in admin UI in a future chat.
- **B25** — Auto-routing rules (entity/project/cost code suggestion from vendor heuristics). Operator's existing PC-side rules to be lifted into this once Q7 keywords are shared. Until then, AI capture returns suggestions only; user confirms in 19B UI.
- **B26** — `pause_ai_capture` / `resume_ai_capture` operator helper scripts. Wrap the APScheduler `pause_job("ai_capture_dispatcher")` / `resume_job(...)` calls in `python -m app.scripts.pause_ai_capture` etc. Useful during incident response without needing a redeploy. Currently the only "pause" path is flipping `POSTMARK_INBOUND_ENABLED=false` (which blocks inbound but lets the queue drain) or `AI_CAPTURE_MODEL=test-stub` (which produces dummy data — destructive). Per Appendix D.

### Chat 19A — implementation-driven addition (resolved in scope)

- **B27 (closed 2026-02-15)**: Post-time budget-terminal status check. `post_actual`
  now re-checks the parent budget's terminal status (Closed/Superseded) and raises
  `BudgetLineLockedError` if the budget transitioned to a terminal state while a
  Draft was in flight. Operator workflow: Void the Draft, or move it to the
  Current budget version, then re-post. Implementation: `app/services/actuals.py::post_actual`.
  Test: `tests/test_actuals_service.py::TestStateMachine::test_draft_to_posted_blocked_when_budget_terminal`.

### Chat 19B — new items added at chat-end (2026-02-15)

Verbatim from Build Pack v1 front matter §"New backlog items (added at chat-end)".

- **B28** — AI-capture review surface. The full UI for `Awaiting_Review` job
  inspection, promote-to-actual workflow, confidence-score display, and
  per-extraction-cost visibility. Target: Chat 19C. Reasonable scope: list page
  + detail page + promote form + retry/discard actions. ≈25 tests.

- **B29** — Bulk-pay batch endpoint. Currently 19B does N independent
  `POST /actuals/:id/mark-paid` calls for a multi-selection bulk-pay. If Louise
  routinely pays >50 invoices in a single session, the N-call pattern becomes
  flaky on slow networks. Backend should add `POST /actuals/bulk/mark-paid`
  accepting an array; frontend swaps the loop for a single POST. Defer until
  usage data shows the loop is a problem.

- **B30** — Money input UX polish. The Draft-create form takes raw Decimal
  strings for net/vat. A custom money input component (`<MoneyInput>`) that
  handles thousand-separators on display, strips them on submit, and validates
  2dp would reduce data-entry errors. Pattern can also be back-applied to the
  Budgets line edit. Defer pending the broader "form polish pass" backlog item.

- **B31** — Louise's payment-view filters. v1 supports only `status` + `project`.
  Realistic Louise needs are: `aged > N days`, `supplier`, `entity` (Parent/SPV/
  ConstructionCo), `amount band`. Defer; ship v1 with status+project; iterate
  after week 1 of real use.

- **B32** — Actuals export. CSV/PDF export of the actuals list (per project and
  global). Finance team will want this for monthly reporting. Defer to Chat 22+
  (broader reporting track).

- **B33** — Attachment thumbnails. v1 renders attachments as a row with filename
  + size + download link. PDF page-1 thumbnail (server-side or client-side via
  pdf.js) would help recognise the right invoice at a glance. Defer; nice-to-have.

- **B34** — Defensive 422 on project-scoped actuals list. The live
  `GET /projects/{project_id}/actuals` constructs `ActualsListFilters` mid-handler.
  After the D32 patch, if a non-frontend caller (Postman, future module) passes a
  comma-separated `status` to this endpoint, the field_validator raises
  `ValueError` during model construction and surfaces a 500 (not the intended 422).
  Frontend in 19B never triggers this path (multi-status only goes to the global
  endpoint), but wrapping construction in try/except → HTTPException(422) is a
  small hardening pass. Defer until a real consumer asks.

- **B35** — Server-side sensitive-field stripping in the change-log response.
  The 19A backend `_serialise_change_log` returns raw `event_payload` JSONB to
  all callers. 19B gates the display in `ActualHistory.jsx` on
  `actuals.view_sensitive`, but a readonly user who calls
  `GET /actuals/:id/change-log` directly still sees sensitive payloads
  (dispute_reason, void_reason, etc.). UI-only gating is fragile; backend should
  strip sensitive keys from the payload for callers without
  `actuals.view_sensitive`. Defer; this is a 19A hardening item, not in 19B's scope.

### Chat 19C — new items added at chat-end (2026-02-17)

Verbatim from chat-19C Build Pack v-final front matter, lines 86–91.

- **B37** — pdf.js lazy-loaded attachment thumbnails. v1 uses `<embed>` (D38);
  v2 wraps `pdfjs-dist` in `React.lazy` + `Suspense` to render a page-1
  thumbnail without busting the bundle cap. Re-scopes B33 with explicit
  lazy-load requirement.

- **B38** — AI capture cost dashboard UI. Surfaces per-job and rolling-window
  `cost_pence`, `prompt_tokens`, `completion_tokens` from `ai_capture_jobs`.
  Pairs with existing B24 (backend ready).

- **B39** — Auto-routing rules engine UI. Operator-defined rules:
  "supplier X → entity Y, project Z, cost code C". Backend B25 implementation
  prerequisite.

- **B40** — Multi-status filter on the AI capture list (e.g. "Awaiting Review
  AND Failed"). v1 single-status per D40 + D45.

- **B41** — Bulk discard. v1 is per-row.

- **B42** — Re-promote a Discarded job. Currently terminal; would need a
  backend transition `Discarded → Queued`. Defer.

### Chat 19C — B36 resolution note

**B36** (logged in chat-19B closing under §"Open items for Chat 19C") is
closed via regression test only. Symptom not reproducible at HEAD; zero LOC
backend change applied per operator instruction. The invariant is locked by
`backend/tests/test_actuals_attachments.py::TestB36AttachmentReadAfterWrite::
test_post_attachment_immediately_visible_in_list` (green at HEAD) and the
chat-19B `actuals-attachments.pm.spec.ts:Delete attachment` E2E has been
un-skipped. See `docs/chat-summaries/chat-19c-closing.md` §"B36 RCA — not
reproducible" for the full RCA and the hypothesised silent fix.


## 15. CI path portability — `test_audit_remediation_p0.py` + `_p1.py` hard-coded `/app/...` absolute paths

**RESOLVED Chat 30** — fixed via two test-only pushes (`77e3eb3`
path-relative refactor 17→7; `acaa9a0` role-based admin lookup +
cookie-domain fix 7→0). CI #33 green. Zero product code.

**Status:** pre-existing. Surfaced during the Chat 29 polish-pass CI
run as 17 failures. **NOT** introduced by Chat 29 commits — repo CI
has been red on the backend job since the test files were first
committed (`020a8e3` "Audit Remediation TIER P0 (v2 build pack): four
critical fixes" + the follow-on auto-commit `700f184`,
pre-Chat-28).

**Symptom.** Tests open files via absolute paths like
`/app/backend/app/routers/appraisals.py`. Works inside Emergent's
container (repo mounted at `/app`); fails on the GitHub Actions
runner (checkout at `/home/runner/work/SY-Hub/SY-Hub/`) with
`FileNotFoundError`.

**Affected tests (17 total).** All `FileNotFoundError` +
downstream auth-401 cascades in
`backend/tests/test_audit_remediation_p0.py` +
`backend/tests/test_audit_remediation_p1.py`. Literal offending
literals at `_p0.py:135` (`appraisals.py`), `:634`
(`po_receipts.py`), `:663` (`auth/tokens.py`), `:895`
(`routers/auth.py`), plus the partner cases in `_p1.py`.

**Fix (~30 min, frontend-touching nil, backend-test-only).**
Replace every `path = "/app/backend/..."` literal with a
`__file__`-relative resolution. The test files live at
`backend/tests/`, so `parents[2]` resolves to `/app` (or whatever
the repo root is on the runner):

```python
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
path = REPO_ROOT / "app" / "routers" / "appraisals.py"
```

Run pytest locally to confirm 1004 → 1021 passing (re-enables the
17), then push.

### Chat 31 — new items added at chat-end (2026-05-31)

Added at chat-end per Chat 31 close. B43–B45 were named as Stage-2
deferrals in the 2.4C Build Pack; logged here for traceability. B46 and
B47 are new this chat.

- **B43** — Stage 2 per-role / per-user budget approval limits. Current
  2.4C is Stage 1: a single global `budget.self_approval_threshold_gbp`.
  Stage 2 adds per-role and/or per-user limits (e.g. PM can self-approve
  to £5k, Contracts Manager to £25k, Director unlimited). Needs a limits
  table keyed on role/user + the activate guard reading the caller's
  effective limit instead of the global threshold. Defer until real usage
  shows the single global threshold is too blunt.

- **B44** — Threshold admin UI. `system_config` budget keys (incl.
  `budget.self_approval_threshold_gbp`) are editable only via
  `PUT /system-config/{key}` today. Build a front-end admin surface for
  super_admin to view + edit budget config without hitting the API
  directly. Pairs with the broader system-config admin surface.

- **B45** — Front-end message for the 403 self-approval refusal. The 2.4C
  backend returns HTTP 403 (`BudgetSelfApprovalError`) when a creator
  tries to self-activate at/above threshold. Front-end should catch this
  and show a guided "this needs a Director to approve — ask [X]" prompt
  rather than a raw error toast. Pairs with B46.

- **B46** — `/budgets/{id}/activate-preview` endpoint. Read-only: runs the
  SoD self-approval guard without mutating budget status, so the FE can
  warn the user inline ("you can't approve this yourself") before they
  click Activate. UX warm-up for B45. Suggested as unsolicited scope in
  Chat 31; declined for 2.4C and logged here. Defer.

- **B47 (closed 2026-05-31)** — Push-hygiene cleanup. Auto-commit `352eb08`
  swept noise onto main: a hostname-rename artefact, `scripts/seed_r7_*`,
  and `test_reports/helpers/*`. VERIFIED gone from main at Chat 34 — all
  named files return 404. No Claude Code pass needed. (Hostname-rename
  artefact unnamed in original entry; named junk confirmed removed.)

**Owner.** Defer to the Track 2 wrap-up audit (Chat 30+) with MD /
Louise, OR to a Claude Code checkpoint pass. **Not blocking** —
local pytest has caught real regressions throughout Tracks 2 + 3.

**Tracked in:** `docs/chat-summaries/chat-29-closing.md` §C.

### Chat 32 — new items added at chat-end (2026-05-31)

Deferred during Build Pack 2.7 (Subcontractors / CIS / supplier documents)
per locked decisions LD2/LD3 and single-session scope discipline.

- **B48** — CIS verification auto-expiry flagging. 2.7 stores
  `expires_on` on `subcontractor_cis_verifications` but does NOT scan or
  flag lapsed verifications. Add an attention-scan (mirror the budgets
  `requires_attention` pattern) that flags subcontractors whose current
  CIS verification has expired or is within N days of expiry. Payment-
  blocking on a lapsed verification belongs with 2.8 valuations (which
  don't yet exist) — wire there, not here. Defer.

- **B49** — Migrate `supplier_documents` to the Track 5 versioned
  document store. 2.7 ships a lightweight `supplier_documents` table with
  `file_ref` as a reference string only (no binary upload pipeline). When
  Track 5 lands the versioned store + approval workflow, migrate supplier
  compliance docs onto it and deprecate the standalone table's file path.
  Defer to Track 5.

- **B50** — Per-project supplier/subcontractor ratings. The Phase 2 brief
  (Prompt 2.7) mentions "ratings per project"; deferred from 2.7 to keep
  it a single backend session. Needs a ratings table keyed on
  (supplier_id, project_id) + a scoring scheme. Defer; low priority until
  there's enough subcontractor history to rate.

- **B51** — Subcontractor onboarding checklist widget (read-only).
  Bolt-on UX surface on top of 2.7: surface each Subcontractor's
  `current_cis_status` plus most-recent `supplier_documents` expiry on a
  dashboard panel. Two-endpoint backend addition (no migration):
  `GET /api/v1/subcontractors/onboarding-summary` (list view, one row per
  subcontractor with the two derived fields) and
  `GET /api/v1/subcontractors/{id}/onboarding-checklist` (detail view —
  full document list + current verification). Held back to keep 2.7
  scope-locked; spec properly when 2.7-FE picks up so widget design is
  driven by FE needs not back-end speculation. Defer.

### Chat 33–34 — new items added at chat-end (2026-05-31)

- **B52** — Contingency-line flag UI. 2.6 added `budget_lines.is_contingency`
  but it's settable only via direct SQL or a future budget-edit form. A
  Project-Detail toggle would let PMs designate contingency lines without
  engineering, unlocking the ContingencyDrawdown BCR type for live projects.
  Offered by Emergent at Chat 33 close as unsolicited scope; declined
  (frontend, out of 2.6 backend scope). Fold into 2.6-FE. Defer.

- **B53** — Prompt 2.8 split (decision record, not a build task). 2.8 split
  into **2.8a** (Subcontracts + Variations — Chat 34) and **2.8b**
  (Valuations + Payment Notices + Retention release + CIS deductions —
  later). Driven by the brief's explicit "candidate split" flag; 2.8a closes
  the variation→BCR loop into 2.6, 2.8b is the monthly-money engine and uses
  the 2.7 CIS verification data + the `retention_pct`/`cis_applies` fields
  stored (unused) in 2.8a.

- **B54** — Variation summary endpoint. Aggregated approved-variation totals
  per subcontract (folded-into-sum vs BCR-routed). Offered by Emergent at
  Chat 34 close as unsolicited scope; declined (dashboard/2.8b territory).
  Fold into 2.8b or the reporting track. Defer.

- **B55** — PO variation workflow for NON-subcontract orders (extras/alterations
  on material/supplier POs). Out of scope for 2.8b; logged for a later prompt.
  
- **B56** — Subcontract→budget line mapping. `_pick_budget_line_for_subcontract`
  currently picks "any active line". Should map a specific budget line per
  subcontract. Backend. From Chat 35 (2.8b).
  
- **B57** — `view_sensitive` masking pushed into SELECT. Currently masks at the
  serialise layer for valuation/notice endpoints; push filtering into the query
  so masked columns aren't materialised. Backend hardening. From Chat 35 (2.8b).
