# Chat 20 — Prompt 2.5D / B38 — AI Capture Cost Dashboard

**Status:** Complete (Emergent-side). Awaiting operator-side pytest +
`alembic upgrade head` against PostgreSQL.

**Predecessor:** Chat 19C closed 2026-02-17. Bundle 423.99 kB gz, pytest 790,
Jest 118, alembic head 0025_actuals.

---

## 1. Self-report (§R7 template)

| Item | Result |
|---|---|
| Bundle gate 1 — main delta | **+0.17 kB gz** (423.99 → 424.16) — limit ≤ +3 kB gz ✅ |
| Bundle gate 2 — absolute main | **424.16 kB gz** — hard cap 437.0 kB (12.84 kB headroom) ✅ |
| Lazy chunk created | `ai-capture-costs.*.chunk.js` — **4.43 kB gz** ✅ |
| Recharts pulled into shared lazy chunk | chunk 52 — **113.03 kB gz**, NOT in main ✅ |
| Jest delta | **+33 tests / +8 suites** (118 → 151 tests, 25 → 33 suites) — all passing ✅ |
| pytest delta | **+15 tests** added in `tests/test_ai_capture_stats.py` (operator-side run) ⏳ |
| ESLint | No issues on new files ✅ |
| ruff | No issues on new files ✅ |
| Alembic head | `0026_ai_capture_costs_perm` (operator must run `alembic upgrade head`) ⏳ |
| Existing AI capture pipeline LOC | **0 changes** to extract/promote/discard/retry paths ✅ |
| Existing actuals state machine LOC | **0 changes** ✅ |

### Backend surface change (single endpoint added, per §R6 STOP gate)

`GET /api/v1/ai-capture-jobs/stats?from_date=&to_date=` — gated by
`require_permission("ai_capture.view_costs")`.

### Invariants honoured

- **I1 flat routes** — `/ai-capture/cost` is a top-level sibling, placed
  BEFORE `/ai-capture/:jobId` in `App.js` so the literal segment never
  collides with the param route.
- **I3 fmtGBP / pence ÷ 100** — every monetary render goes through `fmtGBP`
  with `cost_pence / 100`. Backend never emits floats.
- **I8 AppShell NAV requires perm code** — `nav-ai-capture-cost` entry uses
  `requires: "ai_capture.view_costs"`.
- **I10 path alias `@/`** — all imports use `@/components/...`,
  `@/lib/...`, `@/pages/...`, `@/hooks/...`.
- **I11 bundle hard cap 437 kB** — enforced via `React.lazy()` with
  `webpackChunkName: "ai-capture-costs"` magic comment. Recharts is only
  pulled in when the page is navigated to.
- **I12 cross-domain query invalidation** — `aiCaptureKeys.stats` factory
  is placed under `aiCaptureKeys.all`, so any existing invalidation that
  hits `aiCaptureKeys.all` (promote/discard/retry mutations) will refetch
  an open cost dashboard automatically.
- **I13 hooks-above-perm-gate** — `useCaptureCostStats()` is called BEFORE
  the `canViewCaptureCosts(me)` early-return; `enabled: canViewCaptureCosts(me)`
  short-circuits the network call when the user lacks permission.
- **E12 cross-domain test stubbing** — recharts mocked via
  `jest.mock('recharts', () => { const React = require('react'); ... })`
  with `React.createElement` inside the hoisted factory, in every test
  file that renders a chart.

### Deviations applied

- **D6 zero-fill daily series** — `compute_capture_stats` zero-fills missing
  days in the date range so the line chart never has gaps.
- **D7 integer pence everywhere** — no floats over the wire; `avg_cost_pence`
  is `round(total / count)`.
- **D8 no Radix Select for date picker** — radio-style toggle group, no
  F9 sentinel needed for an enclosed 4-value set.
- **D12 individual recharts imports** — `ResponsiveContainer, LineChart, …`
  named imports for tree-shaking.

### PASS-2 audit fixes applied

- **H6** — "All time" preset sends an explicit `2024-01-01` floor rather
  than empty params; backend's missing-params default is last-30-days
  which would silently truncate.
- **H10** — totals card period label uses the friendly preset name
  ("All time", "Last 7 days") rather than computed day count.

---

## 2. Files changed

### New

| File | LOC | Purpose |
|---|---:|---|
| `backend/alembic/versions/0026_ai_capture_costs_perm.py` | 102 | Migration: ENUMs + permission row + role grants + audit |
| `backend/tests/test_ai_capture_stats.py` | 297 | 15 pytest tests (perm + aggregation + validation + catalogue) |
| `frontend/src/lib/schemas/aiCaptureStats.js` | 37 | Zod schema for `/stats` response |
| `frontend/src/pages/AICaptureCosts.jsx` | 75 | Lazy-loaded cost dashboard page |
| `frontend/src/components/ai-capture/DateRangePicker.jsx` | 41 | 7d/30d/90d/All toggle |
| `frontend/src/components/ai-capture/CostTotalsCards.jsx` | 71 | 4-card totals row |
| `frontend/src/components/ai-capture/CostDailyChart.jsx` | 60 | Recharts line chart |
| `frontend/src/components/ai-capture/CostByStatusChart.jsx` | 71 | Recharts bar chart |
| `frontend/src/lib/__tests__/aiCaptureCapability-costs.test.js` | 30 | canViewCaptureCosts (5 tests) |
| `frontend/src/lib/schemas/__tests__/aiCaptureStats-schemas.test.js` | 46 | schema (4 tests) |
| `frontend/src/lib/api/__tests__/aiCapture-stats.test.js` | 54 | api fn (4 tests) |
| `frontend/src/components/ai-capture/__tests__/DateRangePicker.test.jsx` | 25 | picker (3 tests) |
| `frontend/src/components/ai-capture/__tests__/CostTotalsCards.test.jsx` | 60 | totals (7 tests) |
| `frontend/src/components/ai-capture/__tests__/CostDailyChart.test.jsx` | 64 | daily chart (4 tests) |
| `frontend/src/components/ai-capture/__tests__/CostByStatusChart.test.jsx` | 60 | status chart (3 tests) |
| `frontend/src/pages/__tests__/AICaptureCosts.test.jsx` | 106 | page (3 tests) |
| `docs/chat-20-build-pack-v-final.md` | — | Build pack archived |

### Modified

| File | Reason |
|---|---|
| `backend/app/models/rbac.py` | Add `ai_capture` to `RESOURCES` tuple + `view_costs` to `ACTIONS` |
| `backend/app/seed_rbac.py` | Insert `ai_capture.view_costs` permission; add to `finance` role set (super_admin/director inherit via global set) |
| `backend/app/routers/ai_capture.py` | Append `GET /ai-capture-jobs/stats` endpoint |
| `backend/app/services/ai_capture.py` | Append `compute_capture_stats(db, from_date, to_date)` service |
| `frontend/src/lib/api/aiCapture.js` | Export `getCaptureCostStats()` |
| `frontend/src/hooks/aiCapture.js` | `aiCaptureKeys.stats(filters)` factory + `useCaptureCostStats()` hook |
| `frontend/src/lib/aiCaptureCapability.js` | Export `canViewCaptureCosts(me)` |
| `frontend/src/App.js` | `React.lazy(import("@/pages/AICaptureCosts"))` + `/ai-capture/cost` route (placed before `:jobId`) |
| `frontend/src/components/AppShell.jsx` | NAV entry `AI Capture Costs` with `requires: "ai_capture.view_costs"` |

---

## 3. Operator-side verification checklist

Run on Rhys's local machine after `git pull`:

```bash
# 1. Migration
cd backend && alembic upgrade head
# Expect: head = 0026_ai_capture_costs_perm

# 2. Backend tests (target: 790 + 15 = 805)
pytest tests/test_ai_capture_stats.py -v
pytest  # full suite

# 3. Frontend (already verified in Emergent — re-run for sanity)
cd ../frontend && yarn test --watchAll=false   # 151 tests
yarn build                                      # main ≤ 437 kB gz

# 4. Playwright smoke
yarn e2e:smoke
```

Manual UI check:
1. Log in as test-finance@example.test
2. Click "AI Capture Costs" in sidebar — page renders 4 totals cards + 2 charts
3. Click 7d / 90d / All time — chart refreshes, "Total spent" updates
4. Log in as test-pm@example.test — sidebar entry NOT visible; direct
   nav to `/ai-capture/cost` shows "You don't have permission".

---

## 4. STOP gates — none triggered

- No unsolicited scope expansion beyond §R0–§R8 ✅
- Backend surface: 1 migration + 1 endpoint + 1 service function (no
  changes to existing pipeline) ✅
- Bundle gate 1: +0.17 kB ≤ +3 kB ✅
- Bundle gate 2: 424.16 ≤ 437 kB ✅

---

## 5. Backlog state

No new items added in this chat. B43–B46 (from build pack front matter)
remain open. Chat 20 itself closed clean.

---

## 6. Commit message (per §R8 step 1)

```
feat(ai-capture): cost dashboard (B38, Prompt 2.5D)

- Migration 0026: ai_capture.view_costs permission + role grants
  (super_admin, director, finance)
- GET /api/v1/ai-capture-jobs/stats with London-tz date bucketing,
  zero-fill daily series, integer-pence totals
- Lazy-loaded /ai-capture/cost page with 4 totals cards + daily line
  chart + by-status bar chart (recharts in its own split chunk)
- 33 Jest tests added (118 -> 151), 15 pytest tests added
- Bundle: main 423.99 -> 424.16 kB gz (+0.17), well under 437 kB cap
- Zero LOC change to existing AI capture pipeline or actuals state
  machine
```
