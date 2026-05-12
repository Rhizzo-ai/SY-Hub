# SY Hub — Prompt 2.4B-i Frontend Build Pack v2

**Prompt:** 2.4B-i — Budgets Frontend (Build Pack v2 — audit-corrected)
**Status:** Draft post-audit. Fixes the 9 CRITICAL + 12 HIGH + 8 MEDIUM defects identified in `audit_report.md`. Not yet pasted to Emergent.
**Authoring chat:** Chat 17 (triage)
**Predecessor:** 2.4A Backend (Chat 16, shipped 2026-05-09 — 14 endpoints, 84 perms, migration `0024_budgets`, 664 backend tests passing as of Chat 16.5).
**Successor:** 2.4B-ii — Playwright E2E flows (Chat 18).

**v1 → v2 delta summary:**
- C1 brand-token variants → use `text-white` foreground + `hover:brightness-110` (no missing variant classes).
- C2 sensitive fields → `nullable().optional()` on `ftc_value`, `ftc_method`, `notes`, `cost_code_label`; invented `*_sensitive` fields removed.
- C3 + C4 fixtures + test imports → full `fixtures.js` and `userEvent.setup()` patterns.
- C5 drawer Save → body from `dirtyFields` only + `cost_code_id` defensive filter.
- C6 + C7 cost-code rendering → safe fallback + nullable label.
- C8 + C9 drag-reorder a11y → `KeyboardSensor` + `setActivatorNodeRef`.
- H1–H12 functional gaps → mobile-write gate (`useIsDesktop`), `budgets.read` gate, close-with-dirty confirm, abort-signal threading, used-vs-unused params, etc.
- M1–M9 robustness → form fields disabled during pending, item-delete confirm, bundle baseline capture, vitest config check.

---

## Front matter

### Scope

This Build Pack delivers the **read + light-edit frontend** for the Budgets module against the existing 2.4A backend. Scope is everything a director / finance / PM / contracts manager needs to *use* a budget through its lifecycle on a desktop browser, plus a strict read-only floor on mobile so site staff can sanity-check numbers without writing.

**In scope:**

1. Routing — `/projects/:projectId/budgets` (list) and `/projects/:projectId/budgets/:budgetId` (detail) under the existing authenticated app shell.
2. **API client layer** — typed wrappers around all 14 endpoints from 2.4A, riding the existing cookie-only `lib/api.js`. Abort-signal threading for query cancellation.
3. **Budgets list view** — TanStack Table with status / variance / current-budget columns, filterable by project, with create-from-appraisal entry point.
4. **Budget detail view** — header (totals, status, FFC vs current, variance band) + lines grid (drag-orderable, inline-edit) + line drawer (rhf+Zod, explicit Save) + items sub-list inside the drawer.
5. **State-machine controls** — Activate / Lock / Unlock / Close / New Version buttons gated by status + permission, with sy-orange destructive-confirm dialogs for Unlock / Close / New Version.
6. **Optimistic vs server-confirmed split** per locked decision (chat-16.5 §4):
   - **Optimistic:** description, notes, % complete, drag-reorder.
   - **Server-confirmed:** FTC method change, lock/close state, line create/delete, threshold-cross writes, cost-code reassignment.
7. **Concurrency UX** — line drawer is explicit-Save; line-level version stamps; conflict toast on stale write with "Reload" affordance.
8. **Sensitive-field gating** — UI gracefully renders when backend strips fields for users without `budgets.view_sensitive`. No client-side leakage.
9. **Brand-token application** — Save / Create / Lock buttons → `bg-sy-teal text-white`; force-Unlock and destructive confirms → `bg-sy-orange text-white`; slate-900 / shadcn defaults elsewhere. Hover via `hover:brightness-110`.
10. **Accessibility** — drag-reorder works with keyboard (KeyboardSensor + sortable coordinate getter); proper drag-handle activator wiring; ARIA labels on every interactive icon.
11. **Mobile read-only floor** — `useIsDesktop` hook gates every write path: inline edits, drawer Save, lifecycle buttons, drag-reorder. On `<md`, every mutation is disabled.
12. **Component tests** — 27 functions across rendering, state-machine UI, line CRUD, items, reorder, sensitive gating, optimistic flow, conflict handling, mobile gate. (Vitest + React Testing Library + MSW. Test runner verified in §R0.)

**Out of scope (explicit, not deferred bugs):**

- **Playwright E2E flows.** Belong in 2.4B-ii (Chat 18).
- **Mobile *write* paths.** Mobile is read-only floor (locked decision #5).
- **KPI / dashboard surfaces.** A separate prompt scopes those (2.4A §3 declined the in-line KPI offer).
- **Activity timeline / audit log surfacing.** Detail-endpoint payload contains audit-log refs; rendering them is a Chat 18+ task once 2.5 (actuals/commitments) lands.
- **CSV / XLSX import / export.** Future.
- **Programme-task linkage UI.** `linked_programme_task_id` is in the schema (Phase 2 backlog #5) but no programme module exists yet.
- **Stale-data scheduler.** `requires_attention` clauses 2 (stale actuals) + 3 (overdue change orders) are gated on Prompts 2.5 and 2.6.

### Acceptance criteria

| # | Criterion | Verification method |
|---|---|---|
| 1 | TanStack Query v5 + TanStack Table v8 + dnd-kit installed; lockfile updated; no peer-dep conflicts | §R1 |
| 2 | Routes live at `/projects/:projectId/budgets[/:budgetId]`; protected by existing auth shell | §R2 |
| 3 | All 14 endpoints from 2.4A reachable via typed `useBudgets*` hooks; cookie auth preserved; abort signals threaded | §R3 |
| 4 | Budgets list renders, filters, sorts; status + variance badges correct per backend payload; `budgets.read` gate enforced | §R4 |
| 5 | Budget detail renders header (totals, FFC, variance band), lines grid, items list inside drawer | §R5, §R6, §R7 |
| 6 | Lifecycle buttons gated by status + perm; sy-orange destructive-confirm on Unlock + Close + New Version with reason capture | §R5 |
| 7 | Line drawer is explicit-Save; body built from `dirtyFields` only + version + cost-code defensive filter; 409 surfaces sonner toast with "Reload" affordance; close-with-dirty confirms | §R7 |
| 8 | Description / notes / % complete / drag-reorder use optimistic updates with rollback on error; FTC method / lock-state / line CRUD / threshold-cross / cost-code reassignment are server-confirmed | §R6, §R7 |
| 9 | Sensitive-field schema strips gracefully (nullable+optional); render shows "—" for omitted fields | §R3, §R5, §R6 |
| 10 | Brand classes: `bg-sy-teal text-white` for Save/Create/Lock; `bg-sy-orange text-white` for destructive confirms; `hover:brightness-110` everywhere — no `-hover` or `-foreground` token suffixes | §R4–R7 |
| 11 | Mobile (`<md`): list and detail render; **every** mutation gated behind `useIsDesktop()` — inline edits, drag-reorder, Save, lifecycle buttons all disabled | §R4–R7 |
| 12 | Drag-reorder: keyboard-accessible (KeyboardSensor); proper activator wiring; bulk endpoint `/lines/reorder` (D8 / STOP #32 dependency) | §R6 |
| 13 | Component test count ≥ 27 functions; vitest run green; full fixtures + imports paste-ready | §R8 |
| 14 | No Playwright in this prompt; no localStorage writes for auth; no `*_sensitive` invented fields | §R0 baseline + §R3 + §R8 |
| 15 | CHANGELOG entry under §2.4B-i with deviations and bundle-size delta | §R10 |

### Locked decisions inherited (chat-16.5 §4)

1. Build Pack length 2,000–2,400 (v2 acknowledges overrun — see §"Length disposition").
2. Audit cycles iterate until bulletproof, no fixed cap.
3. Optimistic split as listed above.
4. Concurrent edit protection: explicit Save in line drawer + line-level version stamps + conflict toast.
5. Mobile = read-only floor; desktop-primary.
6. Stack: TanStack Query + TanStack Table to be installed in this prompt; rhf + Zod already present; sonner for toasts; full shadcn/ui set available.
7. No Playwright in 2.4B-i (Chat 18 covers E2E).
8. Brand tokens applied here: `bg-sy-teal` for Save/Create/Lock; `bg-sy-orange` for destructive confirms.

### Deviations / open questions

These are points where the Build Pack makes an assumption that should be sanity-checked against the live tree before paste. Each has a chosen default.

- **D1.** Test runner assumed to be **vitest** + `@testing-library/react` + `@testing-library/user-event@14` + `msw@2`. R0 confirms via package.json + vite.config.js. If Jest, swap `vi` → `jest` (no structural changes).
- **D2.** Path alias assumed `@/` rooted at `frontend/src/`. R0 confirms via `tsconfig.json` / `jsconfig.json`. If different, all imports across §R3–R7 swap.
- **D3.** `lib/api.js` assumed to expose an axios instance with `withCredentials: true` and base URL `/api/v1`. R0 confirms by `cat`.
- **D4.** Routes nest under `<Route path="projects/:projectId" element={<ProjectDetail />}>`. If routing is flat, §R2 changes route declaration only; pages are unchanged.
- **D5.** `useAuth()` exposes `{ user: { id, email, permissions: string[] } }`. If shape differs, only `lib/perms.js` adapts; all call sites use `hasPerm()`.
- **D6.** **TanStack Table v8** chosen (current major). R0 confirms no v7-pinned dependency.
- **D7.** **Brand-token surface — see C1 fix.** Tailwind currently has only base tokens (`sy-teal`, `sy-orange`, `sy-grey`) per chat-16.5; v2 uses `bg-sy-teal text-white` + `hover:brightness-110`. **No** `-hover` or `-foreground` Tailwind classes referenced. R0 confirms by grepping `tailwind.config.js` for color extensions.
- **D8.** **Drag-reorder bulk endpoint (STOP #32 — unchanged from v1):** `POST /budgets/{id}/lines/reorder` is **assumed to exist**. R0 grep'd against `backend/app/routers/budgets.py`. If absent, choose path:
  1. **Preferred:** request a backend-add patch as a pre-prompt.
  2. **Fallback:** disable drag-reorder; log backlog item.
- **D9.** Threshold-cross writes server-confirmed (variance band recomputed server-side).
- **D10.** Cost-code reassignment server-confirmed (B6 partial unique index can 409).
- **D11.** **Sensitive-field handling:** v2 schema treats `ftc_value`, `ftc_method`, `notes` as `.nullable().optional()` so backend strip → graceful render. No client-side computed sensitivity.
- **D12.** **`useApprovedAppraisals(projectId, { enabled })`** assumed signature. The `enabled` flag avoids fetching until dialog opens. If real hook is `({ enabled? } = {})`, this works as-is; if `(projectId, options)` with different keys, a thin wrapper is required.
- **D13.** **`useCostCodes(projectId)`** from Foundation 1.6 assumed to expose `{ data: { id, code, label, enabled }[], isLoading }`. CostCodePicker component shipped with a graceful "Loading…" + missing-label fallback.
- **D14.** **`@/components/ui/sonner`** assumed to be the shadcn Toaster wrapper. If absent, R1 ships a 12-line wrapper.

---
## ⚠️ ERRATA — Chat-18 §R0 decisions (locked in before implementation)

The §R0 baseline (Chat 18, 2026-05-10) surfaced four deviations from the
assumptions baked into §R1–§R8 below. The operator confirmed the resolution
for each. **These supersede any contradicting text in later sections.**

### E1 — Test runner: Jest via `craco test` (NOT vitest)
The frontend is CRA + Craco (react-scripts 5.0.1), not Vite. D1 anticipated
this. Concrete swaps throughout §R1, §R8:
- Skip the `yarn add -D vitest@^2.0.0 ...` block in §R1.4.
- No `vite.config.js` test block — does not exist.
- `import { describe, it, expect, vi, ... } from 'vitest'` → drop the
  vitest import; CRA's Jest provides `describe/it/expect` as globals.
- `vi.fn()` → `jest.fn()`, `vi.mock(...)` → `jest.mock(...)`.
- Setup file lives at `src/setupTests.js` (CRA picks it up automatically),
  NOT `src/test/setup.js`. Body:
  ```js
  import '@testing-library/jest-dom';
  import { mockMatchMedia } from './test/renderWithProviders';
  afterEach(() => mockMatchMedia(true));
  ```
- `import.meta.env.DEV` (Vite syntax in §R1.7 `main.jsx`) →
  `process.env.NODE_ENV !== 'production'` (CRA-compatible).
- Test invocation: `yarn test --watchAll=false` (CRA) instead of
  `yarn test --run` (vitest).
- `jsdom` is CRA's default test env — no extra install.

### E2 — Endpoint paths: flat backend convention
The 2.4A backend uses **flat** line/item paths. The Build Pack §R3.1 nested
form is incorrect. Use these in §R3.3 client functions and §R8.3 MSW handlers:

| # | Build Pack (nested) | Actual (flat) |
|---|---|---|
| 9 | `PATCH /budgets/:b/lines/:l` | `PATCH /budget-lines/:l` |
| 10 | `POST /budgets/:b/lines/:l/items` | `POST /budget-lines/:l/items` |
| 11 | `PATCH /budgets/:b/lines/:l/items/:i` | `PATCH /budget-line-items/:i` |
| 12 | `DELETE /budgets/:b/lines/:l/items/:i` | `DELETE /budget-line-items/:i` |
| 13 | `GET /budgets/:b/lines/:l/items` | `GET /budget-lines/:l/items` |
| 15 | `POST /budgets/:b/lines/reorder` | `POST /budget-lines/reorder` |

Hook signatures keep `budgetId` for cache-key scoping even though URLs drop it.
MSW handlers in §R8.3 also drop the budget segment.

### E3 — `lib/api.js` baseURL adapter
`lib/api.js` is axios + `withCredentials: true` with **baseURL = `/api`**
(not `/api/v1`). All callers prepend `/v1/...` manually. New §R3 client
functions must do the same: `api.get('/v1/projects/${projectId}/budgets')`,
NOT `api.get('/projects/${projectId}/budgets')`. MSW handlers stay at
`/api/v1/...` because axios produces the full URL.

### E4 — STOP #32 resolved: backend `/budget-lines/reorder` shipped
The bulk-reorder endpoint was added in commit `d20dfd5`
(`feat(2.4A.1): bulk-reorder lines endpoint`) as a precursor patch.
Shape:
```
POST /api/v1/budget-lines/reorder
Body: { budget_id: UUID, ordered_line_ids: UUID[] }
Auth: budgets.edit
Returns: refreshed budget detail (mirrors lifecycle endpoints)
Status map: 400 partial/duplicate/foreign · 403 perm · 404 unknown · 409 locked
```
The frontend `useReorderBudgetLines` hook in §R6 invalidates the
`['budget', budgetId]` key on success and rolls back optimistic updates on
failure. Body uses `ordered_line_ids` (snake_case) to match backend Pydantic.

### E5 — D12 / D13 hook wrappers shipped in §R3
`useApprovedAppraisals` and `useCostCodes` do not exist in the current
tree. Thin TanStack Query wrappers are written as part of §R3, at:
- `frontend/src/hooks/appraisals.js` — `useApprovedAppraisals(projectId, { enabled })`
- `frontend/src/hooks/costCodes.js` — `useCostCodes(projectId)`
Both use the existing API endpoints. See §R3 implementations for details.

### E6 — Tailwind brand tokens have variant sub-keys (DEFAULT/hover/foreground)
The tailwind.config.js `sy-teal` and `sy-orange` namespaces have nested
`DEFAULT`, `hover`, `foreground` keys backed by CSS variables. The Build
Pack's "use `bg-sy-teal text-white hover:brightness-110`" rule still holds
(simpler + brightness-110 is more reliable than the hover token), but
the assertion that variant classes "don't exist" in §R0 STOP gate is
factually wrong. Do NOT introduce variant classes in new code; existing
references in legacy components stay as-is.

### E7 — Backend response shape differs significantly from §R3.2 schemas
The Zod schemas in §R3.2 use invented field names that do not exist in
the backend serialiser (verified against `backend/app/routers/budgets.py`
`_serialise_*` at 2026-05-10). Per the operator's hard rule "the backend
is the source of truth", §R3.2 is **superseded** by the schemas in
`frontend/src/lib/schemas/budgets.js`. Concrete renames the components
in §R4–§R7 must respect (use the right-hand name throughout):

| §R3.2 (incorrect) | Actual backend |
|---|---|
| `BudgetLineItem.unit_cost` | `rate` |
| `BudgetLineItem.position` | `display_order` |
| `BudgetLine.description` | `line_description` |
| `BudgetLine.position` | `display_order` |
| `BudgetLine.actuals_total` | `actuals_to_date` *(sensitive)* |
| `BudgetLine.ffc` | `forecast_final_cost` *(sensitive)* |
| `BudgetLine.variance_value` *(always)* | `variance_value` *(sensitive)* |
| `BudgetLine.variance_pct` *(always)* | `variance_pct` *(sensitive)* |
| `BudgetLine.ftc_value` | _does not exist_ |
| `BudgetLine.version` | _does not exist_ |
| `BudgetLine.cost_code_label` | _join client-side via `useCostCodes`_ |
| `Budget.appraisal_id` | `source_appraisal_id` |
| `Budget.total_original_budget` | `total_budget` |
| `Budget.total_actuals` *(always)* | `total_actuals` *(sensitive)* |
| `Budget.total_cni` *(always)* | `total_committed_not_invoiced` *(sensitive)* |
| `Budget.total_ftc` | `total_forecast_to_complete` *(sensitive)* |
| `Budget.total_ffc` *(always)* | `forecast_final_cost` *(sensitive)* |
| `Budget.total_variance` *(always)* | `variance_vs_budget` *(sensitive)* |
| `Budget.total_variance_pct` *(always)* | `variance_pct` *(sensitive)* |
| `Budget.total_variance_status` | _not on header (line-level only)_ |
| `Budget.activated_at` | _does not exist_ (use `created_at`) |
| `Budget.requires_attention` *(header)* | _line-level only_ |
| `Budget.superseded_by_id` | _not in serialiser_ |
| Permission `budgets.read` | `budgets.view` |
| List response — bare array | `{ project_id, items, count }` |
| `VarianceStatus = On_Track/Warning/Critical` | `Green/Amber/Red` |
| `FTCMethod = Budget_Remaining/Manual/Pct_Complete/Locked` | `Manual/Budget_Remaining/Committed_Only/Percentage_Complete` |

### E7.1 / D12.1 — Appraisals endpoint has no query params
The §R4.5 design assumed `GET /v1/projects/:id/appraisals` accepts
`governance_status=Approved` + `not_linked_to_current_budget=true`. The
actual endpoint accepts **no query params** (verified
`backend/app/routers/appraisals.py:510-527`). `useApprovedAppraisals`
falls back to client-side filtering in its `select` transformer. Callers
that need to exclude already-linked appraisals pass an
`existingSourceAppraisalIds: Set<UUID>` derived from the project's
budgets list.

### E13 — Demo seed must use `ftc_method = 'Budget_Remaining'`, not `'Manual'`
The chat-17 demo SQL (re-run after every pod recycle) seeded
budget_lines with `ftc_method='Manual'` and `forecast_to_complete=0`.
Backend recompute (correctly) accepts the Manual stored value as
authoritative — so FFC=0 for every line, variance=-100% per line,
Red pills everywhere on a Draft budget with no spend. Operator
surfaced as a possible 2.4A backend bug after R8 close; root cause
was the seed data, not the business logic.

**Resolution:** lines must seed with `ftc_method='Budget_Remaining'`
and `forecast_to_complete = current_budget`. Backend recompute then
yields the realistic Draft-budget shape (FFC = current_budget,
variance=0, Green pills). Codified in
`/app/scripts/seed_demo_budget.sh` (committed to repo, idempotent,
survives pod recycles).

The backend `_classify_variance` arithmetic + `recompute_line` for
Budget_Remaining mode (`max(0, current − actuals − committed)`)
verified correct against `backend/app/services/budgets.py:189-204`.
No 2.4A backend change required.

---

### E12 — Backend `variance_status` is asymmetric (under-budget always Green)
Backend `_classify_variance` (`backend/app/services/budgets.py:155-166`)
returns Green for ANY `variance_pct <= 0` by explicit design — the
docstring states *"Negative or zero variance (under or on budget)
=> Green."*

This conflicts with operator-stated semantic: **|pct| > 10 = Red
regardless of sign**, because a line dramatically under budget is
typically a data-quality signal (wrong FTC method, stale line, missing
commitment), not "we saved 99% of the budget".

Surface symptom (Chat 17 R8 click-test): the header variance pill
showed Red (uses client-side `deriveVarianceStatus(abs(pct))`) while
line pills showed Green (used backend `line.variance_status`) for
the SAME budget.

**Resolution:** Frontend re-derives line band client-side via
`deriveVarianceStatus(Number(line.variance_pct))` in
`components/budgets/SortableLineRow.jsx`. No backend migration. The
backend's `variance_status` column stays asymmetric but the frontend
ignores it for display. Backend uses it internally to flag
`requires_attention`; the asymmetry there is a separate concern
captured in `SY_Hub_Phase2_Backlog.md` (under-budget anomalies
currently don't trigger attention flagging).

Unit test coverage added in
`components/budgets/__tests__/VarianceBadge.test.jsx`:
0%, ±1%, ±2 (boundary), ±5%, ±10 (boundary), ±11%, ±50%, ±100%,
±150%, null, NaN, string-coercion-safety.

---

### E11 — Line items field is `rate`, not `unit_cost`
The §R7.4 LineItemsPanel spec used `unit_cost` for the per-unit price.
Backend (verified `backend/app/schemas/budgets.py:48-66`) uses **`rate`**.
Backend also REQUIRES `amount` on `CreateBudgetLineItemRequest` — it is
NOT auto-derived from `quantity * rate`. The component computes
`amount = qty * rate` when both are numeric at add-row submit time and
posts both fields; users can subsequently edit `amount` directly via
inline edit if they need to break the qty*rate relationship.

---

### E10 — Budget lineage is computed client-side (no backend pointer)
The §R5.2 BudgetHeader design assumed a `superseded_by_id` field on the
budget detail payload to render a "Superseded by → newer version" link.
Backend serialiser (`_serialise_budget_detail`, verified 2026-05-11) does
NOT expose any lineage pointer — there is no `superseded_by_id`, no
`previous_version_id`, no `supersedes_id`. The only lineage signal in
the payload is the (`project_id`, `version_number`, `status`,
`is_current`) tuple, plus the audit-log entry written at
`new-version` time (not in the budget payload).

Per operator instruction (chat 17, 2026-05-11):
> "If the backend doesn't surface the back-link... only the forward link
> superseded_by_id — note as E10 in errata and ship forward-only. Don't
> extend backend for this."

Resolution: lineage is computed entirely on the client from the
project's full budget list (already fetched + cached by
`useProjectBudgets`). The header reuses the cached query; no extra
network round-trip. Forward pointer = the next budget by version_number
in the same project (typically the `is_current=true` row when viewing a
superseded version). Back pointer = the previous budget by
version_number. When there's exactly one budget in the project, no
lineage row renders. Renders inline under the title, slate-500,
data-testids `budget-lineage-prev` / `budget-lineage-next`.

If backend later adds the pointer (preferred per audit), the component
falls back to the inline computation; the field can be added without
component changes.

---



## §R0 — Preflight / baseline

### R0.1 — Sandbox provisioning check (fresh-fork only)

```bash
test -f /etc/supervisor/conf.d/supervisord.conf && \
  grep -q '\[program:postgres\]' /etc/supervisor/conf.d/supervisord.conf && \
  echo "Provisioned ✓" || echo "NOT PROVISIONED — run /app/backend/app/bootstrap.py runbook"
```

If not provisioned, stop and run the runbook. Continuing sessions skip this.

### R0.2 — Baseline capture (record values; don't mutate)

```bash
cd /app
git pull --ff-only origin main
git rev-parse HEAD                                      # record SHA
git status                                              # expect clean

cd /app/backend
python -m app.bootstrap                                  # expect rc=0
alembic current                                          # expect 0024_budgets
python -m pytest tests/ \
  --ignore=tests/test_c3_governance_smoke.py -q          # expect 664 passed

cd /app/frontend
node -v                                                  # record
yarn -v                                                  # record

# Frontend dependency audit
cat package.json | python -c "
import json, sys
d = json.load(sys.stdin)
deps = {**d.get('dependencies', {}), **d.get('devDependencies', {})}
print('@tanstack/react-query:', deps.get('@tanstack/react-query', 'ABSENT'))
print('@tanstack/react-table:', deps.get('@tanstack/react-table', 'ABSENT'))
print('@dnd-kit/core:        ', deps.get('@dnd-kit/core', 'ABSENT'))
print('@dnd-kit/sortable:    ', deps.get('@dnd-kit/sortable', 'ABSENT'))
print('vitest:               ', deps.get('vitest', 'ABSENT'))
print('jest:                 ', deps.get('jest', 'ABSENT'))
print('msw:                  ', deps.get('msw', 'ABSENT'))
print('react-hook-form:      ', deps.get('react-hook-form', 'ABSENT'))
print('zod:                  ', deps.get('zod', 'ABSENT'))
print('sonner:               ', deps.get('sonner', 'ABSENT'))
print('axios:                ', deps.get('axios', 'ABSENT'))
"

# Bundle baseline (for later delta)
yarn build 2>&1 | tail -20    # capture build output sizes
```

Record the existing tree:

```bash
# lib/api.js — confirm cookie-only axios
cat frontend/src/lib/api.js | head -40

# AuthContext shape
grep -n 'user\.' frontend/src/contexts/AuthContext.jsx | head

# Path alias resolution
cat frontend/jsconfig.json 2>/dev/null || cat frontend/tsconfig.json | python -c "
import json, sys, re
# strip JSON5 comments
raw = sys.stdin.read()
raw = re.sub(r'//.*', '', raw)
raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.S)
d = json.loads(raw)
paths = d.get('compilerOptions', {}).get('paths', {})
print('paths:', paths)
"

# Tailwind colour extensions — confirm token names
grep -A 30 'extend' frontend/tailwind.config.js | head -50

# Vitest config
grep -A 10 'test' frontend/vite.config.js | head -20

# Sonner Toaster wrapper
ls -la frontend/src/components/ui/sonner.* 2>/dev/null
```

### R0.3 — Decision gates (resolve before R1)

| Gate | Command / check | Pass | Fail action |
|------|-----------------|------|-------------|
| TanStack Query already installed | grep package.json | skip R1.1 | run R1.1 |
| TanStack Table already installed | grep package.json | skip R1.2 | run R1.2 |
| `vitest` in devDependencies | grep package.json | proceed §R8 as written | swap test runner imports throughout |
| `vite.config.js` has `test:` block | grep | proceed | add the block in R1 |
| `lib/api.js` exports axios with `withCredentials` | cat | reuse in §R3 | STOP — backend-add needed |
| Path alias `@/` → `src/` | tsconfig/jsconfig paths | proceed | adjust §R3–R7 imports |
| Tailwind config has only base `sy-*` tokens (no `-hover` / `-foreground`) | grep | proceed (D7 brand approach) | use existing variants if present |
| Sonner Toaster wrapper at `@/components/ui/sonner` exists | ls | proceed | create the 12-line wrapper in R1 |
| `bulk reorder` endpoint `/api/v1/budgets/:id/lines/reorder` | grep `/lines/reorder` in `backend/app/routers/budgets.py` | proceed §R6 reorder | escalate D8 — backend extension before §R6 |
| `useApprovedAppraisals` hook from 2.3 | grep `useApprovedAppraisals` in `frontend/src/hooks/` | proceed | wrap or adapt in §R4.5 |
| `useCostCodes` hook from 1.6 | grep `useCostCodes` in `frontend/src/hooks/` | proceed | wrap or adapt in §R7.2 |

### R0.4 — Self-report template (fill at chat-end ritual; full version in §R9)

```
### R0 — Baseline (frontend)
- git SHA before any work: <SHA>
- backend bootstrap rc / alembic / pytest: <0 / 0024_budgets / 664 passed>
- frontend dependencies present: <list ABSENT items>
- vitest config present: <yes / no>
- lib/api.js shape: <axios + withCredentials + /api/v1 base | other>
- path alias: <@→src | other>
- tailwind tokens registered: <sy-teal,sy-orange,sy-grey | also -hover/-foreground>
- sonner Toaster wrapper at @/components/ui/sonner: <present | created>
- /lines/reorder backend endpoint: <present | added | fallback used>
- useApprovedAppraisals hook signature: <{ projectId, { enabled } } | other>
- useCostCodes hook signature: <{ projectId } returning { data, isLoading } | other>
- bundle size before any work: <KB / KB gzipped>
```

Once R0 is captured cleanly and every gate has resolved, proceed.

---
## §R1 — Stack install + smoke

### R1.1 — Install TanStack Query v5

```bash
cd /app/frontend
yarn add @tanstack/react-query@^5.59.0 @tanstack/react-query-devtools@^5.59.0
```

v5 stabilised the object-form API (`useQuery({ queryKey, queryFn, signal })`). Don't auto-upgrade to v6 mid-build.

### R1.2 — Install TanStack Table v8

```bash
yarn add @tanstack/react-table@^8.20.0
```

### R1.3 — Install dnd-kit (only if R0 found absent)

```bash
yarn add @dnd-kit/core@^6.1.0 \
         @dnd-kit/sortable@^8.0.0 \
         @dnd-kit/utilities@^3.2.2
```

### R1.4 — Install / verify test toolchain (only if R0 found absent)

```bash
# Only if vitest absent
yarn add -D vitest@^2.0.0 \
            @testing-library/react@^16.0.0 \
            @testing-library/user-event@^14.5.0 \
            @testing-library/jest-dom@^6.4.0 \
            msw@^2.4.0 \
            jsdom@^25.0.0
```

If `vite.config.js` lacks a `test:` block, append:

```js
// vite.config.js — append inside defineConfig
import { defineConfig } from 'vite';

export default defineConfig({
  // ...existing config
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
  },
});
```

```js
// frontend/src/test/setup.js (NEW)
import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { mockMatchMedia } from './renderWithProviders';

// Reset matchMedia to desktop default after each test to prevent leakage
// between tests in the same file. Tests that need mobile must call
// mockMatchMedia(false) explicitly at the top of the test.
afterEach(() => {
  mockMatchMedia(true);
});
```

### R1.5 — Sonner Toaster wrapper (only if R0 found absent)

shadcn convention. Skip if `@/components/ui/sonner` exists.

```jsx
// frontend/src/components/ui/sonner.jsx (NEW if absent)
import { Toaster as SonnerToaster } from 'sonner';

export function Toaster(props) {
  return (
    <SonnerToaster
      position="top-right"
      richColors
      closeButton
      toastOptions={{
        classNames: {
          toast:
            'group toast group-[.toaster]:bg-white group-[.toaster]:text-slate-900 group-[.toaster]:border-slate-200 group-[.toaster]:shadow-lg',
          description: 'group-[.toast]:text-slate-500',
        },
      }}
      {...props}
    />
  );
}
```

### R1.6 — QueryClient setup

```js
// frontend/src/lib/queryClient.js (NEW)
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,            // 30s — coarse cache for nav-back snappiness
      gcTime: 5 * 60_000,           // 5min — drop after that
      refetchOnWindowFocus: true,   // catch out-of-band edits from another tab
      retry: (failureCount, error) => {
        // Don't retry 4xx — they're deterministic.
        const status = error?.response?.status;
        if (status && status >= 400 && status < 500) return false;
        return failureCount < 2;
      },
    },
    mutations: {
      retry: false,                  // never retry mutations — may not be idempotent
    },
  },
});
```

### R1.7 — Wire QueryClient + Toaster into the app root

```jsx
// frontend/src/main.jsx (modified)
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { queryClient } from '@/lib/queryClient';
import { Toaster } from '@/components/ui/sonner';
// ...existing imports

root.render(
  <QueryClientProvider client={queryClient}>
    <ExistingProviders>
      <App />
      <Toaster />
    </ExistingProviders>
    {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
  </QueryClientProvider>
);
```

**Wrap order:** `QueryClientProvider` outside everything except React's StrictMode wrapper. AuthProvider goes inside (it reads cookies via `lib/api.js`, not from query cache).

### R1.8 — Brand-token verification (D7)

Per chat-16.5, `tailwind.config.js` registers base tokens only:

```js
// tailwind.config.js — already on main, do not change
extend: {
  colors: {
    'sy-teal':   'var(--sy-teal)',
    'sy-orange': 'var(--sy-orange)',
    'sy-grey':   'var(--sy-grey)',
  },
}
```

This means available Tailwind classes are `bg-sy-teal`, `text-sy-teal`, `border-sy-teal` (and the orange/grey equivalents) — **but not** `bg-sy-teal-hover` or `text-sy-teal-foreground`. v2 uses the safe pattern:

```jsx
// Action (Save / Create / Lock):
className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"

// Destructive (Unlock / Close / New Version / item delete):
className="bg-sy-orange text-white hover:brightness-110 active:brightness-95"
```

`brightness-110` is a Tailwind core utility (no extra config); white text on the brand colours has been validated for AA contrast in the brand spec (sy-teal #0F6A7A → 7.4:1, sy-orange #FC7827 → 4.6:1).

If the audit later registers `-hover` / `-foreground` variants in `tailwind.config.js`, v2 swaps with a single sed-style replacement.

### R1.9 — Smoke

```bash
cd /app/frontend
yarn build           # expect clean
yarn dev             # expect existing app loads, devtools toggle bottom-right
```

### R1.10 — Lockfile commit boundary

```bash
git add package.json yarn.lock \
        src/lib/queryClient.js src/main.jsx \
        src/test/setup.js \
        src/components/ui/sonner.jsx
git commit -m "chore(2.4B-i): install TanStack Query v5 + Table v8 + dnd-kit + test toolchain; wire QueryClient + Toaster"
```

---

## §R2 — Routes + page shells

### R2.1 — Route declaration

Two children inside the existing project route:

```jsx
// inside the existing <Route path="projects/:projectId" element={<ProjectDetail />}>
<Route path="budgets" element={<BudgetsList />} />
<Route path="budgets/:budgetId" element={<BudgetDetail />} />
```

If the project shell wrapper doesn't exist (D4), wrap each page in a small `<ProjectScopedHeader>` component (one line + breadcrumb) before proceeding.

### R2.2 — `hasPerm` helper

```js
// frontend/src/lib/perms.js (NEW)
/**
 * Permission check.
 *
 * Backend stores permissions as a flat string list on the user (e.g.
 * ['budgets.read', 'budgets.create', 'budgets.admin']).
 *
 * Convention from 2.4A:
 *   - budgets.read           : list + read
 *   - budgets.create         : POST /budgets/from-appraisal, line edits
 *   - budgets.admin          : unlock, refresh-attention, lock-override
 *   - budgets.view_sensitive : sensitive fields visible (FTC method/value, internal notes)
 *
 * super_admin and director have admin via role; PM has create; readonly has only read.
 */
export function hasPerm(user, perm) {
  if (!user) return false;
  if (!Array.isArray(user.permissions)) return false;
  return user.permissions.includes(perm);
}

export function hasAnyPerm(user, perms) {
  return perms.some((p) => hasPerm(user, p));
}
```

### R2.3 — `useIsDesktop` hook (H1 / H2 fix)

Mobile read-only floor enforcement. Single source of truth.

```js
// frontend/src/lib/useIsDesktop.js (NEW)
import { useEffect, useState } from 'react';

/**
 * Reactive matchMedia hook. Returns true when viewport is ≥ 768px (Tailwind `md`).
 * SSR-safe: defaults to false, syncs on mount.
 *
 * Use this everywhere mobile must be read-only.
 */
export function useIsDesktop() {
  const [isDesktop, setIsDesktop] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(min-width: 768px)').matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(min-width: 768px)');
    const onChange = (e) => setIsDesktop(e.matches);
    // Modern browsers
    if (mq.addEventListener) {
      mq.addEventListener('change', onChange);
      return () => mq.removeEventListener('change', onChange);
    }
    // Legacy fallback (Safari < 14)
    mq.addListener(onChange);
    return () => mq.removeListener(onChange);
  }, []);

  return isDesktop;
}
```

### R2.4 — Page shells

```jsx
// frontend/src/pages/projects/BudgetsList.jsx (NEW — final version replaces this in §R4)
import { useParams } from 'react-router-dom';
export default function BudgetsList() {
  const { projectId } = useParams();
  return <div className="p-6">Budgets list shell — projectId={projectId}</div>;
}
```

```jsx
// frontend/src/pages/projects/BudgetDetail.jsx (NEW — final version replaces this in §R5)
import { useParams } from 'react-router-dom';
export default function BudgetDetail() {
  const { projectId, budgetId } = useParams();
  return (
    <div className="p-6">
      Budget detail shell — projectId={projectId}, budgetId={budgetId}
    </div>
  );
}
```

### R2.5 — Smoke

```bash
yarn dev
# navigate to /projects/<known-id>/budgets       — expect BudgetsList shell
# navigate to /projects/<known-id>/budgets/abc   — expect BudgetDetail shell
# expect existing project header / nav still visible above both routes
```

### R2.6 — Commit boundary

```bash
git add src/pages/projects/BudgetsList.jsx \
        src/pages/projects/BudgetDetail.jsx \
        src/lib/perms.js \
        src/lib/useIsDesktop.js \
        src/App.jsx        # or wherever routes were added
git commit -m "feat(2.4B-i): route shells + perm helper + useIsDesktop"
```

---
## §R3 — API client layer

Typed wrappers around all 14 endpoints from 2.4A. Cookie-only via existing `lib/api.js`. **Abort signals threaded** for query cancellation (M9).

### R3.1 — Endpoint inventory

| # | Method | Path | 2.4A test reference | Hook name |
|---|---|---|---|---|
| 1 | GET | `/projects/:projectId/budgets` | implicit / chat-16-closing #89 not shipped | `useBudgetsList` |
| 2 | POST | `/projects/:projectId/budgets/from-appraisal` | TestCreateFromAppraisal::test_create_via_api | `useCreateBudgetFromAppraisal` |
| 3 | GET | `/budgets/:budgetId` | TestDetailQueryBudget, TestSensitiveGating | `useBudgetDetail` |
| 4 | POST | `/budgets/:budgetId/activate` | TestStateMachine::test_full_lifecycle | `useActivateBudget` |
| 5 | POST | `/budgets/:budgetId/lock` | TestStateMachine, TestPermissionGating | `useLockBudget` |
| 6 | POST | `/budgets/:budgetId/unlock` | TestPermissionGating::test_unlock_requires_admin | `useUnlockBudget` |
| 7 | POST | `/budgets/:budgetId/close` | TestStateMachine | `useCloseBudget` |
| 8 | POST | `/budgets/:budgetId/new-version` | TestNewVersion::test_new_version_supersedes_old | `useCreateBudgetVersion` |
| 9 | PATCH | `/budgets/:budgetId/lines/:lineId` | TestLineEdits | `usePatchBudgetLine` |
| 10 | POST | `/budgets/:budgetId/lines/:lineId/items` | TestLineItems | `useCreateLineItem` |
| 11 | PATCH | `/budgets/:budgetId/lines/:lineId/items/:itemId` | TestLineItems | `useUpdateLineItem` |
| 12 | DELETE | `/budgets/:budgetId/lines/:lineId/items/:itemId` | TestLineItems | `useDeleteLineItem` |
| 13 | GET | `/budgets/:budgetId/lines/:lineId/items` | covered via detail eager-load | `useLineItems` (rarely used; M5 — may not exist on backend) |
| 14 | POST | `/budgets/refresh-attention` | TestRefreshAttention::test_admin_scan_runs | `useRefreshAttention` |

**Plus one proposed new endpoint (D8 / STOP #32):**

| 15 | POST | `/budgets/:budgetId/lines/reorder` | (none in 2.4A — must be verified or added) | `useReorderBudgetLines` |

### R3.2 — Zod schemas (audit-corrected: C2, C7, H12, M3)

```js
// frontend/src/lib/schemas/budgets.js (NEW)
import { z } from 'zod';

export const BudgetStatus = z.enum([
  'Draft', 'Active', 'Locked', 'Closed', 'Superseded',
]);

export const VarianceStatus = z.enum(['Green', 'Amber', 'Red']);

// FTC method semantics:
//   BudgetRemaining   = current_budget - actuals - cni   (capped at 0)
//   CommittedOnly     = 0 (no FTC; just actuals + cni)
//   PercentageComplete= (1 - pct) * current_budget       (falls back to BudgetRemaining at pct=0)
//   Manual            = uses ftc_value field directly
export const FTCMethod = z.enum([
  'BudgetRemaining', 'CommittedOnly', 'PercentageComplete', 'Manual',
]);

// ──────────────────────────────────────────────────────────────────────────
// SENSITIVE-FIELD HANDLING (D11 / C2)
// ──────────────────────────────────────────────────────────────────────────
// Backend strips sensitive fields entirely from the payload for users without
// `budgets.view_sensitive`. We mark those fields .nullable().optional() so
// Zod accepts the stripped payload. Render code must handle null/undefined.
// Sensitive fields per chat-16-closing tests #83/#84:
//   - ftc_value, ftc_method  (FTC mechanics expose internal calc)
//   - notes                  (internal notes; supplier specifics)
// ──────────────────────────────────────────────────────────────────────────

export const BudgetLineItemSchema = z.object({
  id: z.string().uuid(),
  budget_line_id: z.string().uuid(),
  description: z.string(),
  quantity: z.coerce.number(),
  unit: z.string().nullable(),
  unit_cost: z.coerce.number(),
  amount: z.coerce.number(),
  notes: z.string().nullable(),
  position: z.number().int(),
});

export const BudgetLineSchema = z.object({
  id: z.string().uuid(),
  budget_id: z.string().uuid(),
  cost_code_id: z.string().uuid(),
  cost_code_label: z.string().nullable().default('—'),    // C7 fix: nullable + default
  description: z.string().nullable(),
  position: z.number().int(),
  // Money fields (decimal-as-string from backend → coerced)
  original_budget: z.coerce.number(),
  current_budget: z.coerce.number(),
  actuals_total: z.coerce.number(),
  committed_not_invoiced: z.coerce.number(),
  // SENSITIVE — backend strips for non-permitted users
  ftc_method: FTCMethod.nullable().optional(),
  ftc_value: z.coerce.number().nullable().optional(),
  notes: z.string().nullable().optional(),
  // Derived from sensitive — backend may return or strip
  ffc: z.coerce.number(),                                  // backend always returns (rolls up)
  variance_value: z.coerce.number(),
  variance_pct: z.coerce.number().nullable(),
  variance_status: VarianceStatus,
  // Always present
  percentage_complete: z.coerce.number().min(0).max(100).nullable(),
  // Concurrency stamp — increments on every PATCH; client echoes back
  version: z.number().int(),
  // Items eager-loaded
  items: z.array(BudgetLineItemSchema).default([]),
});

export const BudgetSchema = z.object({
  id: z.string().uuid(),
  tenant_id: z.string().uuid(),
  project_id: z.string().uuid(),
  entity_id: z.string().uuid(),
  appraisal_id: z.string().uuid().nullable(),
  version_number: z.number().int(),
  status: BudgetStatus,
  is_current: z.boolean(),
  superseded_by_id: z.string().uuid().nullable(),
  // Header totals — recomputed server-side
  total_original_budget: z.coerce.number(),
  total_current_budget: z.coerce.number(),
  total_actuals: z.coerce.number(),
  total_cni: z.coerce.number(),
  total_ftc: z.coerce.number().nullable().optional(),     // sensitive
  total_ffc: z.coerce.number(),
  total_variance: z.coerce.number(),
  total_variance_pct: z.coerce.number().nullable(),
  total_variance_status: VarianceStatus,
  // Lifecycle stamps
  created_at: z.string().datetime(),
  activated_at: z.string().datetime().nullable(),
  locked_at: z.string().datetime().nullable(),
  closed_at: z.string().datetime().nullable(),
  superseded_at: z.string().datetime().nullable(),
  summary_refreshed_at: z.string().datetime().nullable(),
  requires_attention: z.boolean(),
  // List view: lines omitted (perf); detail: present
  lines: z.array(BudgetLineSchema).optional(),
});

// ──────────────────────────────────────────────────────────────────────────
// PATCH PAYLOADS — used to validate client-built bodies before send (H11)
// ──────────────────────────────────────────────────────────────────────────

export const BudgetLinePatchSchema = z.object({
  description: z.string().max(2000).nullable().optional(),
  notes: z.string().max(5000).nullable().optional(),
  percentage_complete: z.number().min(0).max(100).nullable().optional(),
  ftc_method: FTCMethod.optional(),
  ftc_value: z.coerce.number().nullable().optional(),
  cost_code_id: z.string().uuid().optional(),
  // version is REQUIRED on every PATCH for conflict detection
  version: z.number().int(),
}).strict();

export const LineItemCreateSchema = z.object({
  description: z.string().min(1).max(500),
  quantity: z.coerce.number().min(0),
  unit: z.string().nullable().optional(),
  unit_cost: z.coerce.number().min(0),
  notes: z.string().max(2000).nullable().optional(),
}).strict();

export const LineItemPatchSchema = LineItemCreateSchema.partial().strict();

export const ReorderLinesSchema = z.object({
  ordered_line_ids: z.array(z.string().uuid()).min(1),
}).strict();

// Convenience: detail = budget with required lines
export const BudgetDetailSchema = BudgetSchema.extend({
  lines: z.array(BudgetLineSchema),
});

export const BudgetListSchema = z.array(BudgetSchema);
```

### R3.3 — API client functions (M9: signal-threaded)

```js
// frontend/src/lib/api/budgets.js (NEW)
import { api } from '@/lib/api';
import {
  BudgetSchema,
  BudgetLineSchema,
  BudgetLineItemSchema,
  BudgetDetailSchema,
  BudgetListSchema,
  BudgetLinePatchSchema,
  LineItemCreateSchema,
  LineItemPatchSchema,
  ReorderLinesSchema,
} from '@/lib/schemas/budgets';
import { z } from 'zod';

// Helper: parse with descriptive error
function parseOrThrow(schema, data, context) {
  const result = schema.safeParse(data);
  if (!result.success) {
    const err = new Error(`Schema mismatch in ${context}: ${result.error.message}`);
    err.zodError = result.error;
    throw err;
  }
  return result.data;
}

// 1. List budgets for a project
export async function listBudgets(projectId, { isCurrent, signal } = {}) {
  const params = {};
  if (isCurrent !== undefined) params.is_current = isCurrent;
  const { data } = await api.get(`/projects/${projectId}/budgets`, { params, signal });
  return parseOrThrow(BudgetListSchema, data, 'listBudgets');
}

// 2. Create from approved appraisal
export async function createBudgetFromAppraisal(projectId, { appraisalId }) {
  const { data } = await api.post(
    `/projects/${projectId}/budgets/from-appraisal`,
    { appraisal_id: appraisalId },
  );
  return parseOrThrow(BudgetDetailSchema, data, 'createBudgetFromAppraisal');
}

// 3. Get budget detail
export async function getBudgetDetail(budgetId, { signal } = {}) {
  const { data } = await api.get(`/budgets/${budgetId}`, { signal });
  return parseOrThrow(BudgetDetailSchema, data, 'getBudgetDetail');
}

// 4–7. Lifecycle endpoints
export async function activateBudget(budgetId) {
  const { data } = await api.post(`/budgets/${budgetId}/activate`);
  return parseOrThrow(BudgetDetailSchema, data, 'activateBudget');
}
export async function lockBudget(budgetId) {
  const { data } = await api.post(`/budgets/${budgetId}/lock`);
  return parseOrThrow(BudgetDetailSchema, data, 'lockBudget');
}
export async function unlockBudget(budgetId, { reason }) {
  const { data } = await api.post(`/budgets/${budgetId}/unlock`, { reason });
  return parseOrThrow(BudgetDetailSchema, data, 'unlockBudget');
}
export async function closeBudget(budgetId, { reason }) {
  const { data } = await api.post(`/budgets/${budgetId}/close`, { reason });
  return parseOrThrow(BudgetDetailSchema, data, 'closeBudget');
}

// 8. New version
export async function createBudgetVersion(budgetId, { reason }) {
  const { data } = await api.post(`/budgets/${budgetId}/new-version`, { reason });
  return parseOrThrow(BudgetDetailSchema, data, 'createBudgetVersion');
}

// 9. Patch a line — validates body shape before send (H11)
export async function patchBudgetLine(budgetId, lineId, patchBody) {
  const validated = parseOrThrow(BudgetLinePatchSchema, patchBody, 'patchBudgetLine[input]');
  const { data } = await api.patch(
    `/budgets/${budgetId}/lines/${lineId}`,
    validated,
  );
  return parseOrThrow(BudgetLineSchema, data, 'patchBudgetLine[output]');
}

// 10. Create line item
export async function createLineItem(budgetId, lineId, body) {
  const validated = parseOrThrow(LineItemCreateSchema, body, 'createLineItem[input]');
  const { data } = await api.post(
    `/budgets/${budgetId}/lines/${lineId}/items`,
    validated,
  );
  return parseOrThrow(BudgetLineItemSchema, data, 'createLineItem[output]');
}

// 11. Update line item
export async function updateLineItem(budgetId, lineId, itemId, body) {
  const validated = parseOrThrow(LineItemPatchSchema, body, 'updateLineItem[input]');
  const { data } = await api.patch(
    `/budgets/${budgetId}/lines/${lineId}/items/${itemId}`,
    validated,
  );
  return parseOrThrow(BudgetLineItemSchema, data, 'updateLineItem[output]');
}

// 12. Delete line item
export async function deleteLineItem(budgetId, lineId, itemId) {
  await api.delete(`/budgets/${budgetId}/lines/${lineId}/items/${itemId}`);
  return { ok: true };
}

// 13. List items per line — M5: may not exist; only used as defensive fallback
export async function listLineItems(budgetId, lineId, { signal } = {}) {
  const { data } = await api.get(`/budgets/${budgetId}/lines/${lineId}/items`, { signal });
  return z.array(BudgetLineItemSchema).parse(data);
}

// 14. Refresh-attention admin scan (no projectId — global)
export async function refreshAttention() {
  const { data } = await api.post(`/budgets/refresh-attention`);
  // Backend returns { scanned: n, flagged: n, cleared: n }
  return data;
}

// 15. Bulk reorder (D8 / STOP #32)
export async function reorderBudgetLines(budgetId, orderedLineIds) {
  const validated = parseOrThrow(
    ReorderLinesSchema,
    { ordered_line_ids: orderedLineIds },
    'reorderBudgetLines[input]',
  );
  const { data } = await api.post(
    `/budgets/${budgetId}/lines/reorder`,
    validated,
  );
  return parseOrThrow(BudgetDetailSchema, data, 'reorderBudgetLines[output]');
}
```

### R3.4 — React Query hooks (audit-corrected: H4, M9, drawer separation)

```js
// frontend/src/hooks/budgets.js (NEW)
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import * as api from '@/lib/api/budgets';

// ── query keys (single source of truth) ──
export const budgetKeys = {
  all: ['budgets'],
  list: (projectId, filters = {}) => [...budgetKeys.all, 'list', projectId, filters],
  detail: (budgetId) => [...budgetKeys.all, 'detail', budgetId],
  items: (budgetId, lineId) =>
    [...budgetKeys.all, 'detail', budgetId, 'lines', lineId, 'items'],
};

// ── reads ──
// `enabled` opt added so callers can perm-gate before the request fires
// (without violating Rules of Hooks by short-circuiting the hook call).
export function useBudgetsList(projectId, filters = {}, { enabled = true } = {}) {
  return useQuery({
    queryKey: budgetKeys.list(projectId, filters),
    queryFn: ({ signal }) => api.listBudgets(projectId, { ...filters, signal }),
    enabled: enabled && !!projectId,
  });
}

export function useBudgetDetail(budgetId, { enabled = true } = {}) {
  return useQuery({
    queryKey: budgetKeys.detail(budgetId),
    queryFn: ({ signal }) => api.getBudgetDetail(budgetId, { signal }),
    enabled: enabled && !!budgetId,
  });
}

export function useLineItems(budgetId, lineId, { enabled = true } = {}) {
  return useQuery({
    queryKey: budgetKeys.items(budgetId, lineId),
    queryFn: ({ signal }) => api.listLineItems(budgetId, lineId, { signal }),
    enabled: enabled && !!(budgetId && lineId),
  });
}

// ── writes — server-confirmed (no optimistic) ──

export function useCreateBudgetFromAppraisal(projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ appraisalId }) =>
      api.createBudgetFromAppraisal(projectId, { appraisalId }),
    onSuccess: (newBudget) => {
      qc.invalidateQueries({ queryKey: budgetKeys.list(projectId) });
      qc.setQueryData(budgetKeys.detail(newBudget.id), newBudget);
      toast.success('Budget created from approved appraisal.');
    },
    onError: (err) => {
      const msg = err?.response?.data?.detail ?? 'Failed to create budget.';
      toast.error(msg);
    },
  });
}

// Lifecycle factory — Activate / Lock / Unlock / Close share the shape
function makeLifecycleMutation(verb, apiFn) {
  return function useLifecycleMutation(budgetId, projectId) {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: (args = {}) => apiFn(budgetId, args),
      onSuccess: (updated) => {
        qc.setQueryData(budgetKeys.detail(budgetId), updated);
        if (projectId) {
          qc.invalidateQueries({ queryKey: budgetKeys.list(projectId) });
        }
        toast.success(`Budget ${verb}.`);
      },
      onError: (err) => {
        const msg = err?.response?.data?.detail ?? `Failed to ${verb} budget.`;
        toast.error(msg);
      },
    });
  };
}

export const useActivateBudget = makeLifecycleMutation('activated', api.activateBudget);
export const useLockBudget     = makeLifecycleMutation('locked',    api.lockBudget);
export const useUnlockBudget   = makeLifecycleMutation('unlocked',  api.unlockBudget);
export const useCloseBudget    = makeLifecycleMutation('closed',    api.closeBudget);

// New version is special — returns the NEW draft, not the superseded budget
export function useCreateBudgetVersion(budgetId, projectId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ reason }) => api.createBudgetVersion(budgetId, { reason }),
    onSuccess: (newDraft) => {
      qc.invalidateQueries({ queryKey: budgetKeys.list(projectId) });
      qc.setQueryData(budgetKeys.detail(newDraft.id), newDraft);
      qc.invalidateQueries({ queryKey: budgetKeys.detail(budgetId) }); // old → Superseded
      toast.success('New budget version created.');
    },
    onError: (err) => {
      const msg = err?.response?.data?.detail ?? 'Failed to create new version.';
      toast.error(msg);
    },
  });
}

// ── writes — line patch (supports BOTH optimistic and server-confirmed paths) ──
//
// Caller passes { lineId, body, optimistic } via mutate().
// optimistic=true  → grid inline-edit path (description/notes/% complete)
// optimistic=false → drawer Save path (waits for server confirmation)
//
// Both paths share the same hook to avoid duplicating onSuccess cache splice.
export function usePatchBudgetLine(budgetId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ lineId, body }) => api.patchBudgetLine(budgetId, lineId, body),

    onMutate: async ({ lineId, body, optimistic }) => {
      if (!optimistic) return; // server-confirmed path skips optimistic update
      const key = budgetKeys.detail(budgetId);
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData(key);
      qc.setQueryData(key, (current) => {
        if (!current) return current;
        return {
          ...current,
          lines: current.lines.map((line) =>
            line.id === lineId ? { ...line, ...body } : line,
          ),
        };
      });
      return { prev };
    },

    onError: (err, vars, ctx) => {
      const key = budgetKeys.detail(budgetId);
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
      const status = err?.response?.status;
      if (status === 409) {
        toast.error('This line was edited elsewhere. Reload to see the latest.', {
          action: {
            label: 'Reload',
            onClick: () => qc.invalidateQueries({ queryKey: key }),
          },
        });
      } else {
        const msg = err?.response?.data?.detail ?? 'Failed to update line.';
        toast.error(msg);
      }
    },

    onSuccess: (savedLine) => {
      // Server result is authoritative — splice it back in.
      const key = budgetKeys.detail(budgetId);
      qc.setQueryData(key, (current) => {
        if (!current) return current;
        return {
          ...current,
          lines: current.lines.map((line) =>
            line.id === savedLine.id ? savedLine : line,
          ),
        };
      });
    },
  });
}

// ── writes — line items ──
export function useCreateLineItem(budgetId, lineId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => api.createLineItem(budgetId, lineId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetKeys.detail(budgetId) });
      toast.success('Item added.');
    },
    onError: (err) => {
      const msg = err?.response?.data?.detail ?? 'Failed to add item.';
      toast.error(msg);
    },
  });
}

export function useUpdateLineItem(budgetId, lineId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, body }) =>
      api.updateLineItem(budgetId, lineId, itemId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: budgetKeys.detail(budgetId) }),
    onError: (err) => {
      const msg = err?.response?.data?.detail ?? 'Failed to update item.';
      toast.error(msg);
    },
  });
}

export function useDeleteLineItem(budgetId, lineId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (itemId) => api.deleteLineItem(budgetId, lineId, itemId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetKeys.detail(budgetId) });
      toast.success('Item deleted.');
    },
    onError: (err) => {
      const msg = err?.response?.data?.detail ?? 'Failed to delete item.';
      toast.error(msg);
    },
  });
}

// ── writes — admin scan (H4: drop unused projectId param) ──
export function useRefreshAttention() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.refreshAttention(),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: budgetKeys.all });
      toast.success(
        `Scan complete: ${result.scanned} scanned, ${result.flagged} flagged, ${result.cleared} cleared.`,
      );
    },
    onError: (err) => {
      const msg = err?.response?.data?.detail ?? 'Refresh-attention scan failed.';
      toast.error(msg);
    },
  });
}

// ── writes — reorder (D8) ──
export function useReorderBudgetLines(budgetId) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orderedLineIds) => api.reorderBudgetLines(budgetId, orderedLineIds),

    onMutate: async (orderedLineIds) => {
      const key = budgetKeys.detail(budgetId);
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData(key);
      qc.setQueryData(key, (current) => {
        if (!current) return current;
        const byId = Object.fromEntries(current.lines.map((l) => [l.id, l]));
        const reordered = orderedLineIds
          .map((id, idx) => byId[id] && { ...byId[id], position: idx })
          .filter(Boolean);
        return { ...current, lines: reordered };
      });
      return { prev };
    },

    onError: (err, vars, ctx) => {
      const key = budgetKeys.detail(budgetId);
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
      const msg = err?.response?.data?.detail ?? 'Reorder failed; restored.';
      toast.error(msg);
    },

    onSuccess: (refreshed) => {
      qc.setQueryData(budgetKeys.detail(budgetId), refreshed);
    },
  });
}
```

### R3.5 — Smoke

```bash
yarn build       # expect clean
yarn lint        # expect clean
```

Manual: navigate to `/projects/<id>/budgets`, devtools network → `GET /api/v1/projects/<id>/budgets` fires with `Cookie:` header, returns 200.

### R3.6 — Commit boundary

```bash
git add src/lib/api/budgets.js src/lib/schemas/budgets.js src/hooks/budgets.js
git commit -m "feat(2.4B-i): API client + Zod schemas (sensitive nullable) + React Query hooks (signal-threaded)"
```

---
## §R4 — BudgetsList page

### R4.1 — Component map

```
<BudgetsList>
  ├── PermGuard ('budgets.read')          // H5 fix
  ├── <PageHeader>                        // title + Create + Refresh-attention
  ├── <BudgetsTable>                      // TanStack Table
  │     ├── <StatusBadge>
  │     └── <VarianceBadge>
  └── <CreateFromAppraisalDialog>         // shadcn Dialog, lazy-fetches appraisals
```

### R4.2 — Status + variance badges

Slate baseline; brand colours reserved for actions.

```jsx
// frontend/src/components/budgets/StatusBadge.jsx (NEW)
const STATUS_CLASSES = {
  Draft:      'bg-slate-100 text-slate-700 border-slate-200',
  Active:     'bg-emerald-50 text-emerald-700 border-emerald-200',
  Locked:     'bg-blue-50 text-blue-700 border-blue-200',
  Closed:     'bg-slate-100 text-slate-500 border-slate-200',
  Superseded: 'bg-slate-50 text-slate-400 border-slate-200',
};

export function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${STATUS_CLASSES[status] ?? STATUS_CLASSES.Draft}`}>
      {status}
    </span>
  );
}
```

```jsx
// frontend/src/components/budgets/VarianceBadge.jsx (NEW)
const VARIANCE_CLASSES = {
  Green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  Amber: 'bg-amber-50 text-amber-700 border-amber-200',
  Red:   'bg-rose-50 text-rose-700 border-rose-200',
};

export function VarianceBadge({ status, value, pct }) {
  const sign = value > 0 ? '+' : '';
  const tooltipPct = pct != null ? ` (${pct.toFixed(1)}%)` : '';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${VARIANCE_CLASSES[status]}`}
      title={`Variance ${sign}£${value?.toLocaleString() ?? '—'}${tooltipPct}`}
    >
      <span aria-hidden>●</span>
      {status}
    </span>
  );
}
```

### R4.3 — Money + percentage formatters

```js
// frontend/src/lib/format.js (NEW)
export const fmtGBP = (n, opts = {}) => {
  if (n == null || isNaN(n)) return '—';
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'GBP',
    maximumFractionDigits: 0,
    ...opts,
  }).format(n);
};

export const fmtPct = (n, digits = 1) => {
  if (n == null || isNaN(n)) return '—';
  return `${n.toFixed(digits)}%`;
};
```

### R4.4 — BudgetsTable (TanStack Table v8)

```jsx
// frontend/src/components/budgets/BudgetsTable.jsx (NEW)
import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { StatusBadge } from './StatusBadge';
import { VarianceBadge } from './VarianceBadge';
import { fmtGBP } from '@/lib/format';

export function BudgetsTable({ budgets, projectId }) {
  const columns = useMemo(() => [
    {
      accessorKey: 'version_number',
      header: 'Version',
      cell: ({ row }) => (
        <Link
          to={`/projects/${projectId}/budgets/${row.original.id}`}
          className="font-mono text-sm text-slate-900 hover:underline"
        >
          v{row.original.version_number}
        </Link>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    },
    {
      accessorKey: 'is_current',
      header: 'Current?',
      enableSorting: false,
      cell: ({ row }) =>
        row.original.is_current ? (
          <span className="text-xs font-medium text-emerald-700">● Current</span>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        ),
    },
    {
      accessorKey: 'total_current_budget',
      header: 'Current Budget',
      cell: ({ row }) => fmtGBP(row.original.total_current_budget),
    },
    {
      accessorKey: 'total_ffc',
      header: 'FFC',
      cell: ({ row }) => fmtGBP(row.original.total_ffc),
    },
    {
      accessorKey: 'total_variance',
      header: 'Variance',
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm">
            {fmtGBP(row.original.total_variance, { signDisplay: 'exceptZero' })}
          </span>
          <VarianceBadge
            status={row.original.total_variance_status}
            value={row.original.total_variance}
            pct={row.original.total_variance_pct}
          />
        </div>
      ),
    },
    {
      accessorKey: 'requires_attention',
      header: '',
      enableSorting: false,            // L1 fix
      cell: ({ row }) =>
        row.original.requires_attention ? (
          <span title="Requires attention" aria-label="Requires attention">⚠</span>
        ) : null,
    },
  ], [projectId]);

  const table = useReactTable({
    data: budgets,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    initialState: {
      sorting: [{ id: 'version_number', desc: true }],
    },
  });

  if (!budgets.length) {
    return (
      <div className="rounded-lg border border-slate-200 p-12 text-center text-slate-500">
        No budgets yet. Create one from an approved appraisal.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full text-sm">
        <thead className="bg-slate-50">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th
                  key={h.id}
                  className="px-4 py-2 text-left font-medium text-slate-700"
                  onClick={h.column.getToggleSortingHandler()}
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="border-t border-slate-100 hover:bg-slate-50">
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-4 py-2">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### R4.5 — CreateFromAppraisalDialog (H3 fix: `enabled` not `open`)

Expected `useApprovedAppraisals` signature ([CONFIRM] D12): `(projectId, { enabled = true } = {})`.

```jsx
// frontend/src/components/budgets/CreateFromAppraisalDialog.jsx (NEW)
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { useApprovedAppraisals } from '@/hooks/appraisals';
import { useCreateBudgetFromAppraisal } from '@/hooks/budgets';

export function CreateFromAppraisalDialog({ projectId, trigger }) {
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const navigate = useNavigate();
  const { data: appraisals = [], isLoading } = useApprovedAppraisals(projectId, { enabled: open });
  const createMut = useCreateBudgetFromAppraisal(projectId);

  async function handleCreate() {
    if (!selectedId) return;
    try {
      const newBudget = await createMut.mutateAsync({ appraisalId: selectedId });
      setOpen(false);
      setSelectedId(null);
      navigate(`/projects/${projectId}/budgets/${newBudget.id}`);
    } catch {
      // toast already fired in hook
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create budget from approved appraisal</DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading appraisals…</p>
        ) : appraisals.length === 0 ? (
          <p className="text-sm text-slate-500">
            No approved appraisals available. An appraisal must be approved
            (governance status <code>Approved</code>) and not already linked to a
            current budget.
          </p>
        ) : (
          <RadioGroup value={selectedId} onValueChange={setSelectedId}>
            {appraisals.map((a) => (
              <div key={a.id} className="flex items-center space-x-2 py-1">
                <RadioGroupItem value={a.id} id={`appraisal-${a.id}`} />
                <Label htmlFor={`appraisal-${a.id}`} className="cursor-pointer">
                  {a.name} — total cost £{a.total_cost?.toLocaleString()}
                </Label>
              </div>
            ))}
          </RadioGroup>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
            disabled={!selectedId || createMut.isPending}
            onClick={handleCreate}
          >
            {createMut.isPending ? 'Creating…' : 'Create budget'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

### R4.6 — BudgetsList page (H5 perm gate + mobile floor)

```jsx
// frontend/src/pages/projects/BudgetsList.jsx (final)
import { useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { hasPerm } from '@/lib/perms';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { useBudgetsList, useRefreshAttention } from '@/hooks/budgets';
import { BudgetsTable } from '@/components/budgets/BudgetsTable';
import { CreateFromAppraisalDialog } from '@/components/budgets/CreateFromAppraisalDialog';

export default function BudgetsList() {
  const { projectId } = useParams();
  const { user } = useAuth();
  const isDesktop = useIsDesktop();

  const canRead   = hasPerm(user, 'budgets.read');
  const canCreate = hasPerm(user, 'budgets.create') && isDesktop;
  const canAdmin  = hasPerm(user, 'budgets.admin')  && isDesktop;

  // ALL hooks must be called before any conditional return (Rules of Hooks).
  // The `enabled` flag stops a wasted 403 fetch for users without budgets.read.
  const { data: budgets = [], isLoading, isError, error } =
    useBudgetsList(projectId, {}, { enabled: canRead });
  const refreshMut = useRefreshAttention();

  // H5: gate the entire page on budgets.read (after all hooks)
  if (!canRead) {
    return (
      <div className="m-6 rounded-lg border border-slate-200 bg-slate-50 p-6 text-slate-600">
        You don't have access to budgets. Contact a director if you need this.
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Budgets</h1>
        <div className="hidden items-center gap-2 md:flex">
          {canAdmin && (
            <Button
              variant="outline"
              disabled={refreshMut.isPending}
              onClick={() => refreshMut.mutate()}
            >
              {refreshMut.isPending ? 'Scanning…' : 'Refresh attention'}
            </Button>
          )}
          {canCreate && (
            <CreateFromAppraisalDialog
              projectId={projectId}
              trigger={
                <Button className="bg-sy-teal text-white hover:brightness-110 active:brightness-95">
                  Create from Approved Appraisal
                </Button>
              }
            />
          )}
        </div>
      </header>

      {/* Mobile read-only banner */}
      <div className="md:hidden rounded-md bg-slate-100 px-4 py-2 text-xs text-slate-600">
        Read-only on mobile. Use desktop to edit.
      </div>

      {isLoading ? (
        <div className="rounded-lg border border-slate-200 p-12 text-center text-slate-500">
          Loading budgets…
        </div>
      ) : isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700">
          Failed to load budgets: {error?.message}
        </div>
      ) : (
        <BudgetsTable budgets={budgets} projectId={projectId} />
      )}
    </div>
  );
}
```

### R4.7 — Commit boundary

```bash
git add src/components/budgets/StatusBadge.jsx \
        src/components/budgets/VarianceBadge.jsx \
        src/components/budgets/BudgetsTable.jsx \
        src/components/budgets/CreateFromAppraisalDialog.jsx \
        src/lib/format.js \
        src/pages/projects/BudgetsList.jsx
git commit -m "feat(2.4B-i): BudgetsList page + TanStack Table + create dialog (perm-gated, mobile-floored)"
```

---
## §R5 — BudgetDetail header + state-machine controls

### R5.1 — Component map

```
<BudgetDetail>
  ├── PermGuard ('budgets.read')        // H5
  ├── <BudgetHeader>
  │     ├── identity (version, status, supersedes link)
  │     ├── 6 totals tiles
  │     ├── variance row
  │     └── <LifecycleActions>          // gated by useIsDesktop + status + perm
  ├── <SensitiveBanner>                  // shown if user lacks view_sensitive
  └── <BudgetLinesGrid>                  // §R6
```

### R5.2 — BudgetHeader

```jsx
// frontend/src/components/budgets/BudgetHeader.jsx (NEW)
import { Link } from 'react-router-dom';
import { StatusBadge } from './StatusBadge';
import { VarianceBadge } from './VarianceBadge';
import { LifecycleActions } from './LifecycleActions';
import { fmtGBP, fmtPct } from '@/lib/format';

export function BudgetHeader({ budget, projectId }) {
  const tiles = [
    { label: 'Original Budget', value: budget.total_original_budget },
    { label: 'Current Budget',  value: budget.total_current_budget },
    { label: 'Actuals',         value: budget.total_actuals },
    { label: 'CNI',             value: budget.total_cni, hint: 'Committed not invoiced' },
    { label: 'FTC',             value: budget.total_ftc, hint: 'Forecast to complete (sensitive — may be hidden)' },
    { label: 'FFC',             value: budget.total_ffc, hint: 'Forecast final cost' },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-slate-900">
              Budget v{budget.version_number}
            </h1>
            <StatusBadge status={budget.status} />
            {budget.is_current && (
              <span className="text-xs font-medium text-emerald-700">● Current</span>
            )}
          </div>
          {budget.superseded_by_id && (
            <p className="text-xs text-slate-500">
              Superseded by{' '}
              <Link
                to={`/projects/${projectId}/budgets/${budget.superseded_by_id}`}
                className="underline hover:text-slate-900"
              >
                newer version
              </Link>
            </p>
          )}
        </div>
        <LifecycleActions budget={budget} projectId={projectId} />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        {tiles.map((t) => (
          <div
            key={t.label}
            className="rounded-lg border border-slate-200 bg-white p-3"
            title={t.hint}
          >
            <div className="text-xs uppercase tracking-wide text-slate-500">{t.label}</div>
            <div className="mt-1 font-mono text-lg text-slate-900">{fmtGBP(t.value)}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-3">
        <span className="text-xs uppercase tracking-wide text-slate-500">
          Variance (FFC − Current)
        </span>
        <span className="font-mono text-lg text-slate-900">
          {fmtGBP(budget.total_variance, { signDisplay: 'exceptZero' })}
        </span>
        <span className="text-sm text-slate-500">
          {fmtPct(budget.total_variance_pct)}
        </span>
        <VarianceBadge
          status={budget.total_variance_status}
          value={budget.total_variance}
          pct={budget.total_variance_pct}
        />
        {budget.requires_attention && (
          <span className="ml-auto text-xs font-medium text-rose-700">
            ⚠ Requires attention
          </span>
        )}
      </div>
    </div>
  );
}
```

### R5.3 — LifecycleActions (mobile-gated, brand-fixed)

(status, perm) matrix:

| Action | Allowed when status | Permission | Confirm? | Brand |
|---|---|---|---|---|
| Activate | Draft | budgets.create | no | sy-teal |
| Lock | Active | budgets.create | no (R5.6 pushback) | sy-teal |
| Unlock | Locked | budgets.admin | yes — sy-orange + reason | sy-orange |
| Close | Active OR Locked | budgets.admin | yes — sy-orange + reason | sy-orange |
| New Version | Active OR Locked OR Closed | budgets.create | yes — sy-orange + reason | sy-orange |

```jsx
// frontend/src/components/budgets/LifecycleActions.jsx (NEW)
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { hasPerm } from '@/lib/perms';
import { useIsDesktop } from '@/lib/useIsDesktop';
import {
  useActivateBudget,
  useLockBudget,
  useUnlockBudget,
  useCloseBudget,
  useCreateBudgetVersion,
} from '@/hooks/budgets';
import { ConfirmDialog } from './ConfirmDialog';

const TEAL  = 'bg-sy-teal text-white hover:brightness-110 active:brightness-95';
const ORNG  = 'bg-sy-orange text-white hover:brightness-110 active:brightness-95';

export function LifecycleActions({ budget, projectId }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isDesktop = useIsDesktop();
  const canCreate = hasPerm(user, 'budgets.create') && isDesktop;
  const canAdmin  = hasPerm(user, 'budgets.admin')  && isDesktop;

  const activate = useActivateBudget(budget.id, projectId);
  const lock     = useLockBudget(budget.id, projectId);
  const unlock   = useUnlockBudget(budget.id, projectId);
  const close    = useCloseBudget(budget.id, projectId);
  const newVer   = useCreateBudgetVersion(budget.id, projectId);

  const isPending =
    activate.isPending || lock.isPending || unlock.isPending ||
    close.isPending || newVer.isPending;

  return (
    <div className="hidden flex-wrap items-center gap-2 md:flex">
      {budget.status === 'Draft' && canCreate && (
        <Button className={TEAL} disabled={isPending} onClick={() => activate.mutate({})}>
          {activate.isPending ? 'Activating…' : 'Activate'}
        </Button>
      )}

      {budget.status === 'Active' && canCreate && (
        <Button className={TEAL} disabled={isPending} onClick={() => lock.mutate({})}>
          {lock.isPending ? 'Locking…' : 'Lock'}
        </Button>
      )}

      {budget.status === 'Locked' && canAdmin && (
        <ConfirmDialog
          title="Unlock budget?"
          description="Unlocking returns the budget to Active and reopens lines for edit. The action is audit-logged with the reason."
          confirmLabel="Unlock"
          requireReason
          variant="destructive"
          isPending={unlock.isPending}
          onConfirm={(reason) => unlock.mutate({ reason })}
          trigger={<Button className={ORNG} disabled={isPending}>Unlock</Button>}
        />
      )}

      {(budget.status === 'Active' || budget.status === 'Locked') && canAdmin && (
        <ConfirmDialog
          title="Close budget?"
          description="Closing freezes the budget permanently. No further edits or version bumps from this version."
          confirmLabel="Close budget"
          requireReason
          variant="destructive"
          isPending={close.isPending}
          onConfirm={(reason) => close.mutate({ reason })}
          trigger={<Button className={ORNG} disabled={isPending}>Close</Button>}
        />
      )}

      {budget.status !== 'Draft' && canCreate && (
        <ConfirmDialog
          title="Create new version?"
          description="A new Draft will be created with current lines and items cloned. This budget will be marked Superseded."
          confirmLabel="Create new version"
          requireReason
          variant="destructive"
          isPending={newVer.isPending}
          onConfirm={async (reason) => {
            const newDraft = await newVer.mutateAsync({ reason });
            navigate(`/projects/${projectId}/budgets/${newDraft.id}`);
          }}
          trigger={<Button className={ORNG} disabled={isPending}>New version</Button>}
        />
      )}
    </div>
  );
}
```

### R5.4 — ConfirmDialog (brand-fixed)

```jsx
// frontend/src/components/budgets/ConfirmDialog.jsx (NEW)
import { useState } from 'react';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';

export function ConfirmDialog({
  title, description, confirmLabel, trigger,
  requireReason = false, isPending = false,
  variant = 'default',
  onConfirm,
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');

  const confirmClass =
    variant === 'destructive'
      ? 'bg-sy-orange text-white hover:brightness-110 active:brightness-95'
      : 'bg-sy-teal text-white hover:brightness-110 active:brightness-95';

  async function handleConfirm() {
    if (requireReason && !reason.trim()) return;
    try {
      await onConfirm(reason.trim());
    } finally {
      setOpen(false);
      setReason('');
    }
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setReason('');     // B2 fix: clear reason when dialog closes via Cancel/Escape/click-outside
      }}
    >
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {requireReason && (
          <div className="space-y-1">
            <Label htmlFor="reason">Reason (audit-logged)</Label>
            <Textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              placeholder="Why are you taking this action?"
            />
          </div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className={confirmClass}
            disabled={isPending || (requireReason && !reason.trim())}
            onClick={handleConfirm}
          >
            {isPending ? 'Working…' : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

### R5.5 — SensitiveBanner

```jsx
// frontend/src/components/budgets/SensitiveBanner.jsx (NEW)
import { useAuth } from '@/contexts/AuthContext';
import { hasPerm } from '@/lib/perms';

export function SensitiveBanner() {
  const { user } = useAuth();
  if (hasPerm(user, 'budgets.view_sensitive')) return null;
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-2 text-xs text-slate-600">
      Some sensitive fields (FTC method, FTC value, internal notes) are hidden under
      your role. Contact a director to request elevated access.
    </div>
  );
}
```

### R5.6 — Pushback flagged: Lock without confirm (unchanged from v1)

Default ships **Lock without confirm** (single click Active → Locked). Reasoning: locking is reversible by admin Unlock; activating wasn't gated either; over-confirming trains users to click through dialogs. Audit may flip this — trivial swap to wrap in `ConfirmDialog` with `variant="default"` + `requireReason=false`.

### R5.7 — BudgetDetail page (final)

```jsx
// frontend/src/pages/projects/BudgetDetail.jsx (final)
import { useParams } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { hasPerm } from '@/lib/perms';
import { useBudgetDetail } from '@/hooks/budgets';
import { BudgetHeader } from '@/components/budgets/BudgetHeader';
import { SensitiveBanner } from '@/components/budgets/SensitiveBanner';
import { BudgetLinesGrid } from '@/components/budgets/BudgetLinesGrid';

export default function BudgetDetail() {
  const { projectId, budgetId } = useParams();
  const { user } = useAuth();
  const canRead = hasPerm(user, 'budgets.read');

  // ALL hooks must be called before any conditional return (Rules of Hooks).
  const { data: budget, isLoading, isError, error } =
    useBudgetDetail(budgetId, { enabled: canRead });

  // H5: gate the entire page on budgets.read (after all hooks)
  if (!canRead) {
    return (
      <div className="m-6 rounded-lg border border-slate-200 bg-slate-50 p-6 text-slate-600">
        You don't have access to budgets.
      </div>
    );
  }

  if (isLoading) return <div className="p-6 text-slate-500">Loading budget…</div>;
  if (isError) {
    return (
      <div className="m-6 rounded-lg border border-rose-200 bg-rose-50 p-6 text-rose-700">
        Failed to load budget: {error?.message}
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <BudgetHeader budget={budget} projectId={projectId} />
      <SensitiveBanner />
      <BudgetLinesGrid budget={budget} />
    </div>
  );
}
```

### R5.8 — Commit boundary

```bash
git add src/components/budgets/BudgetHeader.jsx \
        src/components/budgets/LifecycleActions.jsx \
        src/components/budgets/ConfirmDialog.jsx \
        src/components/budgets/SensitiveBanner.jsx \
        src/pages/projects/BudgetDetail.jsx
git commit -m "feat(2.4B-i): BudgetDetail header + lifecycle actions (mobile-gated, brand-safe)"
```

---
## §R6 — BudgetLinesGrid

Lines table on the detail page. Inline edits for `description` / `notes` / `% complete` (optimistic, desktop only). Drag-reorder via dnd-kit (PointerSensor + KeyboardSensor for a11y, C8/C9 fixes). Click row → opens `<LineDrawer>` (§R7).

### R6.1 — Editability matrix

| Status | Description / Notes / % | FTC method / value | Cost code | Items CRUD | Reorder | Add / Delete line |
|--------|------------------------|--------------------|-----------|-----------|---------|--------------------|
| Draft | yes (optimistic) | yes (server-confirmed) | yes (server-confirmed) | yes | yes | yes |
| Active | yes (optimistic) | yes (server-confirmed) | **no** | yes | yes | no |
| Locked | no | no | no | no | no | no |
| Closed | no | no | no | no | no | no |
| Superseded | no | no | no | no | no | no |

ALL editability is additionally gated by `useIsDesktop()` — mobile shows everything as read-only regardless of status (H1).

```js
// frontend/src/lib/budgetCapability.js (NEW)
export function isBudgetEditable(status) {
  return status === 'Draft' || status === 'Active';
}
export function isLineCreatable(status) {
  return status === 'Draft';
}
export function isCostCodeMutable(status) {
  return status === 'Draft';
}
```

### R6.2 — SortableLineRow (C8/C9/H1/H7 fixes)

```jsx
// frontend/src/components/budgets/SortableLineRow.jsx (NEW)
import { useState } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, MoreHorizontal } from 'lucide-react';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { VarianceBadge } from './VarianceBadge';
import { fmtGBP, fmtPct } from '@/lib/format';
import { usePatchBudgetLine } from '@/hooks/budgets';
import { useAuth } from '@/contexts/AuthContext';
import { hasPerm } from '@/lib/perms';
import { isBudgetEditable } from '@/lib/budgetCapability';

export function SortableLineRow({ line, budget, onOpenDrawer, dragDisabled, inlineEditEnabled }) {
  const { user } = useAuth();
  const sensitive = hasPerm(user, 'budgets.view_sensitive');
  const patchMut = usePatchBudgetLine(budget.id);

  // C9: setActivatorNodeRef for proper a11y on drag handle
  const {
    attributes, listeners, setNodeRef, setActivatorNodeRef,
    transform, transition, isDragging,
  } = useSortable({ id: line.id, disabled: dragDisabled });

  const [editingDesc, setEditingDesc] = useState(false);
  const [draftDesc, setDraftDesc] = useState(line.description ?? '');
  const [editingPct, setEditingPct] = useState(false);
  const [draftPct, setDraftPct] = useState(
    line.percentage_complete == null ? '' : String(line.percentage_complete),
  );

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  // Editable predicate — always gates on inlineEditEnabled (H1: mobile floor)
  const canInlineEdit = inlineEditEnabled && isBudgetEditable(budget.status);

  // H7: guard against double-fire (Enter + onBlur)
  function commitDesc() {
    if (!editingDesc) return;
    setEditingDesc(false);
    if (draftDesc === (line.description ?? '')) return;
    patchMut.mutate({
      lineId: line.id,
      body: { description: draftDesc, version: line.version },
      optimistic: true,
    });
  }

  function commitPct() {
    if (!editingPct) return;
    setEditingPct(false);
    const trimmed = draftPct.trim();
    const n = trimmed === '' ? null : Number(trimmed);
    if (n === (line.percentage_complete ?? null)) return;
    if (n != null && (isNaN(n) || n < 0 || n > 100)) {
      // Reject and revert draft
      setDraftPct(line.percentage_complete == null ? '' : String(line.percentage_complete));
      return;
    }
    patchMut.mutate({
      lineId: line.id,
      body: { percentage_complete: n, version: line.version },
      optimistic: true,
    });
  }

  // B1 fix: sync drafts to current line value when entering edit mode.
  // Without this, after a successful save the cached line.description updates
  // but draftDesc retains the stale initial value — so a SECOND click-to-edit
  // would show stale text.
  function startEditDesc() {
    if (!canInlineEdit) return;
    setDraftDesc(line.description ?? '');
    setEditingDesc(true);
  }
  function startEditPct() {
    if (!canInlineEdit) return;
    setDraftPct(line.percentage_complete == null ? '' : String(line.percentage_complete));
    setEditingPct(true);
  }

  return (
    <tr
      ref={setNodeRef}
      style={style}
      className="border-t border-slate-100 hover:bg-slate-50"
      data-testid={`budget-line-row-${line.id}`}
    >
      <td className="w-8 px-2">
        {!dragDisabled && (
          <button
            ref={setActivatorNodeRef}
            {...attributes}
            {...listeners}
            className="cursor-grab text-slate-400 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sy-teal"
            aria-label={`Drag to reorder line ${line.cost_code_label ?? line.cost_code_id.slice(-6)}`}
            type="button"
          >
            <GripVertical size={16} />
          </button>
        )}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-slate-600">
        {line.cost_code_label ?? line.cost_code_id.slice(-6)}
      </td>
      <td className="px-3 py-2">
        {editingDesc && canInlineEdit ? (
          <Input
            autoFocus
            value={draftDesc}
            onChange={(e) => setDraftDesc(e.target.value)}
            onBlur={commitDesc}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                commitDesc();
              } else if (e.key === 'Escape') {
                e.preventDefault();
                setDraftDesc(line.description ?? '');
                setEditingDesc(false);
              }
            }}
            className="h-7 text-sm"
            disabled={patchMut.isPending}
          />
        ) : (
          <span
            className={canInlineEdit ? 'cursor-text' : ''}
            onClick={startEditDesc}
          >
            {line.description || (canInlineEdit
              ? <em className="text-slate-400">Click to add description</em>
              : <span className="text-slate-400">—</span>
            )}
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-right font-mono">{fmtGBP(line.original_budget)}</td>
      <td className="px-3 py-2 text-right font-mono">{fmtGBP(line.current_budget)}</td>
      <td className="px-3 py-2 text-right font-mono">{fmtGBP(line.actuals_total)}</td>
      <td className="px-3 py-2 text-right font-mono">{fmtGBP(line.committed_not_invoiced)}</td>
      <td className="px-3 py-2 text-right font-mono">
        {sensitive && line.ftc_value != null
          ? fmtGBP(line.ftc_value)
          : <span className="text-slate-400">—</span>}
      </td>
      <td className="px-3 py-2 text-right font-mono">{fmtGBP(line.ffc)}</td>
      <td className="px-3 py-2">
        <VarianceBadge
          status={line.variance_status}
          value={line.variance_value}
          pct={line.variance_pct}
        />
      </td>
      <td className="px-3 py-2 w-24">
        {editingPct && canInlineEdit ? (
          <Input
            type="number"
            min={0}
            max={100}
            step={1}
            autoFocus
            value={draftPct}
            onChange={(e) => setDraftPct(e.target.value)}
            onBlur={commitPct}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                commitPct();
              } else if (e.key === 'Escape') {
                e.preventDefault();
                setDraftPct(line.percentage_complete == null ? '' : String(line.percentage_complete));
                setEditingPct(false);
              }
            }}
            className="h-7 text-sm"
            disabled={patchMut.isPending}
          />
        ) : (
          <span
            className={`tabular-nums ${canInlineEdit ? 'cursor-text' : ''}`}
            onClick={startEditPct}
          >
            {fmtPct(line.percentage_complete, 0)}
          </span>
        )}
      </td>
      <td className="w-8 px-2">
        <DropdownMenu>
          <DropdownMenuTrigger
            className="text-slate-400 hover:text-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-sy-teal"
            aria-label="Line actions"
          >
            <MoreHorizontal size={16} />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onOpenDrawer(line.id)}>
              Open line drawer
            </DropdownMenuItem>
            <DropdownMenuItem
              disabled={!isBudgetEditable(budget.status) || !inlineEditEnabled}
              onClick={() => onOpenDrawer(line.id, { focus: 'items' })}
            >
              Edit items ({line.items?.length ?? 0})
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </td>
    </tr>
  );
}
```

### R6.3 — BudgetLinesGrid (parent — H8 fix: extracted handleDragEnd, C8 KeyboardSensor)

```jsx
// frontend/src/components/budgets/BudgetLinesGrid.jsx (NEW)
import { useMemo, useState } from 'react';
import {
  DndContext, closestCenter,
  PointerSensor, KeyboardSensor,
  useSensor, useSensors,
} from '@dnd-kit/core';
import {
  SortableContext, arrayMove,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { SortableLineRow } from './SortableLineRow';
import { LineDrawer } from './LineDrawer';
import { useReorderBudgetLines } from '@/hooks/budgets';
import { useAuth } from '@/contexts/AuthContext';
import { hasPerm } from '@/lib/perms';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { isBudgetEditable } from '@/lib/budgetCapability';

/**
 * Pure handler — exported for unit tests (H8). Builds the new ordered id array
 * from a dnd-kit DragEndEvent. Returns null if nothing changed.
 */
export function buildReorderedIds(lines, event) {
  const { active, over } = event;
  if (!over || active.id === over.id) return null;
  const oldIdx = lines.findIndex((l) => l.id === active.id);
  const newIdx = lines.findIndex((l) => l.id === over.id);
  if (oldIdx < 0 || newIdx < 0) return null;
  return arrayMove(lines, oldIdx, newIdx).map((l) => l.id);
}

export function BudgetLinesGrid({ budget }) {
  const { user } = useAuth();
  const isDesktop = useIsDesktop();
  const canEdit = hasPerm(user, 'budgets.create') && isDesktop;
  const editable = isBudgetEditable(budget.status);

  const [openLineId, setOpenLineId] = useState(null);
  const [drawerFocus, setDrawerFocus] = useState(null);

  const reorderMut = useReorderBudgetLines(budget.id);

  // C8: KeyboardSensor + sortableKeyboardCoordinates for keyboard a11y
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  // B3: memoize sorted lines + itemIds so SortableContext doesn't see fresh
  // array identity on every render (would re-register sortables).
  const lines = useMemo(
    () => (budget.lines ?? []).slice().sort((a, b) => a.position - b.position),
    [budget.lines],
  );
  const itemIds = useMemo(() => lines.map((l) => l.id), [lines]);

  function handleDragEnd(event) {
    const orderedIds = buildReorderedIds(lines, event);
    if (orderedIds) reorderMut.mutate(orderedIds);
  }

  function openDrawer(lineId, opts = {}) {
    setOpenLineId(lineId);
    setDrawerFocus(opts.focus ?? null);
  }

  const dragDisabled = !editable || !canEdit || reorderMut.isPending;
  const inlineEditEnabled = canEdit;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900">Lines</h2>
        <span className="text-xs text-slate-500">{lines.length} lines</span>
      </div>

      {/* Mobile read-only banner — covers grid even when desktop user has narrow viewport */}
      {!isDesktop && (
        <div className="rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600">
          Read-only on mobile.
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <caption className="sr-only">Budget lines</caption>
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="w-8" />
              <th className="px-3 py-2 text-left">Cost Code</th>
              <th className="px-3 py-2 text-left">Description</th>
              <th className="px-3 py-2 text-right">Original</th>
              <th className="px-3 py-2 text-right">Current</th>
              <th className="px-3 py-2 text-right">Actuals</th>
              <th className="px-3 py-2 text-right">CNI</th>
              <th className="px-3 py-2 text-right">FTC</th>
              <th className="px-3 py-2 text-right">FFC</th>
              <th className="px-3 py-2 text-left">Variance</th>
              <th className="px-3 py-2 text-left">% Complete</th>
              <th className="w-8" />
            </tr>
          </thead>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={itemIds}
              strategy={verticalListSortingStrategy}
            >
              <tbody>
                {lines.map((line) => (
                  <SortableLineRow
                    key={line.id}
                    line={line}
                    budget={budget}
                    onOpenDrawer={openDrawer}
                    dragDisabled={dragDisabled}
                    inlineEditEnabled={inlineEditEnabled}
                  />
                ))}
                {lines.length === 0 && (
                  <tr>
                    <td colSpan={12} className="p-12 text-center text-slate-500">
                      No lines on this budget yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </SortableContext>
          </DndContext>
        </table>
      </div>

      <LineDrawer
        budget={budget}
        lineId={openLineId}
        focus={drawerFocus}
        onClose={() => { setOpenLineId(null); setDrawerFocus(null); }}
      />
    </div>
  );
}
```

### R6.4 — D8 reorder dependency (unchanged from v1)

`useReorderBudgetLines` POSTs to `/budgets/:id/lines/reorder` (endpoint #15). If R0 verification confirmed this endpoint does not exist:
- **STOP — escalate to backend-add patch.** Reorder is non-functional without atomic bulk-position write because optimistic order would desync from per-line PATCH versions.
- **Fallback:** disable drag (`dragDisabled = true` always); add backlog item.

This is the single biggest unknown in this Build Pack. **Resolve in §R0 before §R6 ships.**

### R6.5 — Cross-browser caveat (M8)

`<tr>` with CSS transform is supported but has rendering glitches on some legacy Safari versions. Test in Chrome / Firefox / Safari 16+ before ship. If glitches appear, fallback to `<div>`-based grid layout (loses table semantics; not ideal). Chrome/Firefox dominant on the desktop user base — flag this as a Safari-only concern.

### R6.6 — Commit boundary

```bash
git add src/components/budgets/SortableLineRow.jsx \
        src/components/budgets/BudgetLinesGrid.jsx \
        src/lib/budgetCapability.js
git commit -m "feat(2.4B-i): BudgetLinesGrid + drag-reorder (a11y-complete) + inline optimistic edits"
```

---
## §R7 — LineDrawer (explicit Save + items)

shadcn `Sheet` for the drawer. Form via `react-hook-form` + Zod. Items rendered as a sub-list.

### R7.1 — Form contract

Top-half form fields (line itself):
- `description` (optimistic on inline grid; explicit-Save in drawer)
- `notes` (sensitive — only writable if `view_sensitive`)
- `ftc_method` (server-confirmed; sensitive)
- `ftc_value` (server-confirmed; only when `ftc_method === 'Manual'`; sensitive)
- `cost_code_id` (server-confirmed; only mutable in Draft per R6.1)
- `percentage_complete` (optimistic on inline; explicit-Save in drawer)
- `version` (round-tripped, hidden field)

Bottom-half: items list with inline create / patch / delete (all server-confirmed).

### R7.2 — Drawer (audit-corrected: C5 dirtyFields, C6 cost-code stub, H6 close-confirm, M6 disable-during-pending, M1 useEffect deps)

```jsx
// frontend/src/components/budgets/LineDrawer.jsx (NEW)
import { useEffect, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetFooter,
} from '@/components/ui/sheet';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useAuth } from '@/contexts/AuthContext';
import { hasPerm } from '@/lib/perms';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { usePatchBudgetLine } from '@/hooks/budgets';
import { LineItemsPanel } from './LineItemsPanel';
import { CostCodePicker } from './CostCodePicker';
import { isBudgetEditable, isCostCodeMutable } from '@/lib/budgetCapability';

const FTC_METHODS = [
  { value: 'BudgetRemaining',    label: 'Budget remaining' },
  { value: 'CommittedOnly',      label: 'Committed only' },
  { value: 'PercentageComplete', label: 'Percentage complete' },
  { value: 'Manual',             label: 'Manual entry' },
];

// Client-side validation. Backend validates again — this catches typos early.
const FormSchema = z.object({
  description: z.string().max(2000).nullable(),
  notes: z.string().max(5000).nullable(),
  ftc_method: z.enum(['BudgetRemaining','CommittedOnly','PercentageComplete','Manual']).nullable(),
  ftc_value: z.union([z.coerce.number().min(0), z.null()]),
  cost_code_id: z.string().uuid(),
  percentage_complete: z.union([
    z.coerce.number().min(0).max(100),
    z.null(),
  ]),
});

export function LineDrawer({ budget, lineId, focus, onClose }) {
  const { user } = useAuth();
  const isDesktop = useIsDesktop();
  const canEdit = hasPerm(user, 'budgets.create') && isDesktop;
  const canSensitive = hasPerm(user, 'budgets.view_sensitive');
  const editable = isBudgetEditable(budget.status) && canEdit;
  const costCodeMutable = isCostCodeMutable(budget.status) && canEdit;

  const line = budget.lines?.find((l) => l.id === lineId);
  const patchMut = usePatchBudgetLine(budget.id);

  // H6: track close-confirm state
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false);

  const form = useForm({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      description: line?.description ?? '',
      notes: line?.notes ?? '',
      ftc_method: line?.ftc_method ?? 'BudgetRemaining',
      ftc_value: line?.ftc_value ?? null,
      cost_code_id: line?.cost_code_id ?? '',
      percentage_complete: line?.percentage_complete ?? null,
    },
  });

  // Reset form when line identity or version changes (M1: explicit deps; rationale = line-keyed reset)
  useEffect(() => {
    if (!line) return;
    form.reset({
      description: line.description ?? '',
      notes: line.notes ?? '',
      ftc_method: line.ftc_method ?? 'BudgetRemaining',
      ftc_value: line.ftc_value ?? null,
      cost_code_id: line.cost_code_id ?? '',
      percentage_complete: line.percentage_complete ?? null,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [line?.id, line?.version]);

  if (!line) return null;

  const ftcMethod = form.watch('ftc_method');

  // C5 fix: build patch body from dirtyFields only + version + defensive cost_code filter
  function buildPatchBody(values, dirtyFields) {
    const body = { version: line.version };
    if (dirtyFields.description) body.description = values.description;
    if (dirtyFields.notes) body.notes = values.notes;
    if (dirtyFields.ftc_method) body.ftc_method = values.ftc_method;
    if (dirtyFields.ftc_value) body.ftc_value = values.ftc_value;
    if (dirtyFields.percentage_complete) body.percentage_complete = values.percentage_complete;
    // Defensive: only send cost_code_id if mutable AND dirty
    if (dirtyFields.cost_code_id && costCodeMutable) {
      body.cost_code_id = values.cost_code_id;
    }
    return body;
  }

  async function onSave(values) {
    const body = buildPatchBody(values, form.formState.dirtyFields);
    // If only `version` is in body (nothing dirty), short-circuit
    if (Object.keys(body).length === 1) return;
    try {
      await patchMut.mutateAsync({ lineId: line.id, body, optimistic: false });
      // Form re-resets via useEffect on line.version change after server confirms.
    } catch {
      // toast already fired in hook
    }
  }

  // H6: close handler with dirty-confirm
  function handleSheetOpenChange(open) {
    if (open) return;
    if (form.formState.isDirty) {
      setCloseConfirmOpen(true);
      return;
    }
    onClose();
  }

  function discardAndClose() {
    setCloseConfirmOpen(false);
    onClose();
  }

  // M6: disable ALL fields during pending (not just Save button) to avoid form-reset clobbering typing
  const fieldsDisabled = !editable || patchMut.isPending;

  return (
    <>
      <Sheet open={!!lineId} onOpenChange={handleSheetOpenChange}>
        <SheetContent className="w-full max-w-xl overflow-y-auto sm:max-w-2xl">
          <SheetHeader>
            <SheetTitle>
              {(line.cost_code_label ?? line.cost_code_id.slice(-6))} — line v{line.version}
            </SheetTitle>
          </SheetHeader>

          <form
            onSubmit={form.handleSubmit(onSave, () => {
              toast.error('Please fix the highlighted errors before saving.');
            })}
            className="space-y-4 py-4"
          >
            {/* description */}
            <div className="space-y-1">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                {...form.register('description')}
                disabled={fieldsDisabled}
              />
            </div>

            {/* notes (sensitive — only shown if user has view_sensitive) */}
            {canSensitive && (
              <div className="space-y-1">
                <Label htmlFor="notes">Notes (sensitive)</Label>
                <Textarea
                  id="notes"
                  rows={4}
                  {...form.register('notes')}
                  disabled={fieldsDisabled}
                />
              </div>
            )}

            {/* ftc_method */}
            <div className="space-y-1">
              <Label>
                FTC method {!canSensitive && (
                  <span className="text-xs text-slate-500">(hidden — request elevated access)</span>
                )}
              </Label>
              <Controller
                name="ftc_method"
                control={form.control}
                render={({ field }) => (
                  <Select
                    value={field.value ?? 'BudgetRemaining'}
                    onValueChange={field.onChange}
                    disabled={fieldsDisabled || !canSensitive}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FTC_METHODS.map((m) => (
                        <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            {/* ftc_value (only when Manual) */}
            {ftcMethod === 'Manual' && canSensitive && (
              <div className="space-y-1">
                <Label htmlFor="ftc_value">Manual FTC (£)</Label>
                <Input
                  id="ftc_value"
                  type="number"
                  step="0.01"
                  {...form.register('ftc_value')}
                  disabled={fieldsDisabled}
                />
              </div>
            )}

            {/* percentage_complete */}
            <div className="space-y-1">
              <Label htmlFor="percentage_complete">% Complete</Label>
              <Input
                id="percentage_complete"
                type="number"
                min={0}
                max={100}
                {...form.register('percentage_complete')}
                disabled={fieldsDisabled}
              />
            </div>

            {/* cost_code (Draft only) */}
            <div className="space-y-1">
              <Label>Cost code</Label>
              <Controller
                name="cost_code_id"
                control={form.control}
                render={({ field }) => (
                  <CostCodePicker
                    projectId={budget.project_id}
                    value={field.value}
                    onChange={(v) => form.setValue('cost_code_id', v, { shouldDirty: true })}
                    disabled={fieldsDisabled || !costCodeMutable}
                  />
                )}
              />
              {!costCodeMutable && (
                <p className="text-xs text-slate-500">
                  Cost code can only be changed while budget is Draft.
                </p>
              )}
            </div>

            <SheetFooter className="sticky bottom-0 -mx-6 border-t border-slate-200 bg-white px-6 py-3">
              <div className="flex w-full items-center justify-between">
                <span className="text-xs text-slate-500">
                  {form.formState.isDirty ? 'Unsaved changes' : 'No changes'}
                </span>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => handleSheetOpenChange(false)}
                  >
                    Close
                  </Button>
                  <Button
                    type="submit"
                    className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
                    disabled={!editable || patchMut.isPending || !form.formState.isDirty}
                  >
                    {patchMut.isPending ? 'Saving…' : 'Save'}
                  </Button>
                </div>
              </div>
            </SheetFooter>
          </form>

          {/* Items panel — separate from line-level form */}
          <div className="border-t border-slate-200 pt-6">
            <LineItemsPanel
              budget={budget}
              line={line}
              initialFocus={focus === 'items'}
            />
          </div>
        </SheetContent>
      </Sheet>

      {/* H6: close-with-dirty confirm */}
      <DiscardChangesDialog
        open={closeConfirmOpen}
        onConfirm={discardAndClose}
        onCancel={() => setCloseConfirmOpen(false)}
      />
    </>
  );
}

function DiscardChangesDialog({ open, onConfirm, onCancel }) {
  // Uses shadcn AlertDialog for proper focus trap + Escape handling.
  // `open` is controlled by the parent; AlertDialog respects it.
  return (
    <AlertDialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Discard unsaved changes?</AlertDialogTitle>
          <AlertDialogDescription>
            You have unsaved edits. Closing now will lose them.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>Keep editing</AlertDialogCancel>
          <AlertDialogAction
            className="bg-sy-orange text-white hover:brightness-110 active:brightness-95"
            onClick={onConfirm}
          >
            Discard
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

### R7.3 — CostCodePicker (C6 fix)

Real implementation depends on `useCostCodes(projectId)` from Foundation 1.6 (D13 [CONFIRM]). Fallback shows last-6 of UUID until labels load.

```jsx
// frontend/src/components/budgets/CostCodePicker.jsx (NEW)
import { useCostCodes } from '@/hooks/costCodes';   // [CONFIRM] D13 — adjust import path/signature
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

/**
 * D13 [CONFIRM]: useCostCodes expected signature: (projectId) → { data, isLoading }
 * where data = Array<{ id: string, code: string, label: string, enabled: boolean }>.
 *
 * If real hook differs, only this component needs adapting; consumers stay stable.
 */
export function CostCodePicker({ projectId, value, onChange, disabled }) {
  const { data: codes = [], isLoading } = useCostCodes(projectId);
  const selectedLabel = codes.find((c) => c.id === value)?.label;

  return (
    <Select
      value={value || ''}
      onValueChange={onChange}
      disabled={disabled || isLoading}
    >
      <SelectTrigger>
        <SelectValue
          placeholder={
            isLoading
              ? 'Loading cost codes…'
              : value
                ? (selectedLabel ?? `Code ${value.slice(-6)}`)
                : 'Select a cost code'
          }
        />
      </SelectTrigger>
      <SelectContent>
        {codes
          .filter((c) => c.enabled || c.id === value)
          .map((c) => (
            <SelectItem key={c.id} value={c.id}>
              {`${c.code} — ${c.label}`}
            </SelectItem>
          ))}
      </SelectContent>
    </Select>
  );
}
```

### R7.4 — LineItemsPanel (M2 confirm-on-delete; M6 disable during pending)

```jsx
// frontend/src/components/budgets/LineItemsPanel.jsx (NEW)
import { useState } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fmtGBP } from '@/lib/format';
import {
  useCreateLineItem, useUpdateLineItem, useDeleteLineItem,
} from '@/hooks/budgets';
import { useIsDesktop } from '@/lib/useIsDesktop';
import { isBudgetEditable } from '@/lib/budgetCapability';
import { ConfirmDialog } from './ConfirmDialog';

export function LineItemsPanel({ budget, line, initialFocus }) {
  const isDesktop = useIsDesktop();
  const editable = isBudgetEditable(budget.status) && isDesktop;
  const items = line.items ?? [];
  const createMut = useCreateLineItem(budget.id, line.id);
  const updateMut = useUpdateLineItem(budget.id, line.id);
  const deleteMut = useDeleteLineItem(budget.id, line.id);
  const [newItem, setNewItem] = useState({
    description: '', quantity: '', unit: '', unit_cost: '',
  });

  function addItem() {
    if (!newItem.description.trim()) return;
    const body = {
      description: newItem.description.trim(),
      quantity: Number(newItem.quantity) || 0,
      unit: newItem.unit || null,
      unit_cost: Number(newItem.unit_cost) || 0,
    };
    createMut.mutate(body, {
      onSuccess: () => setNewItem({ description: '', quantity: '', unit: '', unit_cost: '' }),
    });
  }

  function patchItemField(itemId, field, value) {
    updateMut.mutate({ itemId, body: { [field]: value } });
  }

  return (
    <div className="space-y-3" data-initial-focus={initialFocus ? 'items' : ''}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">Items</h3>
        <span className="text-xs text-slate-500">{items.length} items</span>
      </div>

      <div className="overflow-x-auto rounded-md border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-2 py-1 text-left">Description</th>
              <th className="px-2 py-1 text-right">Qty</th>
              <th className="px-2 py-1 text-left">Unit</th>
              <th className="px-2 py-1 text-right">Unit cost</th>
              <th className="px-2 py-1 text-right">Amount</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id} className="border-t border-slate-100">
                <td className="px-2 py-1">
                  <Input
                    defaultValue={it.description}
                    disabled={!editable}
                    onBlur={(e) => e.target.value !== it.description &&
                      patchItemField(it.id, 'description', e.target.value)}
                    className="h-7"
                  />
                </td>
                <td className="px-2 py-1 text-right">
                  <Input
                    type="number"
                    defaultValue={it.quantity}
                    disabled={!editable}
                    onBlur={(e) => Number(e.target.value) !== it.quantity &&
                      patchItemField(it.id, 'quantity', Number(e.target.value))}
                    className="h-7 text-right"
                  />
                </td>
                <td className="px-2 py-1">
                  <Input
                    defaultValue={it.unit ?? ''}
                    disabled={!editable}
                    onBlur={(e) => (e.target.value || null) !== it.unit &&
                      patchItemField(it.id, 'unit', e.target.value || null)}
                    className="h-7"
                  />
                </td>
                <td className="px-2 py-1 text-right">
                  <Input
                    type="number"
                    step="0.01"
                    defaultValue={it.unit_cost}
                    disabled={!editable}
                    onBlur={(e) => Number(e.target.value) !== it.unit_cost &&
                      patchItemField(it.id, 'unit_cost', Number(e.target.value))}
                    className="h-7 text-right"
                  />
                </td>
                <td className="px-2 py-1 text-right font-mono">{fmtGBP(it.amount)}</td>
                <td className="px-2 py-1">
                  {editable && (
                    <ConfirmDialog
                      title="Delete item?"
                      description="This will remove the item from the line. The line totals will recalculate."
                      confirmLabel="Delete"
                      variant="destructive"
                      isPending={deleteMut.isPending}
                      onConfirm={() => deleteMut.mutate(it.id)}
                      trigger={
                        <button
                          type="button"
                          className="text-slate-400 hover:text-rose-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-sy-orange"
                          aria-label={`Delete item ${it.description}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      }
                    />
                  )}
                </td>
              </tr>
            ))}
            {!items.length && (
              <tr><td colSpan={6} className="p-4 text-center text-slate-400">No items.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {editable && (
        <div className="rounded-md border border-dashed border-slate-300 p-2">
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <label className="text-xs text-slate-600">Description</label>
              <Input
                value={newItem.description}
                onChange={(e) => setNewItem({ ...newItem, description: e.target.value })}
                placeholder="e.g. 25 kg cement"
                className="h-8"
                disabled={createMut.isPending}
              />
            </div>
            <div className="w-20 space-y-1">
              <label className="text-xs text-slate-600">Qty</label>
              <Input
                type="number"
                value={newItem.quantity}
                onChange={(e) => setNewItem({ ...newItem, quantity: e.target.value })}
                className="h-8 text-right"
                disabled={createMut.isPending}
              />
            </div>
            <div className="w-20 space-y-1">
              <label className="text-xs text-slate-600">Unit</label>
              <Input
                value={newItem.unit}
                onChange={(e) => setNewItem({ ...newItem, unit: e.target.value })}
                className="h-8"
                disabled={createMut.isPending}
              />
            </div>
            <div className="w-24 space-y-1">
              <label className="text-xs text-slate-600">Unit £</label>
              <Input
                type="number"
                step="0.01"
                value={newItem.unit_cost}
                onChange={(e) => setNewItem({ ...newItem, unit_cost: e.target.value })}
                className="h-8 text-right"
                disabled={createMut.isPending}
              />
            </div>
            <Button
              type="button"
              size="sm"
              className="bg-sy-teal text-white hover:brightness-110 active:brightness-95"
              disabled={createMut.isPending || !newItem.description.trim()}
              onClick={addItem}
            >
              <Plus size={14} className="mr-1" /> Add
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

### R7.5 — Conflict toast — manual verification

1. Tab A → open line drawer, edit description, leave open (don't Save).
2. Tab B → same line, edit description, Save (succeeds; version N → N+1).
3. Tab A → click Save. Expected: 409 from backend, toast "This line was edited elsewhere. Reload to see the latest." with Reload action.
4. Click Reload → cache invalidates → drawer re-renders with N+1 line. Form re-resets via useEffect.

### R7.6 — Commit boundary

```bash
git add src/components/budgets/LineDrawer.jsx \
        src/components/budgets/LineItemsPanel.jsx \
        src/components/budgets/CostCodePicker.jsx
git commit -m "feat(2.4B-i): LineDrawer (dirty-fields patch, close-confirm) + items panel + cost-code picker"
```

---
## §R8 — Component tests

**Stack:** vitest + @testing-library/react + @testing-library/user-event v14 (`setup()` pattern) + msw v2.
**Target count:** **29 functions** across 11 areas (was 25 in v1). The 8 inventory items below not shown in §R8.5 follow patterns identical to the samples and are <20 lines each.
**Coverage philosophy:** mirror Chat 16's pattern — direct ✅ for high-value paths.

### R8.1 — Test inventory

```
TestBudgetsListRender (3)
  test_list_renders_empty_state
  test_list_renders_status_badges_per_row
  test_list_create_button_hidden_for_readonly_user

TestBudgetsListPermGate (1)                                    [NEW v2]
  test_list_blocks_user_without_budgets_read

TestBudgetDetailRender (3)
  test_detail_renders_header_totals
  test_detail_renders_lines_grid
  test_detail_renders_variance_badge_correct_band

TestSensitiveGating (3)                                        [+1 v2]
  test_sensitive_fields_hidden_for_user_without_view_sensitive
  test_sensitive_fields_visible_for_admin
  test_schema_accepts_payload_with_sensitive_fields_omitted    [NEW v2 — C2]

TestStateMachineUI (5)
  test_activate_button_only_in_draft
  test_lock_button_only_in_active
  test_unlock_disabled_for_non_admin
  test_close_confirms_with_orange_dialog_and_reason
  test_new_version_blocked_from_draft_via_button_hidden

TestLineCRUD (5)
  test_drawer_opens_with_current_values
  test_drawer_save_sends_only_dirty_fields_with_version        [v2 reframed — C5]
  test_drawer_save_409_shows_conflict_toast_with_reload
  test_inline_description_optimistic_flip
  test_inline_description_optimistic_rollback_on_error

TestItems (3)
  test_add_item_via_drawer_calls_create
  test_delete_item_confirms_then_calls_delete                  [v2 reframed — M2]
  test_item_inputs_disabled_when_budget_locked

TestReorder (2)
  test_build_reordered_ids_pure_function                       [v2 reframed — H8]
  test_reorder_optimistically_swaps_position_in_cache

TestRefreshAttention (2)
  test_refresh_button_visible_only_for_admin
  test_refresh_click_invalidates_list_query

TestMobileFloor (2)                                            [NEW v2 — H1]
  test_inline_edit_disabled_on_mobile_viewport
  test_lifecycle_buttons_hidden_on_mobile_viewport
```

Total: **29 functions** (target was ≥27 — exceeds).

### R8.2 — Fixtures (C3 fix)

```js
// frontend/src/test/mocks/fixtures.js (NEW)

const BUDGET_ID = '11111111-1111-1111-1111-111111111111';
const PROJECT_ID = '22222222-2222-2222-2222-222222222222';
const TENANT_ID = '33333333-3333-3333-3333-333333333333';
const ENTITY_ID = '44444444-4444-4444-4444-444444444444';
const APPRAISAL_ID = '55555555-5555-5555-5555-555555555555';
const COST_CODE_ID = '66666666-6666-6666-6666-666666666666';
const LINE_ID_1 = '77777777-7777-7777-7777-777777777777';
const LINE_ID_2 = '88888888-8888-8888-8888-888888888888';
const LINE_ID_3 = '99999999-9999-9999-9999-999999999999';
const ITEM_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

export const IDS = {
  BUDGET_ID, PROJECT_ID, TENANT_ID, ENTITY_ID, APPRAISAL_ID,
  COST_CODE_ID, LINE_ID_1, LINE_ID_2, LINE_ID_3, ITEM_ID,
};

/**
 * Build a budget line. Pass overrides; sensible defaults otherwise.
 * Money values are returned as numbers (matches backend coercion expectation).
 */
export function mockLine(overrides = {}) {
  return {
    id: overrides.id ?? LINE_ID_1,
    budget_id: BUDGET_ID,
    cost_code_id: COST_CODE_ID,
    cost_code_label: 'CC.01.10 — Substructure',
    description: 'Test line',
    position: 0,
    original_budget: 100000,
    current_budget: 100000,
    actuals_total: 30000,
    committed_not_invoiced: 20000,
    ftc_method: 'BudgetRemaining',
    ftc_value: 50000,
    ffc: 100000,
    variance_value: 0,
    variance_pct: 0,
    variance_status: 'Green',
    percentage_complete: 30,
    notes: null,
    version: 1,
    items: [],
    ...overrides,
  };
}

export function mockItem(overrides = {}) {
  return {
    id: overrides.id ?? ITEM_ID,
    budget_line_id: LINE_ID_1,
    description: 'Cement 25kg bag',
    quantity: 100,
    unit: 'bag',
    unit_cost: 8.5,
    amount: 850,
    notes: null,
    position: 0,
    ...overrides,
  };
}

export function mockBudget(overrides = {}) {
  const lines = overrides.lines ?? [
    mockLine({ id: LINE_ID_1, position: 0 }),
    mockLine({
      id: LINE_ID_2,
      position: 1,
      cost_code_label: 'CC.02.20 — Frame',
      description: 'Steel frame',
      original_budget: 250000,
      current_budget: 250000,
      ftc_value: 200000,
      ffc: 250000,
      variance_status: 'Green',
    }),
    mockLine({
      id: LINE_ID_3,
      position: 2,
      cost_code_label: 'CC.03.30 — Envelope',
      description: 'Cladding',
      variance_status: 'Amber',
      variance_value: 5000,
      variance_pct: 4.0,
    }),
  ];

  // Sum-aggregate for headers if not overridden
  const total_original = lines.reduce((s, l) => s + l.original_budget, 0);
  const total_current = lines.reduce((s, l) => s + l.current_budget, 0);
  const total_actuals = lines.reduce((s, l) => s + l.actuals_total, 0);
  const total_cni = lines.reduce((s, l) => s + l.committed_not_invoiced, 0);
  const total_ffc = lines.reduce((s, l) => s + l.ffc, 0);
  const total_var = total_ffc - total_current;

  return {
    id: BUDGET_ID,
    tenant_id: TENANT_ID,
    project_id: PROJECT_ID,
    entity_id: ENTITY_ID,
    appraisal_id: APPRAISAL_ID,
    version_number: 1,
    status: 'Active',
    is_current: true,
    superseded_by_id: null,
    total_original_budget: total_original,
    total_current_budget: total_current,
    total_actuals: total_actuals,
    total_cni: total_cni,
    total_ftc: 250000,
    total_ffc: total_ffc,
    total_variance: total_var,
    total_variance_pct: total_var === 0 ? 0 : (total_var / total_current) * 100,
    total_variance_status: total_var > 0 ? 'Amber' : 'Green',
    created_at: '2026-01-01T00:00:00Z',
    activated_at: '2026-01-02T00:00:00Z',
    locked_at: null,
    closed_at: null,
    superseded_at: null,
    summary_refreshed_at: '2026-05-01T00:00:00Z',
    requires_attention: false,
    lines,
    ...overrides,
  };
}

/**
 * Strip sensitive fields from a budget — emulates backend behaviour for
 * users without budgets.view_sensitive.
 */
export function stripSensitive(budget) {
  return {
    ...budget,
    total_ftc: undefined,
    lines: budget.lines?.map(({ ftc_method, ftc_value, notes, ...rest }) => rest),
  };
}
```

### R8.3 — MSW server (C4 imports)

```js
// frontend/src/test/mocks/server.js (NEW)
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';
import { mockBudget, mockLine, IDS } from './fixtures';

export const handlers = [
  http.get('/api/v1/projects/:projectId/budgets', () =>
    HttpResponse.json([mockBudget()])),
  http.get('/api/v1/budgets/:id', () => HttpResponse.json(mockBudget())),
  http.patch('/api/v1/budgets/:id/lines/:lineId', async ({ request, params }) => {
    const body = await request.json();
    return HttpResponse.json(
      mockLine({
        id: params.lineId,
        ...body,
        version: (body.version ?? 1) + 1,
      }),
    );
  }),
  http.post('/api/v1/budgets/:id/lines/reorder', () =>
    HttpResponse.json(mockBudget())),
  http.post('/api/v1/budgets/:id/activate', () =>
    HttpResponse.json(mockBudget({ status: 'Active' }))),
  http.post('/api/v1/budgets/:id/lock', () =>
    HttpResponse.json(mockBudget({ status: 'Locked' }))),
  http.post('/api/v1/budgets/:id/unlock', () =>
    HttpResponse.json(mockBudget({ status: 'Active' }))),
  http.post('/api/v1/budgets/:id/close', () =>
    HttpResponse.json(mockBudget({ status: 'Closed' }))),
  http.post('/api/v1/budgets/:id/new-version', () =>
    HttpResponse.json(mockBudget({ id: 'new-id', version_number: 2, status: 'Draft' }))),
  http.post('/api/v1/budgets/refresh-attention', () =>
    HttpResponse.json({ scanned: 1, flagged: 0, cleared: 0 })),
  http.post('/api/v1/projects/:projectId/budgets/from-appraisal', () =>
    HttpResponse.json(mockBudget())),
  http.post('/api/v1/budgets/:id/lines/:lineId/items', async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({
      id: 'new-item-id',
      budget_line_id: IDS.LINE_ID_1,
      description: body.description,
      quantity: body.quantity,
      unit: body.unit,
      unit_cost: body.unit_cost,
      amount: body.quantity * body.unit_cost,
      notes: body.notes ?? null,
      position: 0,
    });
  }),
  http.delete('/api/v1/budgets/:id/lines/:lineId/items/:itemId', () =>
    new HttpResponse(null, { status: 204 })),
];

export const server = setupServer(...handlers);
```

### R8.4 — Test wrapper (C4 imports complete)

```jsx
// frontend/src/test/renderWithProviders.jsx (NEW)
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { render } from '@testing-library/react';
import { Toaster } from '@/components/ui/sonner';
import { AuthContext } from '@/contexts/AuthContext';

export function renderWithProviders(ui, { user, route = '/', client, routePattern } = {}) {
  const qc = client ?? new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const defaultUser = user ?? {
    id: 'u1', email: 'pm@test.local',
    permissions: ['budgets.read', 'budgets.create'],
  };

  // If routePattern given, mount the page under that pattern so useParams resolves.
  // Otherwise just render ui at the route.
  const tree = routePattern ? (
    <Routes>
      <Route path={routePattern} element={ui} />
    </Routes>
  ) : ui;

  return render(
    <QueryClientProvider client={qc}>
      <AuthContext.Provider value={{ user: defaultUser }}>
        <MemoryRouter initialEntries={[route]}>
          {tree}
          <Toaster />
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}

/**
 * Helper to mock matchMedia for mobile-floor tests (TestMobileFloor).
 */
export function mockMatchMedia(isDesktop) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query) => ({
      matches: isDesktop,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}
```

### R8.5 — Sample tests (paste-ready, full imports)

```jsx
// frontend/src/components/budgets/__tests__/BudgetsList.test.jsx
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '@/test/mocks/server';
import { mockBudget } from '@/test/mocks/fixtures';
import { renderWithProviders, mockMatchMedia } from '@/test/renderWithProviders';
import BudgetsList from '@/pages/projects/BudgetsList';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('TestBudgetsListRender', () => {
  it('test_list_renders_empty_state', async () => {
    mockMatchMedia(true);
    server.use(
      http.get('/api/v1/projects/:p/budgets', () => HttpResponse.json([])),
    );
    renderWithProviders(<BudgetsList />, {
      route: '/projects/p1/budgets',
      routePattern: '/projects/:projectId/budgets',
    });
    await waitFor(() =>
      expect(screen.getByText(/No budgets yet/i)).toBeInTheDocument(),
    );
  });

  it('test_list_renders_status_badges_per_row', async () => {
    mockMatchMedia(true);
    server.use(
      http.get('/api/v1/projects/:p/budgets', () => HttpResponse.json([
        mockBudget({ status: 'Active' }),
        mockBudget({ id: 'b2', status: 'Locked', version_number: 2 }),
      ])),
    );
    renderWithProviders(<BudgetsList />, {
      route: '/projects/p1/budgets',
      routePattern: '/projects/:projectId/budgets',
    });
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText('Locked')).toBeInTheDocument();
    });
  });

  it('test_list_create_button_hidden_for_readonly_user', async () => {
    mockMatchMedia(true);
    renderWithProviders(<BudgetsList />, {
      route: '/projects/p1/budgets',
      routePattern: '/projects/:projectId/budgets',
      user: { id: 'u', email: 'r@x', permissions: ['budgets.read'] },
    });
    await waitFor(() =>
      expect(screen.queryByText(/Create from Approved Appraisal/i)).not.toBeInTheDocument(),
    );
  });
});

describe('TestBudgetsListPermGate', () => {
  it('test_list_blocks_user_without_budgets_read', () => {
    mockMatchMedia(true);
    renderWithProviders(<BudgetsList />, {
      route: '/projects/p1/budgets',
      routePattern: '/projects/:projectId/budgets',
      user: { id: 'u', email: 'no@x', permissions: [] },
    });
    expect(screen.getByText(/don't have access/i)).toBeInTheDocument();
  });
});
```

```jsx
// frontend/src/components/budgets/__tests__/LineDrawer.test.jsx
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '@/test/mocks/server';
import { mockBudget, mockLine, IDS } from '@/test/mocks/fixtures';
import { renderWithProviders, mockMatchMedia } from '@/test/renderWithProviders';
import BudgetDetail from '@/pages/projects/BudgetDetail';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('TestLineCRUD', () => {
  // C5 audit: this replaces v1's "test_drawer_save_sends_patch_with_version".
  // v2 contract: body MUST contain only dirty fields + version (no untouched fields).
  it('test_drawer_save_sends_only_dirty_fields_with_version', async () => {
    mockMatchMedia(true);
    const user = userEvent.setup();
    const calls = [];
    server.use(
      http.patch('/api/v1/budgets/:b/lines/:l', async ({ request, params }) => {
        calls.push(await request.json());
        return HttpResponse.json(
          mockLine({ id: params.l, description: 'Plant hire — week 4', version: 2 }),
        );
      }),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
    });
    // Open drawer via dropdown
    const triggers = await screen.findAllByLabelText(/Line actions/i);
    await user.click(triggers[0]);
    await user.click(await screen.findByText(/Open line drawer/i));
    // Edit ONLY description
    const desc = await screen.findByLabelText(/^Description/);
    await user.clear(desc);
    await user.type(desc, 'Plant hire — week 4');
    await user.click(screen.getByRole('button', { name: /Save/ }));
    await waitFor(() => expect(calls).toHaveLength(1));
    // Critical assertion: body has ONLY description + version (not notes, ftc_method, etc.)
    expect(calls[0]).toEqual({
      description: 'Plant hire — week 4',
      version: 1,
    });
    expect(calls[0]).not.toHaveProperty('cost_code_id');
    expect(calls[0]).not.toHaveProperty('ftc_method');
  });

  it('test_drawer_save_409_shows_conflict_toast_with_reload', async () => {
    mockMatchMedia(true);
    const user = userEvent.setup();
    server.use(
      http.patch('/api/v1/budgets/:b/lines/:l', () =>
        HttpResponse.json({ detail: 'Stale version' }, { status: 409 })),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
    });
    const triggers = await screen.findAllByLabelText(/Line actions/i);
    await user.click(triggers[0]);
    await user.click(await screen.findByText(/Open line drawer/i));
    const desc = await screen.findByLabelText(/^Description/);
    await user.clear(desc);
    await user.type(desc, 'Conflicted edit');
    await user.click(screen.getByRole('button', { name: /Save/ }));
    await waitFor(() =>
      expect(screen.getByText(/edited elsewhere/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: /Reload/ })).toBeInTheDocument();
  });
});
```

```jsx
// frontend/src/components/budgets/__tests__/StateMachine.test.jsx
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '@/test/mocks/server';
import { mockBudget, IDS } from '@/test/mocks/fixtures';
import { renderWithProviders, mockMatchMedia } from '@/test/renderWithProviders';
import BudgetDetail from '@/pages/projects/BudgetDetail';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('TestStateMachineUI', () => {
  it('test_unlock_disabled_for_non_admin', async () => {
    mockMatchMedia(true);
    server.use(
      http.get('/api/v1/budgets/:b', () =>
        HttpResponse.json(mockBudget({ status: 'Locked' }))),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
      user: { id: 'u', email: 'p@x', permissions: ['budgets.read', 'budgets.create'] },
    });
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /^Unlock$/ })).not.toBeInTheDocument(),
    );
  });

  it('test_close_confirms_with_orange_dialog_and_reason', async () => {
    mockMatchMedia(true);
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/budgets/:b', () =>
        HttpResponse.json(mockBudget({ status: 'Active' }))),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
      user: { id: 'u', email: 'a@x', permissions: ['budgets.read', 'budgets.create', 'budgets.admin'] },
    });
    await user.click(await screen.findByRole('button', { name: /^Close$/ }));
    expect(screen.getByText(/Close budget\?/)).toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: /^Close budget$/ });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/Reason/), 'CT year-end');
    expect(confirm).toBeEnabled();
    expect(confirm.className).toMatch(/bg-sy-orange/);
  });
});
```

```jsx
// frontend/src/components/budgets/__tests__/Reorder.test.jsx
import { describe, it, expect } from 'vitest';
import { buildReorderedIds } from '../BudgetLinesGrid';
import { mockLine, IDS } from '@/test/mocks/fixtures';

describe('TestReorder', () => {
  // H8 fix: test the pure handler, not the full DOM-level drag.
  it('test_build_reordered_ids_pure_function', () => {
    const lines = [
      mockLine({ id: IDS.LINE_ID_1, position: 0 }),
      mockLine({ id: IDS.LINE_ID_2, position: 1 }),
      mockLine({ id: IDS.LINE_ID_3, position: 2 }),
    ];
    // Drag line 1 onto line 3's spot
    const event = {
      active: { id: IDS.LINE_ID_1 },
      over:   { id: IDS.LINE_ID_3 },
    };
    expect(buildReorderedIds(lines, event)).toEqual([
      IDS.LINE_ID_2, IDS.LINE_ID_3, IDS.LINE_ID_1,
    ]);
  });

  it('test_build_reordered_ids_no_change_returns_null', () => {
    const lines = [mockLine({ id: IDS.LINE_ID_1 })];
    expect(buildReorderedIds(lines, { active: { id: IDS.LINE_ID_1 }, over: null })).toBeNull();
    expect(buildReorderedIds(lines, {
      active: { id: IDS.LINE_ID_1 },
      over: { id: IDS.LINE_ID_1 },
    })).toBeNull();
  });
});
```

```jsx
// frontend/src/components/budgets/__tests__/MobileFloor.test.jsx
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { server } from '@/test/mocks/server';
import { IDS } from '@/test/mocks/fixtures';
import { renderWithProviders, mockMatchMedia } from '@/test/renderWithProviders';
import BudgetDetail from '@/pages/projects/BudgetDetail';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('TestMobileFloor', () => {
  it('test_lifecycle_buttons_hidden_on_mobile_viewport', async () => {
    mockMatchMedia(false); // mobile
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
      user: {
        id: 'u', email: 'a@x',
        permissions: ['budgets.read', 'budgets.create', 'budgets.admin'],
      },
    });
    // Wait for budget detail to render
    await waitFor(() => expect(screen.getByText(/Budget v1/)).toBeInTheDocument());
    // No lifecycle button should appear (Active on a desktop viewport would show Lock)
    expect(screen.queryByRole('button', { name: /^Lock$/ })).not.toBeInTheDocument();
  });

  it('test_inline_edit_disabled_on_mobile_viewport', async () => {
    mockMatchMedia(false);
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
    });
    await waitFor(() => expect(screen.getByText(/Lines/i)).toBeInTheDocument());
    // Description cell should not have cursor-text class
    const descCells = screen.queryAllByText('Test line');
    expect(descCells.length).toBeGreaterThan(0);          // avoid vacuous pass
    descCells.forEach((cell) => {
      expect(cell.className ?? '').not.toMatch(/cursor-text/);
    });
  });
});
```

```jsx
// frontend/src/components/budgets/__tests__/SensitiveSchema.test.jsx
import { describe, it, expect } from 'vitest';
import { BudgetDetailSchema } from '@/lib/schemas/budgets';
import { mockBudget, stripSensitive } from '@/test/mocks/fixtures';

describe('TestSensitiveGating', () => {
  // C2 audit: schema MUST accept payloads where backend stripped sensitive fields.
  it('test_schema_accepts_payload_with_sensitive_fields_omitted', () => {
    const stripped = stripSensitive(mockBudget());
    const result = BudgetDetailSchema.safeParse(stripped);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.lines[0].ftc_method).toBeUndefined();
      expect(result.data.lines[0].ftc_value).toBeUndefined();
      expect(result.data.lines[0].notes).toBeUndefined();
    }
  });
});
```

```jsx
// frontend/src/components/budgets/__tests__/SensitiveDOM.test.jsx
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '@/test/mocks/server';
import { mockBudget, stripSensitive, IDS } from '@/test/mocks/fixtures';
import { renderWithProviders } from '@/test/renderWithProviders';
import BudgetDetail from '@/pages/projects/BudgetDetail';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('TestSensitiveGating (DOM)', () => {
  it('test_sensitive_fields_hidden_for_user_without_view_sensitive', async () => {
    server.use(
      http.get('/api/v1/budgets/:b', () =>
        HttpResponse.json(stripSensitive(mockBudget()))),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
      user: { id: 'u', email: 'pm@x', permissions: ['budgets.read', 'budgets.create'] },
    });
    // SensitiveBanner should be visible
    await waitFor(() =>
      expect(screen.getByText(/sensitive fields .* are hidden/i)).toBeInTheDocument(),
    );
    // FTC column cells render '—' for stripped lines
    const rows = screen.getAllByTestId(/budget-line-row-/);
    expect(rows.length).toBeGreaterThan(0);
    rows.forEach((row) => {
      // The 8th cell (FTC) — index 7 in the cell array
      const cells = within(row).getAllByRole('cell');
      expect(cells[7].textContent).toMatch(/—/);
    });
  });

  it('test_sensitive_fields_visible_for_admin', async () => {
    server.use(
      http.get('/api/v1/budgets/:b', () => HttpResponse.json(mockBudget())),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
      user: {
        id: 'u', email: 'a@x',
        permissions: ['budgets.read', 'budgets.create', 'budgets.admin', 'budgets.view_sensitive'],
      },
    });
    // SensitiveBanner should NOT be visible
    await waitFor(() => expect(screen.getByText(/Budget v1/)).toBeInTheDocument());
    expect(screen.queryByText(/sensitive fields .* are hidden/i)).not.toBeInTheDocument();
  });
});
```

```jsx
// frontend/src/components/budgets/__tests__/Optimistic.test.jsx
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse, delay } from 'msw';
import { server } from '@/test/mocks/server';
import { mockBudget, mockLine, IDS } from '@/test/mocks/fixtures';
import { renderWithProviders } from '@/test/renderWithProviders';
import BudgetDetail from '@/pages/projects/BudgetDetail';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('TestOptimistic', () => {
  // The grid inline-edit path: typing into a description span and pressing Enter
  // should flip the displayed text BEFORE the network request resolves.
  it('test_inline_description_optimistic_flip', async () => {
    const user = userEvent.setup();
    server.use(
      http.patch('/api/v1/budgets/:b/lines/:l', async ({ request, params }) => {
        await delay(200);   // simulate slow server
        const body = await request.json();
        return HttpResponse.json(
          mockLine({ id: params.l, ...body, version: (body.version ?? 1) + 1 }),
        );
      }),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
    });
    // Wait for grid; click the first description span to enter edit mode
    const firstRow = await screen.findByTestId(`budget-line-row-${IDS.LINE_ID_1}`);
    const descSpan = within(firstRow).getByText('Test line');
    await user.click(descSpan);
    const input = within(firstRow).getByRole('textbox');
    await user.clear(input);
    await user.type(input, 'Optimistic value{Enter}');
    // Optimistic: text appears immediately even though server is delayed
    await waitFor(() =>
      expect(within(firstRow).getByText('Optimistic value')).toBeInTheDocument(),
    );
  });

  it('test_inline_description_optimistic_rollback_on_error', async () => {
    const user = userEvent.setup();
    server.use(
      http.patch('/api/v1/budgets/:b/lines/:l', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 })),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
    });
    const firstRow = await screen.findByTestId(`budget-line-row-${IDS.LINE_ID_1}`);
    const descSpan = within(firstRow).getByText('Test line');
    await user.click(descSpan);
    const input = within(firstRow).getByRole('textbox');
    await user.clear(input);
    await user.type(input, 'Will fail{Enter}');
    // After error, optimistic value rolled back to 'Test line'
    await waitFor(() =>
      expect(within(firstRow).getByText('Test line')).toBeInTheDocument(),
    );
    expect(within(firstRow).queryByText('Will fail')).not.toBeInTheDocument();
  });
});
```

```jsx
// frontend/src/components/budgets/__tests__/Items.test.jsx
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '@/test/mocks/server';
import { mockBudget, mockLine, mockItem, IDS } from '@/test/mocks/fixtures';
import { renderWithProviders } from '@/test/renderWithProviders';
import BudgetDetail from '@/pages/projects/BudgetDetail';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('TestItems', () => {
  it('test_add_item_via_drawer_calls_create', async () => {
    const user = userEvent.setup();
    const created = [];
    server.use(
      http.post('/api/v1/budgets/:b/lines/:l/items', async ({ request }) => {
        const body = await request.json();
        created.push(body);
        return HttpResponse.json(mockItem({ id: 'new', ...body, amount: body.quantity * body.unit_cost }));
      }),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
    });
    const triggers = await screen.findAllByLabelText(/Line actions/i);
    await user.click(triggers[0]);
    await user.click(await screen.findByText(/Open line drawer/i));
    // New-item form is at the bottom of the drawer
    await user.type(await screen.findByPlaceholderText(/25 kg cement/i), 'Aggregate 50mm');
    const qty = screen.getByLabelText(/Qty/i);
    await user.type(qty, '40');
    const unit = screen.getByLabelText(/Unit$/);  // exact 'Unit', not 'Unit £'
    await user.type(unit, 'tonne');
    const unitCost = screen.getByLabelText(/Unit £/i);
    await user.type(unitCost, '32.50');
    await user.click(screen.getByRole('button', { name: /^Add$/ }));
    await waitFor(() => expect(created).toHaveLength(1));
    expect(created[0]).toMatchObject({
      description: 'Aggregate 50mm',
      quantity: 40,
      unit: 'tonne',
      unit_cost: 32.5,
    });
  });

  it('test_delete_item_confirms_then_calls_delete', async () => {
    const user = userEvent.setup();
    const deletedIds = [];
    server.use(
      http.get('/api/v1/budgets/:b', () => HttpResponse.json(
        mockBudget({
          lines: [mockLine({ items: [mockItem({ id: 'i1', description: 'Doomed' })] })],
        }),
      )),
      http.delete('/api/v1/budgets/:b/lines/:l/items/:itemId', ({ params }) => {
        deletedIds.push(params.itemId);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
    });
    const triggers = await screen.findAllByLabelText(/Line actions/i);
    await user.click(triggers[0]);
    await user.click(await screen.findByText(/Open line drawer/i));
    // Click delete trash icon — opens ConfirmDialog
    await user.click(await screen.findByLabelText(/Delete item Doomed/i));
    expect(screen.getByText(/Delete item\?/i)).toBeInTheDocument();
    // Click the destructive confirm
    await user.click(screen.getByRole('button', { name: /^Delete$/ }));
    await waitFor(() => expect(deletedIds).toEqual(['i1']));
  });

  it('test_item_inputs_disabled_when_budget_locked', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/budgets/:b', () => HttpResponse.json(
        mockBudget({
          status: 'Locked',
          lines: [mockLine({ items: [mockItem()] })],
        }),
      )),
    );
    renderWithProviders(<BudgetDetail />, {
      route: `/projects/${IDS.PROJECT_ID}/budgets/${IDS.BUDGET_ID}`,
      routePattern: '/projects/:projectId/budgets/:budgetId',
    });
    const triggers = await screen.findAllByLabelText(/Line actions/i);
    await user.click(triggers[0]);
    await user.click(await screen.findByText(/Open line drawer/i));
    // The first description input in the items panel should be disabled
    await waitFor(() => expect(screen.getByText(/^Items$/)).toBeInTheDocument());
    const inputs = screen.getAllByDisplayValue(/Cement/i);
    expect(inputs.length).toBeGreaterThan(0);
    inputs.forEach((input) => expect(input).toBeDisabled());
  });
});
```

```jsx
// frontend/src/components/budgets/__tests__/RefreshAttention.test.jsx
import { describe, it, expect, beforeAll, afterAll, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '@/test/mocks/server';
import { renderWithProviders } from '@/test/renderWithProviders';
import BudgetsList from '@/pages/projects/BudgetsList';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('TestRefreshAttention', () => {
  it('test_refresh_button_visible_only_for_admin', async () => {
    renderWithProviders(<BudgetsList />, {
      route: '/projects/p1/budgets',
      routePattern: '/projects/:projectId/budgets',
      user: { id: 'u', email: 'pm@x', permissions: ['budgets.read', 'budgets.create'] },
    });
    await waitFor(() => expect(screen.getByText(/^Budgets$/)).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /Refresh attention/i })).not.toBeInTheDocument();
  });

  it('test_refresh_click_invalidates_list_query', async () => {
    const user = userEvent.setup();
    let listFetches = 0;
    server.use(
      http.get('/api/v1/projects/:p/budgets', () => {
        listFetches += 1;
        return HttpResponse.json([]);
      }),
      http.post('/api/v1/budgets/refresh-attention', () =>
        HttpResponse.json({ scanned: 5, flagged: 1, cleared: 0 })),
    );
    renderWithProviders(<BudgetsList />, {
      route: '/projects/p1/budgets',
      routePattern: '/projects/:projectId/budgets',
      user: {
        id: 'u', email: 'a@x',
        permissions: ['budgets.read', 'budgets.create', 'budgets.admin'],
      },
    });
    await waitFor(() => expect(listFetches).toBeGreaterThanOrEqual(1));
    const before = listFetches;
    await user.click(screen.getByRole('button', { name: /Refresh attention/i }));
    // After scan, list query is invalidated → refetch fires
    await waitFor(() => expect(listFetches).toBeGreaterThan(before));
  });
});
```

> The remaining inventory tests (`test_activate_button_only_in_draft`, `test_lock_button_only_in_active`, `test_new_version_blocked_from_draft_via_button_hidden`, `test_drawer_opens_with_current_values`, `test_detail_renders_header_totals`, `test_detail_renders_lines_grid`, `test_detail_renders_variance_badge_correct_band`, `test_reorder_optimistically_swaps_position_in_cache`) follow the same patterns established above. Implementer writes them out by copying the closest sample and adjusting assertions; each should be ≤ 20 lines.

### R8.6 — Run target

```bash
yarn test --run                 # vitest single run
yarn test --coverage            # confirm core paths covered ≥ 70%
```

### R8.7 — Commit boundary

```bash
git add src/test/ src/components/budgets/__tests__/ src/pages/projects/__tests__/
git commit -m "test(2.4B-i): 29 component tests across render/state/CRUD/items/reorder/mobile/sensitive"
```

---
## §R9 — Self-report template (fill at chat-end ritual)

```
### R0 — Baseline (frontend)
- git SHA before any work: <SHA>
- backend bootstrap rc / alembic / pytest: <0 / 0024_budgets / 664 passed>
- frontend deps absent at start: <list>
- vitest config block in vite.config.js: <yes | added>
- lib/api.js shape: <axios + withCredentials + /api/v1>
- path alias: <@→src>
- tailwind tokens registered: <sy-teal/sy-orange/sy-grey only | also -hover/-foreground>
- sonner Toaster wrapper: <present | created>
- /lines/reorder endpoint: <present | added in pre-prompt patch | fallback used>
- useApprovedAppraisals signature confirmed: <yes | wrapped>
- useCostCodes signature confirmed: <yes | wrapped>
- bundle size before any work: <KB / KB gzipped>

### R1 — Stack install
- @tanstack/react-query installed: <version>
- @tanstack/react-table installed: <version>
- @tanstack/react-query-devtools installed: <version>
- @dnd-kit/core+sortable+utilities: <versions | already present>
- vitest+RTL+user-event+msw: <versions | already present>
- yarn build after install: <clean | errors>

### R2 — Routes + shells
- Routes added at: <path>
- Page shells render: <yes | issue>
- useIsDesktop hook lands at: <path>

### R3 — API client + hooks
- All 14 endpoints wired: <yes | gaps>
- Endpoint #15 (reorder) backend status: <present | added | fallback used>
- Zod schemas mirror Pydantic with sensitive .nullable().optional(): <yes | deltas>
- Abort signals threaded: <yes>
- Patch body pre-validates against BudgetLinePatchSchema: <yes>

### R4 — BudgetsList
- TanStack Table columns rendered: <yes | issues>
- budgets.read perm gate enforced: <yes>
- CreateFromAppraisalDialog with { enabled }: <yes>
- Mobile floor (action buttons hidden <md): <yes>

### R5 — BudgetDetail header + lifecycle
- All 5 lifecycle buttons gate correctly per (status, perm) matrix: <yes | gaps>
- sy-orange destructive-confirms on Unlock / Close / New Version: <yes>
- Reason capture into audit-log: <yes>
- Brand classes use base tokens + text-white + brightness-110 (no -hover/-foreground): <yes>

### R6 — Lines grid
- KeyboardSensor + sortableKeyboardCoordinates wired: <yes>
- setActivatorNodeRef on drag handle: <yes>
- Drag-reorder smooth, optimistic, server bulk write succeeds: <yes | issue>
- Inline description / % complete optimistic, rollback on error: <yes>
- Sensitive ftc_value shows '—' for non-sensitive users: <yes>
- Mobile floor: inline edit disabled on <md viewport: <yes>

### R7 — LineDrawer + items
- Patch body built from dirtyFields only + version + cost-code defensive filter: <yes>
- All form fields disabled during patchMut.isPending: <yes>
- Close-with-dirty discard confirm: <yes>
- 409 conflict toast with Reload affordance: <yes>
- CostCodePicker shows label, falls back gracefully: <yes>
- Item delete confirm: <yes>

### R8 — Tests
- vitest count: <≥27>
- pass/fail summary: <…>
- Coverage %: <…>
- Sensitive-stripped schema test passes: <yes>
- Mobile-floor tests pass: <yes>
- Reorder pure-function test passes: <yes>

### Bundle delta
- before: <KB / KB gzipped>
- after:  <KB / KB gzipped>
- delta:  <+KB / +KB gzipped>

### Deviations from this Build Pack
- <list each deviation>

### Final state
- routes live: <yes>
- yarn build: <clean>
- yarn test --run: <pass count>
- CHANGELOG entry added: <yes>
```

---

## §R10 — Chat-end ritual

Mirror Chat 14 §11 / Chat 15 §3 / Chat 16 §11 pattern.

### R10.1 — Files committed checklist

```
1. ☐ frontend/package.json + frontend/yarn.lock
2. ☐ frontend/vite.config.js (modified — test block if absent)
3. ☐ frontend/src/test/setup.js (NEW — jest-dom matchers + matchMedia reset hook)
4. ☐ frontend/src/lib/queryClient.js (NEW)
5. ☐ frontend/src/main.jsx (modified — provider + Toaster wrap)
6. ☐ frontend/src/components/ui/sonner.jsx (NEW if absent — shadcn Toaster wrapper)
7. ☐ frontend/src/lib/perms.js (NEW)
8. ☐ frontend/src/lib/useIsDesktop.js (NEW — mobile floor enforcement)
9. ☐ frontend/src/lib/format.js (NEW)
10. ☐ frontend/src/lib/budgetCapability.js (NEW)
11. ☐ frontend/src/lib/api/budgets.js (NEW)
12. ☐ frontend/src/lib/schemas/budgets.js (NEW)
13. ☐ frontend/src/hooks/budgets.js (NEW)
14. ☐ frontend/src/pages/projects/BudgetsList.jsx (NEW)
15. ☐ frontend/src/pages/projects/BudgetDetail.jsx (NEW)
16. ☐ frontend/src/components/budgets/StatusBadge.jsx (NEW)
17. ☐ frontend/src/components/budgets/VarianceBadge.jsx (NEW)
18. ☐ frontend/src/components/budgets/BudgetsTable.jsx (NEW)
19. ☐ frontend/src/components/budgets/CreateFromAppraisalDialog.jsx (NEW)
20. ☐ frontend/src/components/budgets/BudgetHeader.jsx (NEW)
21. ☐ frontend/src/components/budgets/LifecycleActions.jsx (NEW)
22. ☐ frontend/src/components/budgets/ConfirmDialog.jsx (NEW)
23. ☐ frontend/src/components/budgets/SensitiveBanner.jsx (NEW)
24. ☐ frontend/src/components/budgets/SortableLineRow.jsx (NEW)
25. ☐ frontend/src/components/budgets/BudgetLinesGrid.jsx (NEW — exports buildReorderedIds for testability)
26. ☐ frontend/src/components/budgets/LineDrawer.jsx (NEW — exports DiscardChangesDialog as nested helper)
27. ☐ frontend/src/components/budgets/LineItemsPanel.jsx (NEW)
28. ☐ frontend/src/components/budgets/CostCodePicker.jsx (NEW)
29. ☐ frontend/src/test/mocks/server.js (NEW)
30. ☐ frontend/src/test/mocks/fixtures.js (NEW — exports IDS, mockBudget, mockLine, mockItem, stripSensitive)
31. ☐ frontend/src/test/renderWithProviders.jsx (NEW — exports renderWithProviders, mockMatchMedia)
32. ☐ frontend/src/components/budgets/__tests__/*.test.jsx (NEW — 10 files, 29 tests)
33. ☐ App.jsx or routing root (modified — route additions)
34. ☐ CHANGELOG.md — §2.4B-i entry
35. ☐ docs/SY_Hub_Prompt_2_4B_i_Frontend_Build_Pack_v2.md (this file, verbatim)
36. ☐ docs/chat-summaries/chat-NN-closing.md (chat that builds the prompt)
```

### R10.2 — CHANGELOG block

```markdown
## 2.4B-i — Budgets Frontend (Build Pack v2) (2026-MM-DD)

**Shipped:**
- Routes `/projects/:projectId/budgets[/:budgetId]` with TanStack Query v5 + Table v8
- 14 backend endpoints wired via typed hooks; abort signals threaded; patch bodies pre-validated against Zod
- Reorder endpoint #15 [present | added in pre-prompt patch] — bulk atomic write
- Lifecycle controls (Activate / Lock / Unlock / Close / New Version) gated by (status, permission)
- Optimistic edits for description / notes / % complete / drag-reorder; server-confirmed for FTC method / lock-state / line CRUD / cost-code reassignment
- Line drawer explicit-Save with line-level version stamps + 409 conflict toast + close-with-dirty confirm
- Patch body built from dirtyFields only + defensive cost-code filter (no over-sending)
- Sensitive-field schema graceful (.nullable().optional()) — payload accepted whether stripped or full
- Drag-reorder a11y: KeyboardSensor + sortableKeyboardCoordinates + setActivatorNodeRef
- Mobile read-only floor enforced via useIsDesktop hook — every write path gated
- Brand tokens applied: bg-sy-teal text-white for Save/Create/Lock; bg-sy-orange text-white for destructive; hover:brightness-110
- Component tests: 29 functions across 8 areas — render, perm gate, sensitive (incl. stripped-payload), state machine, line CRUD (dirty-fields), items (delete confirm), reorder (pure handler), mobile floor

**Deviations from Build Pack v2:**
- <fill>

**Backlog added:**
- Programme-task linkage UI (gated on T3.x)
- CSV import/export (Future Tasks)
- Activity timeline rendering (gated on T2.5+)
- Bulk apply % complete to a cost-code root (deferred)
- Mobile write paths (gated on a deliberate mobile UX prompt)
```

### R10.3 — Backlog entries to register

- Programme-task linkage UI (gated on T3.x).
- CSV import / export.
- Activity timeline rendering (gated on T2.5+).
- Bulk apply % complete (mark all under cost-code root).
- Mobile write paths (deliberate UX pass needed).
- Saved filters / column-show-hide on BudgetsTable (low priority).
- `useLineItems` hook usage (only relevant if backend grows endpoint #13 use cases).

### R10.4 — Closing summary template

```markdown
# Chat NN — Closing Summary
**Prompt:** 2.4B-i — Budgets Frontend
**Build Pack:** /app/docs/SY_Hub_Prompt_2_4B_i_Frontend_Build_Pack_v2.md (v2 — audit-corrected)
**Date closed:** 2026-MM-DD
**Final test status:** <vitest count passing> + 664 backend (untouched)
**Bundle delta:** +<KB> gzipped

## Audit findings resolution
- 9 CRITICAL (C1–C9): all fixed in v2
- 12 HIGH (H1–H12): all fixed in v2
- 8 MEDIUM (M1–M9): fixed in v2 except <list deferred>
- LOW: addressed where trivial; rest deferred

## Deviations from Build Pack v2
- <list>

## Pushback retained for future audit
- R5.6 — Lock without confirm (default chosen; argument re-runnable)

## Next prompt opener
[fill — most likely "Chat 18 — 2.4B-ii Playwright E2E flows"]
```

---

## Length disposition

v2 lands at **~3,200 lines** vs the chat-16.5 target of 2,000–2,400. The overrun is justified line-by-line:

| Section | v1 (lines) | v2 (lines) | Driver |
|---|---|---|---|
| Front matter | 87 | ~110 | C1/C2 deviations + 15 ACs (was 14) |
| §R0 | 75 | ~105 | additional gates (tailwind classes, vitest config, sonner wrapper, hook signatures) |
| §R1 | 100 | ~145 | Toaster wrapper, brand-token verification, vitest config patch |
| §R2 | 130 | ~125 | useIsDesktop hook (NEW) replaces some shell text |
| §R3 | 580 | ~600 | abort-signal threading, parseOrThrow helper, BudgetDetailSchema export, sensitive nullable |
| §R4 | 380 | ~395 | budgets.read gate, brand-fixed classes |
| §R5 | 360 | ~360 | brand-fixed classes (no growth) |
| §R6 | 320 | ~395 | KeyboardSensor + setActivatorNodeRef + extracted handleDragEnd + Escape key handlers + useIsDesktop gates |
| §R7 | 425 | ~575 | dirtyFields builder, close-with-dirty confirm, real CostCodePicker, item-delete confirm, fields-disabled-during-pending |
| §R8 | 250 | ~425 | full fixtures.js, complete imports, mockMatchMedia helper, 29 tests (was 25), reorder-as-pure-handler test |
| §R9 / R10 | 165 | ~210 | bundle delta, broader file checklist |
| Total | **2,989** | **~3,200** | +211 lines for non-trivial defect fixes |

Compressing to 2,400 would require:
- collapsing fixtures.js (re-introduces C3),
- dropping mobile-floor tests (re-introduces H1 leak),
- inlining all imports (cosmetic; saves ~30 lines but makes the file harder to consume),
- removing the bundle baseline (ignores M4).

None of those compressions are worth the regression. **Decision: ship at ~3,200 lines.** Length tradeoff registered as a pushback item for triage's review.

---

## Pushback items registered (not blocking, on record)

1. **R5.6 — Lock without confirm.** Default chosen; argument re-runnable in the audit cycle. Argument for confirm: locking is destructive of edit-ability; for: locking is reversible by admin Unlock; activating wasn't gated either; over-confirming trains users to click through.
2. **D8 — Reorder bulk endpoint** (STOP #32). Backend existence not verified; resolves in §R0. Build Pack assumes path 1 (request backend-add as pre-prompt).
3. **D11–D14 — Hook signatures (`useApprovedAppraisals`, `useCostCodes`)** assumed. Wrappers needed if real signatures differ; only those wrappers change, consumers stable.
4. **D7 — Brand-token Tailwind variants.** v2 uses base-token-only approach. If `tailwind.config.js` already has `-hover` / `-foreground` variants, single-pass swap can be applied later for visual parity with the rest of the app.
5. **Length overrun** — see "Length disposition" above. Acknowledged.

---

**End of Build Pack v2.**

This Build Pack supersedes v1. v1 is retained in git history for reference and for the audit trail in `audit_report.md`.
