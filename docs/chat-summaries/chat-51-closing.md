# Chat 51 — Build Pack B88 Pack 2 — Closing Summary

**Pack:** Build Pack B88 Pack 2 · Job-Costing Grid + Two Budget Screens · Backend + frontend
**Scope:** Buildertrend-class grouped Job-Costing grid as the new centrepiece of the budget surface, served as TWO permission-tiered screens (Full Budget for `budgets.view_sensitive` holders, Construction Budget for everyone else with `budgets.view`), with the construction scope **backend-enforced** end-to-end. Project managers drop to Tier 2.
**Status:** COMPLETE. All 3 gates raw-fetch verified on `origin/main`. Live eyeball passed after four iterations (one Pack-2-introduced regression, three pre-existing legacy bugs surfaced by the new flow). Sandbox-only demo seeder shipped to support repeatable §10 live walkthroughs.

## What shipped

### Gate 1 — Backend (migration + scope service + grid endpoint + scope enforcement + PM revocation)

- **Alembic migration `0045_construction_scope`** — adds `cost_code_sections.included_in_construction_scope` (boolean, NOT NULL, default false). Data step backfills `true` for code "4" + every section parented to "4" (guarded for fresh DBs). Second data step **deletes** the `project_manager → budgets.view_sensitive` grant row from `role_permissions` because `seed_rbac._seed_role_permissions` is additive-only and cannot drop the row on warm pods. Down migration drops the column + re-grants PM `view_sensitive`.
- **`app/services/cost_code_scope.py`** (NEW) — `caller_scope(perms)` is the single source of truth for Tier 1 vs Tier 2; `construction_section_ids`, `construction_cost_code_ids`, `assert_line_in_scope` (404 — mirrors cross-tenant convention), `resolve_request_scope` (the `?scope=` clamp).
- **`GET /api/v1/budgets/{budget_id}/grid`** (NEW) — grouped tree (group → subgroup → lines) with rolled-up subtotals + variance band classification re-using `budget_svc._classify_variance` + Tier-1-only `_allocated_sale_price_provisional` slice. `?scope=full|construction` may only NARROW the caller's entitled scope. Empty groups omitted. Orphan lines bucket into a synthetic "Unassigned" node in full scope, excluded in construction. ≤8 queries per request (no N+1).
- **Scope enforcement on EXISTING endpoints** (the leak fix):
  - Line-level money keys promoted out of the `include_sensitive` gate per D4 — visible to ALL callers on IN-SCOPE lines.
  - Header-level cached totals (incl. `total_budget`) now full-scope-only on `_serialise_budget_summary` / `_serialise_budget_detail`. Detail responses additionally filter `lines` to construction-scoped cost codes when scope is construction.
  - `PATCH/DELETE/items` on out-of-scope lines → **404** via `assert_line_in_scope` (mirrors cross-tenant — existence never leaks).
  - `POST /budget-lines/reorder` → **403** for Tier 2 ("full-budget access required").
- **`seed_rbac.py`** — `project_manager` loses `budgets.view_sensitive` at source. Permission count unchanged (136); role count unchanged (10).
- **`scripts/seed_cost_code_structure.py`** — sets the scope flag on INSERT only for code "4" + canonical Construction subgroups (4.00–4.09). Re-runs over existing rows never revert operator scope edits on OTHER sections. Round-trip recovery restores the canonical set when alembic downgrade-then-upgrade wipes the column default (deviation D-Pack2-A).
- **`routers/cost_codes.py`** — `SectionRead` / `SectionCreate` / `SectionUpdate` expose `included_in_construction_scope`; PATCH gate unchanged (`cost_codes.edit`); audit log captures scope-flip events.
- **Test suite (warm DB, 2nd run)**: **1483 passed · 3 xpassed · 0 failed** · `alembic current = 0045_construction_scope (head)` · permissions=136 · roles=10 · PM has view_sensitive=False. Delta vs Pack 1 close: **+34** (18 grid + 16 scope-enforcement).

### Gate 2 — Frontend (two screens, grouped grid, column picker, CSV export)

- **One shell, two screens** — existing `BudgetDetail` page hosts the new grouped grid + a Full / Construction toggle that writes `?scope=construction` into the URL. Tier 1 sees both toggles; Tier 2 sees only Construction (backend clamps; URL-widen attempts silently fail closed).
- **`src/components/budgets/BudgetJobCostingGrid.jsx`** (NEW) — group → subgroup → lines with rolled-up subtotals, sticky code+description columns, sticky header row, variance heat-map (Red/Amber/Green tinted cells with dark text per a11y), collapse/expand at group + subgroup level, column picker with `localStorage` persistence keyed per scope, Tier-1-only computed columns (projected profit / margin %), row-click line edit gated on `budgets.edit` + `isBudgetEditable(status)` that mounts the EXISTING `LineDrawer` (not rebuilt).
- **API + hook + capability** — `lib/api/budgets.js::getBudgetGrid`, `hooks/budgets.js::useBudgetGrid` + scoped query key, `lib/budgetCapability.js::getBudgetScope`/`canSeeFullBudget`.
- **CSV export** on the cost-code admin screen — Export CSV button + `exportCostCodesCsv(tree, codes)` helper. Client-side only (no new backend endpoint), UTF-8 BOM, `SY_cost_codes_YYYYMMDD.csv` filename, sorted by group → subgroup → code.
- **Legacy `BudgetGridV2` family left in tree, unreferenced** — `BudgetGridV2.jsx`, `BudgetGridV2Desktop.jsx`, `BudgetGridMobileReadOnly.jsx`, `BudgetGridToolbar.jsx`, `BudgetGridColumns.jsx`, `BudgetGridHeaderTiles.jsx`, `BulkActionsBar.jsx`, `BulkDeleteConfirmDialog.jsx`, `ColumnVisibilityMenu.jsx`, `ManageViewsDialog.jsx`, `MobileLineDetailDrawer.jsx`, `SaveViewDialog.jsx`, `ViewPresetsDropdown.jsx`, `SORT_KEY_MAP.js`, `PerLineTransactionDrilldown/*` — pending operator deprecation decision. Existing tests retained as a regression net.
- **Test suite**: **94 suites · 802 tests · 0 failed**. Delta vs Pack 1 close: **+29**.

### Gate 3 — Closing docs (this entry + CHANGELOG)

- This file plus `CHANGELOG.md` entry for Chat 51, including the full deviations block (D-Pack2-A through G).
- `docs/SY_Hub_Phase2_Backlog.md` untouched per non-negotiable.

## The four-round eyeball saga

Gate 2's first hand-off shipped the two screens, the grid, the column picker and the CSV export — all green in CI — but four issues surfaced once the operator started clicking:

| Round | Defect | Root cause | Fix |
|---|---|---|---|
| 1 | PM list crash "Expected number, received nan @ total_budget" | Client schema still marked `total_budget` `moneyRequired`; backend §R5 now omits it for Tier 2 | All 7 cached header money keys `.optional()`; 5 schema-shape tests added |
| 1 | Row click on grid did nothing | I missed wiring the existing LineDrawer to `LineRow` onClick | LineDrawer mounted from the grid, gated on `budgets.edit` + `isBudgetEditable(status)`; 5 status-gated tests added |
| 2 | LineDrawer cost-code dropdown empty for every line | **Pre-existing legacy bug.** `CostCodePicker` read `c.id / c.enabled / c.label` but the API returns `cost_code_id / is_enabled / name`. Was silently broken since inception | Canonical field names; 3 picker tests pinning the field-name reads |
| 2 | LineDrawer FTC method "hidden — request elevated access" for super_admin | **Pre-existing stale gate.** `ftc_method` was `view_sensitive`-gated, but per §R5 / D4 it has always been a non-sensitive field returned to all callers | Gate removed; 2 tests asserting visibility regardless of `view_sensitive` |
| 3 (after pod recycle) | "+ Add item" silently broken | **Pre-existing payload bug.** Client sent `display_order` against `CreateBudgetLineItemRequest` which is `extra="forbid"` → 422 every click; the mutation had no `onError` so the failure was swallowed | Drop `display_order` (backend `line_svc.create_item` auto-assigns); add error toast so silent regressions can't hide again; 4 tests |
| 3 | "No items on this line yet" on demo-seeded lines | The demo seeder inserts `budget_lines` via direct SQL, bypassing `line_svc._create_default_items`. The normal create-from-appraisal flow seeds the canonical 4 defaults — verified end-to-end against a fresh project | No fix needed |

Defect #3 (row-click on Superseded budget) was investigated against the live API and cleared as already-correct: `data.budget.status` propagates from the `/grid` response, so the gating is fresh on every render and the component test exercises exactly that code path.

## Deviations (mirror of CHANGELOG block)

- **D-Pack2-A** — Seed restores `included_in_construction_scope=true` on canonical Construction sections (4 + 4.00–4.09) after an alembic round-trip resets the column default; rule unchanged for every other section.
- **D-Pack2-B** — Seed script lives at `backend/scripts/seed_cost_code_structure.py` (pack referenced `scripts/`). No file moved.
- **D-Pack2-C** — Drag-to-reorder dropped from the grouped grid; ordering is now group/code-driven via cost-code admin.
- **D-Pack2-D** — Sandbox demo seeder at `backend/scripts/seed_b88_pack2_demo.py` (idempotent, NOT a migration, NOT run by bootstrap, NOT a test fixture).
- **D-Pack2-E** — Pre-existing `CostCodePicker` field-name bug fixed under Gate 2 follow-up (`cost_code_id` / `is_enabled` / `name`).
- **D-Pack2-F** — Pre-existing LineDrawer `view_sensitive` gate on `ftc_method` / Manual FTC removed (not in §R5 sensitive set). `notes` gate left untouched — operator did not flag it; B93 covers editor rework.
- **D-Pack2-G** — Pre-existing `LineItemsBreakdown.addItem` body sent `display_order` against an `extra="forbid"` schema; fixed by dropping the field and adding an error toast.

## Sandbox demo seeder

`backend/scripts/seed_b88_pack2_demo.py` — idempotent one-shot that wipes any prior 'B88P2 Demo — Pin Oak' project + dependents and re-seeds:

- Project "B88P2 Demo — Pin Oak" + Approved appraisal
- Cost lines spanning section 1 (Land), section 2 (overheads), and three Construction subgroups (4.00 / 4.01 / 4.02)
- Active v1 budget with the canonical heat-map composition:
  - Red 4.00 (Demolition): +18.0% variance
  - Amber 4.01 (Substructure): +5.0% variance
  - Green 4.02 (Superstructure): −8.0% variance
- `test-pm@example.test` promoted to `project_scope='All'` for the session
- MFA wiped on all `test-*@example.test` users

Re-run any time:

```
cd /app/backend && set -a && source .env && set +a && \
  export REACT_APP_BACKEND_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2-) && \
  /root/.venv/bin/python scripts/seed_b88_pack2_demo.py
```

## What was NOT built (per Build Pack §11)

Typed-then-auto-summed group totals · bulk actions · grid filtering · status pills · cost-plan import · budget-from-scratch · mobile rework · pagination / virtualisation · SystemConfig threshold columns · any change to variance band values · any new permission codes · Playwright E2E.

`docs/SY_Hub_Phase2_Backlog.md` untouched per non-negotiable.
