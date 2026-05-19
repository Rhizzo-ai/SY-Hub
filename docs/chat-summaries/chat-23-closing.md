# Chat 23 — closing notes

**Build Pack:** Chat_23_Build_Pack_v_final.md
**Status at close:** STOP gate #9 passed (R8 functional), R9 + R10 complete.
**Acceptance gates:** 38/39 ✓ · 1 documented partial (G38 — see below).

---

## What shipped

### Backend (R1)
| Ref | Change |
|---|---|
| R1.1 | Variance constants 0% / 10%, `_classify_variance` uses `>=` for Red. |
| R1.2 | `_create_default_items` (Materials / Labour / Equipment / Subcontractor) wired into `create_from_appraisal`. Idempotency guard prevents double-creation. |
| R1.3 | Migration 0027 backfills 4 default items on every existing zero-item line. |
| R1.4 | Migration 0028 + `/api/v1/me/preferences/{surface_key}` router. CRUD + saved views + autosave PUT. 14 endpoint tests. |
| R7.3-bk | New `DELETE /api/v1/budget-lines/{line_id}` endpoint (singular per locked decision — frontend fans out sequentially). One audit row per delete with `metadata.kind=line_delete`. 6 endpoint tests. |
| Alembic head | `0028_user_preferences_table` |
| Pytest | 753 → **843** (+90 net across the build pack) |

### Frontend (R2 – R8)
| Ref | Change |
|---|---|
| R2.1 | `@tanstack/react-table ^8.20.0` installed. |
| R2.2 | Budgets routes lazy-loaded via React.lazy + Suspense → `budgets.<hash>.chunk.js`. Main bundle dropped ~29 kB gz. |
| R3 | `BudgetGridV2Desktop` — 12 columns / 6 visible by default / 4 view presets (Quick/Standard/Full/Profit) / variance heat-map / 3-level hierarchy (Category → Line → Items) / column reorder + pin + sort / drag-reorder preserved & disabled when sort active / inline edit removed (drawer-only) / sensitive-field gating on Profit + Margin / `_allocated_sale_price_provisional` server-side allocation gated. |
| R3.10 | 5 header tiles (sensitive-gated). |
| R4 | `BudgetGridDrilldown` mounts in the TanStack expanded-row slot. Breakdown editor + POs stub + Variations stub + **Bills LIVE**. |
| R5 | `NotesCell` — 600ms debounced PATCH with optimistic updates + error rollback. |
| R6 | `useUserPreferences` hooks · autosave (500ms debounce) · Save / Manage Views dialogs · grid state hydrates from snapshot on mount. |
| R7.1 | Line-level row selection (groups + items excluded via `enableRowSelection`). |
| R7.2 | `BulkActionsBar` — Export CSV + Delete + Clear, count badge, over-100 warning. |
| R7.3 | Sequential bulk-delete fan-out (max 100), **live progress meter** ("Deleted X of N…" with partial-failure suffix). Single end-of-loop cache invalidation. sy-orange destructive confirm dialog. |
| R7.4 | Inline RFC-4180 `lib/csv.js::toCsv` (5-line, no papaparse). CSV resolves cost_code FK → human-readable code. Sensitive-field gating enforced at column-construction time (Profit + Margin columns don't exist for non-sensitive users, so they can't land in the CSV). |
| R7.5 | **/api vs /api/v1 prefix audit** (Future_Tasks §11) — fixed silent 404s in `useCostCodes`, `PromoteForm::useEntities`, `ProjectPicker::useProjects`. URL-contract regression pins added per hook. Cost-code on-screen rendering pin added (3 cases) after a regression-investigation gap. |
| R8.1 | `BudgetGridMobileReadOnly` — header tiles (stacked) + search + card list. |
| R8.2 | `MobileLineDetailDrawer` — bottom Sheet, full-viewport, all fields read-only except editable Notes. Sensitive-field gating mirrored from desktop. Per-line drilldown reused. |
| Jest | 151 → **250** (+99 net across the build pack) |
| Bundle | main **395.1 kB gz** (cap 437 kB · headroom 41.9 kB) · budgets chunk **23.89 kB gz** |

### Infrastructure
- `/root/.emergent/on-restart.sh` auto-recovery hook **installed** (was missing — root cause of the 7 container recycles in this chat). Chain: detect missing PG16 → re-install via apt → bootstrap migrations + RBAC seed + test users → soft re-seed R7 spot-check fixture → start backend via supervisor.
- `/app/scripts/seed_r7_spotcheck.sh` — idempotent 10-line, 3-category, mixed-variance Active-budget seed used for STOP-gate spot-checks. Hooked into Step 8 of the on-restart chain.

---

## Acceptance gates (§R10)

| Gate | Status | Notes |
|---|---|---|
| G1 — variance constants 0/10 | ✓ | `services/budgets.py::VARIANCE_RED_PCT = 10` |
| G2 — `>=` for red | ✓ | "variance_pct >= 10 -> Red" |
| G3 — `_create_default_items` wired | ✓ | `services/budget_lines.py:56,206` |
| G4 — 0027 backfill applied | ✓ | alembic head includes 0027 |
| G5 — 0028 user_preferences table | ✓ | table present + 2 rows in dev (autosave from spot-check) |
| G6 — `/me/preferences/...` mounted | ✓ | server.py:158 |
| G7 — alembic head 0028 | ✓ | `0028_user_preferences_table` |
| G8 — backend tests passing | ✓ | **843 passed** (target ~830) |
| G9 — tanstack ^8.20.0 | ✓ | `package.json` |
| G10 — budgets lazy-loaded | ✓ | `budgets.82f02fda.chunk.js` |
| G11 — main bundle ↓ ≥10 kB | ✓ | ~29 kB dropped |
| G12 — BudgetGridV2 replaces v1 | ✓ | v1 grid + sortable row deleted (see G38) |
| G13 — 12 cols / 6 visible | ✓ | `BudgetGridColumns.jsx` + `INITIAL_COLUMN_VISIBILITY` |
| G14 — 4 view presets | ✓ | `ViewPresetsDropdown.jsx` |
| G15 — variance heat-map colours | ✓ | `VarianceCell.jsx` |
| G16 — 3-level hierarchy | ✓ | row-data builder in `BudgetGridV2Desktop.jsx` |
| G17 — categories expanded, items collapsed | ✓ | default expand state |
| G18 — toolbar 5 filters | ✓ | `BudgetGridToolbar.jsx` |
| G19 — column reorder/pin/sort | ✓ | TanStack defaults + persisted prefs |
| G19b — drag-reorder preserved, disabled on sort | ✓ | `SortableLineRowBody` |
| G19c — inline edit removed | ✓ | drawer-only edits |
| G20 — sort at group + line levels | ✓ | TanStack `manualSorting=false` + group rows |
| G21 — Profit/Margin hidden non-sensitive | ✓ | `makeColumns` omits the columns entirely |
| G21b — server attaches `_allocated_sale_price_provisional` | ✓ | sensitive-only |
| G22 — 5 header tiles | ✓ | `BudgetGridHeaderTiles.jsx` |
| G23 — drilldown on chevron | ✓ | TanStack expanded-row slot |
| G24 — Bills live | ✓ | `BillsSection.jsx` |
| G25 — Notes editable desktop + mobile | ✓ | NotesCell receives `canEdit` per-platform |
| G26 — saved views CRUD | ✓ | Save/Manage dialogs |
| G27 — autosave debounced | ✓ | 500ms via `useUserPreferences` |
| G28 — bulk delete + confirm | ✓ | `BulkActionsBar` + `BulkDeleteConfirmDialog` |
| G29 — CSV export visible cols + selected rows | ✓ | with sensitive-field gating + cost-code FK resolution |
| G30 — mobile read-only + Notes editable | ✓ | `BudgetGridMobileReadOnly` + `MobileLineDetailDrawer` |
| G31 — Jest passing ~176+ | ✓ | **250 passed** |
| G32 — bundle ≤ 437 kB | ✓ | **395.1 kB** (41.9 kB headroom) |
| G33 — perms = 86 | ✓ | unchanged |
| G34 — roles = 10 | ✓ | unchanged |
| G35 — CI green | ✓ | both suites green; CI matrix unchanged |
| G36 — no regression in existing endpoints | ✓ | all 753 pre-existing backend tests pass; the +90 are net new |
| G37 — audit on bulk delete + saved-view CRUD, NOT on autosave | ✓ | one audit row per bulk-delete fan-out call; saved-view CRUD audited; autosave PUT is NOT audited |
| **G38 — old v1 files deleted** | **PARTIAL** | `BudgetLinesGrid.jsx` + `SortableLineRow.jsx` **deleted** ✓ · `LineItemsPanel.jsx` **kept** ✗ — still mounted in `LineDrawer.jsx:436` for the drawer's items-tab. Refactor logged as Future_Tasks §13 (P2, ~2 hours: add `initialFocus` to `LineItemsBreakdown`, swap mount, delete file). No functional gap. |
| G39 — chat-23-closing.md committed | ✓ | this file |

**38 / 39 ✓ · 1 documented partial (G38).** Build Pack A is mergeable on the operator's signal.

---

## Deferred (out of Build Pack A scope)

1. **Playwright E2E adaptation** (R9.3 explicitly OUT of scope per spec). The existing flat-grid Playwright specs will go red the moment this merges to `main`. A Build Pack A-followup must port them against the new TanStack grid + mobile card list + drawer.
2. **Mobile shell rework** (Future_Tasks §12, **P1**). R8 is functionally complete, but the surrounding shell (sidebar, top nav, viewport across all surfaces) makes mobile unusable in practice. Dedicated 2-3 day build pack after R10 closes — sized after this one.
3. **`LineItemsPanel.jsx` deletion** (Future_Tasks §13, P2). G38 partial — ~2 hours of refactoring out of closing scope.
4. **`/api` vs `/api/v1` path-prefix drift audit** (Future_Tasks §11, **P1**). Three drifting callers already fixed (`useCostCodes`, `useEntities` in PromoteForm, `useProjects` in ProjectPicker). The remaining audit + the proposed typed-API-client surface to permanently eliminate the bug class still need a dedicated pass.

---

## Operational debt picked up during this chat

- **`/root/.emergent/on-restart.sh` was missing from the pod.** Root cause of every container-recycle data-loss event in this chat (~7 recycles). Reinstalled from `/app/scripts/on-restart.sh.template` and extended with a Step-8 idempotent re-seed of the R7 spot-check fixture. Future recycles are now self-healing.
- **MFA enforcement at role level (super_admin, director, finance) was undocumented.** Now documented in `/app/memory/test_credentials.md` along with the SQL bypass + the recommendation to use `test-pm@example.test` for browser spot-checks (Project Manager role isn't MFA-enforced).
- **Test-pollution between R7 spot-check seed and `test_appraisals.py::TestRetrofit23C1`.** When the R7 fixture is in DB at pytest start, 90 errors cascade. Documented + workaround scripted (wipe before full pytest run).

---

## Next chat-bootable starting point

1. `bash /app/scripts/seed_r7_spotcheck.sh` to re-seed if needed.
2. Login: `test-pm@example.test` / `TestUser-Dev-2026!`.
3. Live preview budget detail: `<REACT_APP_BACKEND_URL>/projects/b2a265ef-dc30-4779-96f6-e139d1881e07/budgets/<current>` (current id printed by seed script).
4. Priority queue: mobile shell rework (P1) · Playwright adaptation (P1) · `/api` prefix audit closure (P1) · LineItemsPanel deletion (P2).
