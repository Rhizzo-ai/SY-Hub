# SY-Hub Platform — PRD

## Original problem statement

Execute strict prompts (Build Packs) to extend the SY-Hub backend per the
SY Homes Phase 1 / Phase 2 brief. Each prompt has 15 locked decisions, an
exact migration count, an exact endpoint count, and a target test delta.
Frontend / actuals / commitments / Xero are out of scope until later prompts.

## Stack
- FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL 16
- Pytest with cookies-only auth contract (no Bearer headers)
- Pattern α tenant scoping: project-id resolution + `_visible_project_ids`
  filter, mirroring `routers/appraisals.py`. **No** `tenant_id` columns on
  Track-2+ tables.
- Audit append-only via `audit_log` + `audit_log_no_modify()` trigger.

## What's been implemented

### 2026-02-15 — Prompt 2.5B Actuals Frontend + Payment View + E2E ✓
- **Frontend + E2E chat** following 19A backend. Bundle 387.10 kB →
  **419.72 kB** (+32.62 kB gz, target ≤+35 / hard cap +50).
- **Surfaces shipped:** ActualsList (per-project table + filters + create
  Sheet), ActualNew (mobile create route), ActualDetail (header / state
  actions / attachments / collapsible history), PaymentsView (Louise's
  global cross-project list with bulk Mark-Paid), AttachmentUploader
  (`react-dropzone@^14` + React synthetic onPaste for clipboard).
- **15 actuals endpoints wired** via `lib/api/actuals.js`; Zod schemas in
  `lib/schemas/actuals.js`; React Query hooks in `hooks/actuals.js`;
  capability helpers in `lib/actualCapability.js`.
- **State machine UI** matches the live router. `canPostDraft` correctly
  uses `actuals.edit` (verified — router docstring's "actuals.post" label
  is documentation-only). All non-trivial actions open a Radix Dialog
  with reason capture; field state resets on action change.
- **BulkPayDialog (Louise)** uses D30 N-call loop with snapshot pattern,
  shared `paid_date`, per-row auto-generated `BACS-YYYYMMDD-{id6}` refs
  (editable), per-row pending/success/error pills, full
  `actualsKeys.all`+`['budgets']` cache invalidation on completion.
- **Sensitive-field gating (D26):** Zod schemas declare sensitive fields as
  `.nullable().optional()`; backend strips at serialiser layer; UI renders
  "—" for `null|undefined` via `fmtGBP`. `ActualHistory` payload tile is
  client-gated on `actuals.view_sensitive`.
- **Pre-prompt backend patch (D32 + D33):** `ActualsListFilters.status`
  now accepts comma-separated values; ValidationError wrapped to 422 in
  both routes. **pytest 780 → 782 passed.**
- **Test deltas:** Jest 47 → **88** (+41 across 7 spec files); Playwright
  32 → **66** (+34 across 9 spec files); smoke 6 → **11**. Coverage:
  `actualCapability.js` 95.16% / `lib/schemas/actuals.js` 100%.
- **Routes are FLAT siblings in App.js** (not nested under ProjectDetail).
  `/payments` is top-level; project routes are `/projects/:id/actuals[/new|/:actualId]`.
- **8 new backlog items (B28–B35)** appended to Phase 2 backlog. Headline:
  B28 — AI capture review surface for Chat 19C.
- Reference: `docs/chat-summaries/chat-19b-closing.md`. **10 implementation
  deviations (E1–E10)** captured. Notably E8 fixed a shipped-code bug in
  `CreateActualSheet` (missing `project_id` in form defaults caused Zod to
  silently reject every submit); E7 patched the `freshActual.ts` factory to
  dynamically resolve the current Active/Locked budget.

### 2026-02-15 — Prompt 2.5A Actuals Backend ✓
- **Backend only — bundle delta 0.** Migration `0025_actuals` applied; 21 new
  endpoints across 3 routers (`actuals`, `inbound`, `ai_capture`); AI capture
  pipeline (Postmark inbound + APScheduler dispatcher + Anthropic stub/live).
- 5 new services: `actuals`, `actual_attachments`, `ai_capture`,
  `postmark_webhook`, `budgets_reconciliation`. 11 domain exceptions in
  `actual_errors`.
- 5 new tables: `actuals` (51 cols), `actual_attachments`,
  `inbound_email_messages`, `ai_capture_jobs`, `actuals_change_log`. 13 plain
  + 2 partial-unique indexes; 6 user triggers; 3 functions. Round-trip
  downgrade/upgrade verified.
- 9 new `audit_action` enum values (`Post`, `Mark_Paid`, `Void`, `Dispute`,
  `Undispute`, `Release_Retention`, `Add_Attachment`, `Remove_Attachment`,
  `Promote_From_Capture`).
- RBAC: `actuals.admin` (sensitive) added. Catalogue exposes 6 actuals perms
  (view/view_sensitive/create/edit/approve/admin). Finance role inherits admin;
  PM gets view/create/edit only.
- 107 new tests across 5 files. **Total backend: 780 passed / 0 failed / 0
  errors.** Baseline gate Jest 47 / pytest 673 / bundle 387.10 kB → after Jest
  47 / **pytest 780** / bundle 387.10 kB (Δ 0).
- Reference: `docs/chat-summaries/chat-19a-closing.md`. 5 implementation
  deviations (E1–E5) captured in chat summary and CHANGELOG. E5 patched
  in-scope (B27 — post-time budget-terminal re-check) per operator request.
  ⚠️ E4 sandbox env change: `POSTMARK_INBOUND_ENABLED=true` for tests;
  production MUST override to `false` until B23 cutover.

### 2026-05-14 — Prompt 2.4B-ii Playwright E2E ✓
- **Test infrastructure only** — zero changes under `backend/app/` or `frontend/src/`.
- Playwright `@playwright/test@1.60.0` + `otplib@12.0.1` (devDependencies).
- 32 physical Playwright tests in 12 spec files across 8 groups (31 active + 1 quarantined LineDrawer #6 per Build Pack v4 §15 known risk + operator policy 3a).
- Smoke subset (`yarn e2e:smoke`): **6/6 passing in 19.3s**.
- `frontend/playwright.config.ts` — single worker, headless, 5 named projects (chromium-pm/admin/readonly/site/anon) with per-role `storageState`.
- `frontend/e2e/global-setup.ts` re-seeds users + extended demo data, primes `storageState` files. `frontend/e2e/global-teardown.ts` exclusion-list sweep.
- 6 helpers in `frontend/e2e/helpers/`: `login.ts`, `seed.ts`, `asserts.ts`, `api.ts`, `factory.ts`, `freshBudget.ts`. No POM per locked decision #9.
- `scripts/seed_demo_budget.sh` extended with `E2E_PROJECT_ID` env override + 3 flags (`--with-v2-lineage`, `--empty-project`, `--extra-appraisal`). All idempotent.
- Baseline gate BEFORE + AFTER: Jest 47 ✓, pytest 673 ✓, bundle 387.09→387.10 kB (delta 0).
- D13 (new): `AppraisalCostLine` schema drift — Build Pack v4 §R2.2b listed 5 phantom columns; corrected to live 10-column schema. Annotation: `docs/chat-summaries/chat-18-build-pack-annotations.md`.
- D14: LineDrawer #6 quarantined (`test.skip`) — covered by Chat 17 Jest unit test.
- Reference: `docs/chat-summaries/chat-18-closing.md`.

### 2026-05-12 — Prompt 2.4B-i §R8 component tests ✓
- 10 test suites, 46 tests, 0 failures, ~3.4s runtime (`yarn test --watchAll=false`).
- Coverage: lib/ 96%, schemas 86%, BudgetsList 92%; component coverage
  46% (5 of 14 components 0% — relied on smoke-tested e2e paths).
- Files: `__tests__/budgetCapability.test.js` (8 tests),
  `__tests__/budgets-schemas.test.js` (5), `BudgetLinesGrid.pure.test.js`
  (5), `VarianceBadge.test.jsx` (6), `StatusBadge.test.jsx` (1),
  `SensitiveBanner.test.jsx` (2), `BudgetLineage.test.jsx` (4),
  `LifecycleActions.test.jsx` (5), `BudgetsList.test.jsx` (4),
  `LineDrawer.test.jsx` (5).
- Test infra: `setupTests.js` + `test/mockMatchMedia.js`
  + `test/renderWithProviders.jsx` + `test/mocks/fixtures.js`
  + `__mocks__/react-router-dom.js` + `jest.resolver.cjs`
  + craco.config.js jest section.
- Required tests all present: `buildReorderedIds` pure-fn (H8),
  lineage breadcrumb (E10), E9 conflict-banner, status×perm matrix,
  sensitive-stripped schema parse, mobile-floor gates, dirtyFields-only
  PATCH body.
- §R6.3 H8 follow-up: extracted `buildReorderedIds` to
  `lib/buildReorderedIds.js` so the pure-fn test doesn't drag dnd-kit /
  zod / shadcn into its require graph.
- §R7 follow-up: corrected FTC method enum values
  (`BudgetRemaining` → `Budget_Remaining` etc.) after schema test
  caught the divergence from backend.

### 2026-05-12 — Prompt 2.4B-i §R7 LineDrawer + LineItemsPanel + CostCodePicker ✓
- `components/budgets/LineDrawer.jsx` — full rhf + Zod form (line_description,
  notes, ftc_method, forecast_to_complete, percentage_complete, cost_code_id);
  dirtyFields-only PATCH body; defensive cost_code_id only sent when status
  permits; sensitive-field gates (notes + FTC fields hidden unless
  `budgets.view_sensitive`); E9 conflict-detect via `updated_at` watermark
  (loadedAt + justSavedRef) with non-blocking "Reload" amber banner;
  close-with-dirty AlertDialog confirm with sy-orange Discard; Cmd/Ctrl+S
  save + Esc close keyboard shortcuts (operator addition).
- `components/budgets/LineItemsPanel.jsx` — inline-CRUD on items table
  (description / qty / unit / rate, computed amount column); add-row
  builder beneath table; per-row Delete via existing ConfirmDialog
  (sy-orange destructive variant); mobile read-only floor. Field rename
  `unit_cost` → `rate` documented as **errata E11**.
- `components/budgets/CostCodePicker.jsx` — shadcn Select wrapping
  `useCostCodes(projectId)`; filters to `enabled` codes but always keeps
  currently-selected even if disabled; loading + missing-label fallback.
- Build: `main.js` 387.08 kB (+4 kB; rhf was already in the bundle).
- Smoke (test-pm on Draft v1): drawer opens, all 6 form fields render,
  dirty tracking flips on type, Cmd+S triggers PATCH + "Line saved"
  toast + dirty resets, Esc with dirty shows discard dialog (Keep
  editing / Discard sy-orange), discard closes drawer, items panel
  shows existing rows + add flow appends new row with computed £500.00.

### 2026-05-11 — Prompt 2.4B-i §R6 Budget Lines Grid ✓
- `components/budgets/SortableLineRow.jsx` — dnd-kit sortable row with
  setActivatorNodeRef-wired drag handle (C8/C9 a11y), inline edit on
  `line_description` and `percentage_complete` (E7 names), optimistic
  update + rollback via `usePatchBudgetLine` (extended in `hooks/budgets.js`),
  client-side cost-code label join (D13/E7), sensitive-field renders via
  `formatMoney(undefined) → "—"`.
- `components/budgets/BudgetLinesGrid.jsx` — DndContext + KeyboardSensor
  for keyboard a11y, `useReorderBudgetLines` with cache-rollback,
  memoised lines/itemIds, mobile read-only banner, reorder-error toast,
  exports pure `buildReorderedIds()` for §R8 unit test.
- `components/budgets/LineDrawer.jsx` — shadcn Sheet placeholder for §R7
  (line JSON dump + "coming next" checklist).
- `lib/budgetCapability.js` — added `isBudgetEditable`, `isLineCreatable`,
  `isCostCodeMutable` status-only helpers.
- Wired into `BudgetDetail.jsx` (replaced §R6 placeholder).
- Build: `main.js` 382.72 kB (+20 kB).
- Smoke (test-pm on v3 Draft): 3 rows render with drag handles, inline
  edit description + %-complete saved and re-rendered, drawer placeholder
  opens via row overflow menu.

### 2026-05-11 — Sandbox provisioning + lineage breadcrumb follow-up
- Recovery: pod-rebuild wiped Postgres install + `postgres` system user
  mid-session. Reinstalled PG16, restored role/DB, re-seeded demo project
  + v1+v2 budgets. Documented as Track 8 / pre-launch hardening item in
  `/app/docs/SY_Hub_Phase2_Backlog.md` (Sandbox / pod-runtime stability).
- New: `components/budgets/BudgetLineage.jsx` — slate-500 inline prev/next
  links computed client-side from cached `useProjectBudgets`. Errata E10
  added to Build Pack (backend has no lineage pointer).
- Verified: v1 (Superseded) → "Next version (v2) →", v2 (Draft, current)
  → "← Previous version (v1)". Cross-navigation confirmed.

### 2026-05-10 — Prompt 2.4B-i Budgets Frontend §R0–§R5 ✓
- §R0–R3: stack installed (TanStack Query v5 + Table v8 + dnd-kit + MSW),
  routes wired, Zod schemas + API clients + 14 React-Query hooks against
  the flat backend paths. Erratas E1–E9 (Jest/CRA, flat paths, baseURL,
  hooks D12/D13, perm rename, schema rename, sensitive optional, refetch-
  on-save conflict UX) baked in.
- §R4: BudgetsList (TanStack Table v8) with status + variance badges,
  CreateFromAppraisal dialog (lazy fetch, exclude existing source
  appraisals), refresh-attention button. `budgets.view` perm gate.
- §R5: BudgetHeader (5 tiles + variance row), LifecycleActions
  (Activate / Lock / Unlock / Close / New Version) gated by status +
  backend-verified perms (`budgets.edit`, `budgets.admin`) and
  `useIsDesktop()`, SensitiveBanner for users without
  `budgets.view_sensitive`, ConfirmDialog with reason capture +
  brand-fixed sy-teal/sy-orange.
- New: `lib/budgetCapability.js`, `components/budgets/{StatusBadge,
  VarianceBadge, BudgetsTable, CreateFromAppraisalDialog, ConfirmDialog,
  SensitiveBanner, BudgetHeader, LifecycleActions}.jsx`.
- Build smoke OK: `main.js` 362.82 kB. Lint clean. Verified end-to-end:
  Draft → Active transition via `POST /api/v1/budgets/:id/activate`.
- **NEXT (next session):** §R6 BudgetLinesGrid (dnd-kit + inline edit),
  §R7 LineDrawer + LineItemsPanel + CostCodePicker (refetch-on-save +
  `updated_at` banner per E9), §R8 component tests (Jest/CRA), §R9/R10.

### 2026-05-09 — Prompt 2.4A Budgets Core (Backend) ✓
- Migration 0024_budgets (3 tables, 3 enums, 7 indexes incl. 2 partial unique).
- ORM models, services (`budgets`, `budget_lines`, `budget_errors`).
- 14 REST endpoints under `/api/v1`.
- New permission `budgets.admin`; PM gains `budgets.create`. Total perms 84.
- 44 new tests; full suite 641/641 passing (was 597 baseline).
- See `/app/CHANGELOG.md` §2.4A and `/app/docs/SY_Hub_Phase2_Backlog.md`.

### Earlier (carried in from previous chats)
- 1.x: tenants, entities, users, RBAC, sessions, audit log, MFA, system_config.
- 2.1: SDLT bands, appraisal default settings (reference data).
- 2.2: Appraisals Core (header, units, cost lines, finance facilities,
  RLV solver, 8-step recompute pipeline, state machine, view_financials gating).
- 2.3 retrofit: Submitted/Approved/Rejected/Reopened toggles + scenarios.
- pre-2.4 cleanup: 0023 cascade fix on `appraisal_scenarios`.

## P0 / P1 / P2 backlog (next prompts)

### P0 — current prompt (Chat 17, Prompt 2.4B-i Frontend) — **CLOSED**
- R0–R10 ✓ shipped. See `docs/chat-summaries/chat-17-closing.md`.

### P0 — next prompt (Chat 18)
- **BudgetLinesGrid v2 (BT-style)** — dedicated Build Pack, full audit
  cycle. Replace flat R6 grid with cost-code grouping, 11+ columns,
  heat-mapped variance, sticky column, bulk-select, filtering. See
  `docs/SY_Hub_Phase2_Backlog.md` HIGH-PRIORITY section.
- **Track 8 P0** — wire `provision_postgres.sh` into `on-restart.sh`
  step 0 (retires the recurring operator interruption pattern observed
  6× in Chat 17). 1-2h fix.

### P0 — Chat 19
- Budgets E2E (Playwright) — pushed from Chat 18 to make room for v2.

### P0 — successor prompt (Chat 18, Prompt 2.4B-ii)
- Budgets E2E (Playwright).

### P1 — Phase 2 backlog (12 items, see SY_Hub_Phase2_Backlog.md)
1. AppraisalUnit aggregation in `create_from_appraisal` (post-Prompt 3.x)
2. Per-line `entity_id` sourcing (multi-entity projects)
3. Actuals service (Prompt 2.5)
4. Commitments service (Prompt 2.5)
5. Budget changes / approval flow (Prompt 2.6)
6. Cash-flow `budget_line_periods` (separate prompt)
7. `linked_programme_task_id` FK to `programme_tasks` (Prompt 3.2)
8. Xero hooks (Track 6)
9. `requires_attention` scheduler infra + clauses 2/3
10. `SystemConfig` variance-threshold columns
11. Idempotency keys on `/from-appraisal`, `/new-version`
12. SOX-style author-cannot-activate review (MD/Louise call)

### P2 — debt / future-proofing
- `Project.tenant_id` column (will retire the `hasattr` no-op in services).
- Remaining `ON DELETE RESTRICT` FKs on `appraisal_scenarios`.

## Architecture notes
```
/app/backend/
├── alembic/versions/      # migrations (head: 0024_budgets)
├── app/
│   ├── auth/              # JWT + RBAC + permissions
│   ├── jobs/              # APScheduler-managed background jobs
│   ├── models/            # SQLAlchemy ORM
│   ├── routers/           # FastAPI routers (mounted via server.py)
│   ├── schemas/           # Pydantic request shapes (extra="forbid")
│   ├── services/          # business logic
│   ├── bootstrap.py       # `python -m app.bootstrap` (idempotent pod-start)
│   └── seed_*.py          # reference-data seeds
├── tests/                 # pytest suite (641 tests passing)
├── scripts/seed_test_users.py
└── server.py              # FastAPI app entry (NB: not main.py)
```

## How to run locally
```bash
sudo supervisorctl status               # mongodb, postgres, frontend already up
cd /app/backend && python -m app.bootstrap   # idempotent; bootstraps DB + seeds
sudo supervisorctl start backend
cd /app/backend && pytest tests/ --ignore=tests/test_c3_governance_smoke.py
```
