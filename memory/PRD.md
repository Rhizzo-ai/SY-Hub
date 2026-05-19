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

### 2026-05-19 — Chat 23 Build Pack A §R5 NotesCell upgrade ✓ (STOP gate #6)
- **`NotesCell.jsx` rewrite**: 600ms debounce; rapid typing coalesces to a single PATCH; **Enter** commits immediately, **Shift+Enter** = newline, **Escape** reverts + cancels pending debounce, **Blur** commits immediately; same-value no-op guard; empty string → `notes: null`; **maxLength=500** enforced via textarea attribute; soft counter appears at ≥450 chars.
- **Optimistic + rollback**: leverages existing `usePatchBudgetLine.onMutate/onError`; NotesCell additionally restores its own `committedRef` so the next entry into edit mode shows the pre-failed value. **`sonner.toast.error`** fires on network failure with the server message.
- **Grid wiring**: `BudgetGridColumns.makeColumns` no longer takes `onUpdateNotes` — it forwards `lineId + budgetId` so the cell owns its own mutation. `BudgetGridV2Desktop` dropped the wrapper closure + the redundant `usePatchBudgetLine` import.
- **Tests:** Jest 184 → **196** (+12 NotesCell cases pinning the entire R5 contract — keystroke debounce, Enter/Shift+Enter/Escape/Blur, null-on-empty, no-op guard, counter, maxLength attr, network-failure rollback + toast).
- **Bundle**: main 395.05 kB unchanged; budgets chunk 18.58 → 18.77 kB (+194 B). Cap 437. Headroom **41.76 kB**.
- **Mobile note**: NotesCell IS mobile-editable per Build Pack §R5; the current mobile stub doesn't yet surface it. Reusing this same NotesCell unchanged in the R8 mobile card list.
- **Currently at:** STOP gate #6 — awaiting operator review before R6 (Saved Views CRUD UI + autosave wiring against the R1.4 backend).

### 2026-05-19 — Chat 23 Build Pack A §R4 BudgetGridDrilldown ✓ (STOP gate #5)
- **R4.1 LineItemsBreakdown** (editable 4-type item editor; description/amount/notes inline + `+ Add item` + delete-with-confirmation using `bg-sy-orange` for the destructive confirm).
- **R4.2 / R4.3** PO + Variations empty-state stubs pointing to Prompts 2.5 / 2.6.
- **R4.4 BillsSection LIVE** (6-col table fed by `useActualsForBudgetLine`). Confirmed param name `budget_line_id` (NOT `line_id`) against `routers/actuals.py:65` before wiring. New `BillStatusBadge` with 5-state semantic colour map (Draft/Posted/Paid/Disputed/Void → slate/sky/emerald/rose/zinc).
- **R4.5 BudgetGridDrilldown** wrapper. Mounted via colspan row directly under each expanded line in `BudgetGridV2Desktop` (items no longer attached as flat TanStack sub-rows).
- **3 confirms answered (operator R4 questions)**:
  1. `appraisal.gdv_total` IS the aggregate development revenue (Σ unit.qty × price_per_unit per `app/services/appraisal_calc.py:144-148`). Not per-unit. ✓
  2. `LineDrawer.jsx` retained (482 lines, unchanged). Actions menu still routes non-Notes edits to it. ✓
  3. Test rename: `PM_EMAIL` → `NON_SENSITIVE_EMAIL = test-readonly@example.test`. PM has `view_sensitive`; only `test-readonly` does not. No production rename, just fixture targeting. ✓
- **Future_Tasks §10** logged: MFA-on-test-users runbook is operational debt (P2). Need a `--test-fixture` middleware bypass for `*@example.test` in non-prod envs.
- **Tests:** Jest 172 → **184** (+12: BillsSection 3, Drilldown stubs + BillStatusBadge 7, budgetCategoryGroup regression-guard updated). Backend unchanged (no backend changes in R4).
- **Bundle:** main 395.05 kB gz (+0.08 from R3), budgets chunk 18.58 kB gz (+1.61). Cap 437. Headroom 41.95 kB.
- **Currently at:** STOP gate #5 — awaiting operator review before R5 (Notes inline-edit upgrade: debounce + audit).

### 2026-05-19 — Chat 23 Build Pack A §R3 BudgetGridV2 ✓ (STOP gate #4)
- **R3.9b backend** (`app/routers/budgets.py`): `_attach_provisional_allocation(db, budget, include_sensitive)` computes per-line `appraisal.gdv_total / len(lines)` 2dp; emitted as `_allocated_sale_price_provisional` on every line ONLY when `budgets.view_sensitive`. Underscore-prefix = "computed, not stored". Source field = `gdv_total` (no literal `sale_price` column exists). 4 new tests passing.
- **R3.1 component tree** — 12 new files under `frontend/src/components/budgets/grid/`:
  - `BudgetGridV2.jsx` — top-level (mobile/desktop chooser).
  - `BudgetGridV2Desktop.jsx` — TanStack Table + filter→group→sort pipeline + drag-reorder (sort-gated).
  - `BudgetGridMobileReadOnly.jsx` — R8 stub (card list).
  - `BudgetGridToolbar.jsx` — 5 filters (search, categories, variance band, only-actuals, only-variance) + views menu + column toggle.
  - `BudgetGridHeaderTiles.jsx` — 5 totals (3 hide for non-sensitive).
  - `BudgetGridColumns.jsx` — 12 cols, 6 default-visible; Profit/Margin conditional on `view_sensitive`.
  - `VarianceCell.jsx`, `MoneyCell.jsx`, `NotesCell.jsx`.
  - `ViewPresetsDropdown.jsx` — Quick/Standard/Full/Profit (Profit hidden if not sensitive).
  - `ColumnVisibilityMenu.jsx`.
  - `SORT_KEY_MAP.js` — id→backend translation + `computedLineValue` for 3 synthetic columns. Dev-mode `console.warn` on miss.
- **R3.5 grouping** — new `lib/budgetCategoryGroup.js` with 9-prefix `CATEGORY_BY_PREFIX`.
- **R3.6 default expansion** — categories open on first render; items closed.
- **R3.4 heat-map** — emerald/amber/rose semantic colours; brand `sy-teal`/`sy-orange` NOT used for variance (operator brand-convention check ✓).
- **R3.8 sort + drag-reorder** — TanStack sort applied via `SORT_KEY_MAP`; drag-reorder kept from v1 and disabled when `sorting.length > 0`.
- **R3.9 gating** — `_allocated_sale_price_provisional` stripped from non-sensitive responses; Profit/Margin columns aren't even created for those users.
- **Inline edit** — Notes ONLY (Q7). All other field edits route through the kept-from-v1 `LineDrawer`.
- **Wiring** — `pages/projects/BudgetDetail.jsx` swaps `BudgetLinesGrid` → `BudgetGridV2`.
- **Bundle:** main 394.97 kB gz (+0.17 over R2), budgets chunk 16.97 kB gz (+4.68). Cap 437 kB. Headroom **42 kB** preserved.
- **Tests:**
  - Backend 833 → **837** (+4 R3.9b cases).
  - Frontend Jest 151 → **172** (+21: VarianceCell 5 / budgetCategoryGroup 7 / SORT_KEY_MAP 8 + the original 1).
- **Currently at:** STOP gate #4 — awaiting operator review before R4 (per-line drilldown: BillsSection live, POs/Variations stubs).

### 2026-05-19 — Chat 23 Build Pack A §R2 frontend code-split ✓ (STOP gate #3)
- **Pre-flight verified:**
  - Full backend pytest run: **833 passed / 0 failed / 0 errors / 122.86s** (post fresh bootstrap; the prior session's ~93 errors were stale-state artifacts from a broken prior bootstrap, not real regressions).
  - G33 permissions=86 ✓ (unchanged); G34 roles=10 ✓ (unchanged).
  - `git status` clean — no auto-URL changes to ride along.
- **R0.3 / R2.1** — `@tanstack/react-table@^8.20.0` already present in `frontend/package.json`. No install needed.
- **R2.2** — `frontend/src/App.js`: `BudgetsList` + `BudgetDetail` converted from eager imports to `React.lazy` with the shared `webpackChunkName: "budgets"` magic comment; route elements wrapped in `<React.Suspense fallback={…Loading…}>` mirroring the existing AICapture pattern. (commit `c8acbb4`)
- **Bundle deltas after R2.2:**
  - `main.js`: **424.17 → 394.80 kB gz** (-29.37 kB — 3× the G11 ≥10 kB target)
  - New chunks: `budgets.a76cfc20.chunk.js` 12.29 kB + `981.chunk.js` 18.20 kB
  - Headroom against the 437 kB cap: **42.20 kB** before §R3 ships Grid v2.
- **Jest:** 151/151 passing (33 suites, 23.8s) — no test changes needed.
- **Fix-ups landed alongside (commit `f0c14a0`):**
  - `test_bootstrap.py::test_alembic_heads_helper_returns_single_head` — sentinel `0027_` → `0028_` per the chat-15 §3 convention now that R1.4 advanced the head.
  - `test_migration_0025_actuals.py::test_alembic_head_is_0025_actuals` — same one-character-class head bump.
  - `test_budgets_default_items.py::test_new_version_copies_items_verbatim_no_autocreate` — explicit `db_session.rollback()` before raw-SQL cleanup so the LIFO-order fixture finaliser doesn't deadlock on the FOR-UPDATE lock the test acquired via `new_version`.

### 2026-05-18 — Chat 23 Build Pack A §R1 backend ✓ (STOP gate #2)
- **R1.1 — Variance band update (commit `98ac673`).** `VARIANCE_AMBER_PCT` 5→0; `VARIANCE_RED_PCT` 15→10. `_classify_variance` operator flipped to use `>=` for Red. 6 new fence-post tests in `test_budgets_variance_bands.py` (-5/0/0.001/9.999/10/25 → Green/Green/Amber/Amber/Red/Red).
- **R1.2 — Auto-create 4 default `budget_line_items` on every new `budget_line` (commit `d990bb3` initial + `ba25b65` fix).** `DEFAULT_LINE_ITEMS = ("Materials","Labour","Equipment","Subcontractor")` at `display_order` 0-3, `amount=0`. `_create_default_items` is idempotent (skips when line already has items). Wired into `create_line` (services/budget_lines.py) and `create_from_appraisal` (services/budgets.py). `new_version` intentionally does NOT call the helper — copies source items verbatim. 5 new tests in `test_budgets_default_items.py` covering constant, service-level create, idempotency, and new_version copy semantics.
- **R1.3 — Migration `0027_default_line_items_backfill` (commit `2725bf1`).** Idempotent backfill: SELECT zero-item lines via LEFT JOIN; INSERT 4 defaults at amount=0. Emits a single `Seed_Run` audit row with `metadata.kind='data_backfill'` + row/item counters. Downgrade removes items matching the exact 4-label + amount=0 + display_order 0-3 shape. 4 tests in `test_migration_0027_backfill.py`. Build Pack §R1.3 spec slug was `0027_budget_line_items_backfill`; operator confirmed canonical name stays `0027_default_line_items_backfill` (one-char-class drift, no rename).
- **R1.4 — `user_preferences` table + 6 endpoints (commit `09d3911`).** Migration `0028_user_preferences_table`: id/user_id/surface_key/name/payload JSONB/created_at/updated_at; FK users.id CASCADE; two partial unique indexes (`name IS NULL` slot = 1 current per user/surface; `name IS NOT NULL` slot = 1 named view per user/surface/name); `set_updated_at` trigger. Service `app/services/user_preferences.py` exposes get_current/set_current/list_views/get_view/create_view/update_view/delete_view with ConflictError/NotFoundError. Router `app/routers/user_preferences.py` mounts under `/api/v1/me/preferences/{surface_key}` with 6 endpoints: GET snapshot, PUT autosave (NOT audited), GET/POST/PUT/DELETE named views (audited Create/Update/Delete). 16 API tests + 3 migration smoke tests = 19 new passing.
- **Test counts after R1 (sample):**
  - `test_budgets.py` 76/76 passing
  - `test_budgets_default_items.py` 5/5
  - `test_budgets_variance_bands.py` 6/6
  - `test_migration_0027_backfill.py` 4/4
  - `test_migration_0028_user_preferences.py` 3/3
  - `test_user_preferences_api.py` 16/16
- **Alembic head:** `0028_user_preferences_table`.
- **Currently at:** Build Pack STOP gate #2 — awaiting operator review before R2 (frontend code-split + TanStack Table install + Grid v2 build).

### 2026-05-18 — Chat 22 CI pipeline hardening ✓ CLOSED
- **Anchor (Future_Tasks §3, open since Chat 14):** GitHub Actions CI pipeline (`.github/workflows/ci.yml`) iteratively hardened across 5 red runs to reach a 799/799 green state without depending on `backend/.env` or sandbox-specific absolute paths.
- **Shipped fixes (cumulative):**
  - `backend/requirements-ci.txt` excludes the private `emergentintegrations` package.
  - `frontend/yarn.lock` regenerated + explicitly staged.
  - 7 pre-existing test-drift assertions patched across 5 test files.
  - CI env: `DATABASE_URL` → `postgresql+psycopg://` (psycopg3 driver), `CORS_ORIGINS`, `MFA_ENCRYPTION_KEY` inline (CI-only Fernet key).
  - CI postgres service: `POSTGRES_INITDB_ARGS=--lc-collate=C.UTF-8 --lc-ctype=C.UTF-8 --encoding=UTF8` (Pattern A — pins CI sort order to match sandbox + Python codepoint oracle).
  - `tests/test_bootstrap.py` + `tests/test_migration_0025_actuals.py`: replaced `/app/backend` hardcodes with `str(Path(__file__).resolve().parents[1])` (Pattern B).
- **Final validation:** Full backend suite (`python -m pytest --ignore=tests/test_c3_governance_smoke.py`) runs **799 passed / 0 failed** (108.72s) under `env -i` with the exact 14-var ci.yml block and no `backend/.env`. The handoff's "3 failing tests" report was a misdiagnosis (non-policy-compliant password in prior agent's local replica). See `CHANGELOG.md` Follow-up 5.
- **Backlog (P3, deferred to Future_Tasks polish):**
  - Refactor 19 cosmetic `load_dotenv("/app/backend/.env")` hardcodes across test suite.
  - Decide explicit `COLLATE` for entity `ORDER BY name` for production deployment.
  - Rename 5 test functions still carrying stale literal numbers from drift patches.

### 2026-02-17 — Prompt 2.5C AI Capture Review Surface ✓
- **Frontend + minimal backend chat.** Surface shipped: AI Capture inbox
  list page (`/ai-capture`) + capture-job detail page (`/ai-capture/:jobId`)
  with side-by-side attachment preview / extracted-fields / promote form.
  PromoteForm re-uses 19B's `BudgetLinePicker` (D37); navigates to the
  created Draft actual on success (D44). One new backend endpoint:
  `GET /api/v1/ai-capture-jobs/:id/attachment` (file bytes, auth-gated).
- **B36 outcome: NOT REPRODUCIBLE AT HEAD.** Zero LOC backend change.
  Hypothesised silent fix in chat-19B's `freshActual` factory rework.
  Regression test `tests/test_actuals_attachments.py::TestB36AttachmentRead
  AfterWrite` pins the read-after-write contract; chat-19B's skipped E2E
  delete case un-skipped (E14). See `chat-19c-closing.md` §"B36 RCA".
- **Bundle headroom remaining post-build: 13.01 kB** (423.99 kB vs +17
  hard-cap of 437.00 kB). Jest 88 → **118**; pytest 782 → **790**;
  smoke unchanged 11/11. 6 new Playwright spec files (operator-run).
- Reference: `docs/chat-summaries/chat-19c-closing.md`. 5 implementation
  deviations (E11–E15) captured. 6 new backlog items B37–B42 appended
  verbatim from Build Pack to Phase 2 backlog.

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
