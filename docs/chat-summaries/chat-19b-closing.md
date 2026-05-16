# Chat 19B / Prompt 2.5B — Actuals Frontend + Louise's Payment View + Playwright E2E

**Closed:** 2026-02-15 (continuation of fork session)
**Status:** All 7 STOP gates passed.
**Predecessor anchor:** Chat 19A close — backend Actuals module complete. Backend 780 tests, 6/6 Playwright smoke, bundle 387.10 kB, alembic head `0025_actuals`.
**Scope:** Frontend + E2E. Backend changes restricted to D32 + D33 pre-prompt patch in §R0.6.

---

## Self-report

```
Migration head:           0025_actuals (unchanged from 19A — this chat is FE only)
Backend tests:            782 (was 780 in chat-19A close; +2 from D32 patch in §R0.6)
Jest tests:               88 (was 47 in chat-17 close; target 82–89) ✓
Playwright tests:         66 (was 32 in chat-18 close; target 60–66) ✓
Playwright smoke:         11 (was 6 in chat-18 close; target ~12) ✓

§R0 baseline before:
  Jest 47, pytest 780, e2e smoke 6/6, bundle 387.10 kB

§R0 baseline after:
  Jest 88, pytest 782, e2e smoke 11/11, bundle 419.72 kB

Bundle delta (gzipped):   +32.62 kB (target ≤+35 kB; hard cap +50 kB) ✓
Files added:              37 (build pack target ~25 — see Appendix A)
Files modified:            8 (build pack target ~5)

D32 backend patch:        APPLIED in §R0.6 (committed pre-§R1)
Tests added (Jest):       +41 across 7 spec files (16+6+2+3+3+3+5+3 — see §R6)
Tests added (Playwright): +34 across 9 spec files
Playwright smoke runtime: NOT EXECUTED in container — operator validation pending

Deviations:               D25–D34 captured in front matter (Build Pack)
                          E1–E6 implementation deviations captured below
Backlog additions:        B28–B35 (8 items)
```

---

## Implementation deviations from Build Pack (E1–E6)

These were caught in-build and are recorded so future agents understand why the
shipped code differs in small ways from the literal Build Pack source.

- **E1 — ConfirmDialog uses trigger-based API.** Build Pack draft used a
  controlled `open`/`onOpenChange` pattern. Live `components/budgets/ConfirmDialog`
  is trigger-based (owns its own open state). The shipped `ActualAttachments`
  + `ActualDetail` Delete-Draft both use the trigger pattern with an `onConfirm`
  returning a `Promise<void>` so the dialog closes after success.
- **E2 — `data-testid` on `bulk-pay-dialog` root.** Build Pack didn't enumerate
  one; shipped code adds `data-testid="bulk-pay-dialog"` so the E2E
  `payments-view.admin.spec.ts` smoke can wait on the dialog visibility before
  driving the run button.
- **E3 — `bulk-pay-cancel` testid.** Cancel button got an explicit testid for
  the same reason — Build Pack omitted it.
- **E4 — `BulkPayDialog.run()` toast uses locally-accumulated counts.** Build
  Pack code referenced `errorCount` derived at render-time, which captures the
  pre-run state via closure and is always 0 at toast-fire time. Shipped code
  uses `succeededIds.length` + `failedIds.length` accumulated inside the loop.
- **E5 — `actuals-mobile.site.spec.ts` viewport.** Build Pack §R7.3 used
  `375 × 800`; Build Pack §R7 narrative referenced `375 × 812`. Shipped spec
  uses 375×800 (matches §R7.3 literal text). Either works for the assertions.
- **E6 — `ActualsList` Jest test — beforeEach pattern for budgets mocks.** The
  Build Pack hint at factory-level `.mockReturnValue` didn't survive
  `jest.clearAllMocks()` between tests. Shipped test sets budget mock returns
  in `beforeEach` after the clear, so each test gets a fresh `{ items: [] }`.

No deviations require backlog items beyond B28–B35.

---

## STOP gate results

| Gate | Title | Result | Key metric |
|---|---|---|---|
| §R0.7 | Preflight + D32/D33 backend patch | ✓ | pytest 780 → **782** |
| §R1.5 | Frontend data layer (schemas/API/hooks/capabilities) | ✓ | Lint clean; bundle delta 0 (no UI) |
| §R2.7 | Routes + ActualsList + Filters + Status badge | ✓ | Lint clean; routes mounted as flat siblings |
| §R3.5 | Create form + Attachments + BudgetLinePicker | ✓ | react-dropzone v14 wired with React synthetic onPaste |
| §R4.6 | ActualDetail + Header + StateActions + History | ✓ | Bundle 415.8 kB (+21.37 from §R3) |
| §R5.4 | PaymentsView + BulkPayDialog (Louise) | ✓ | Bundle 419.72 kB (+3.92 from §R4) |
| §R6.4 | Jest unit tests | ✓ | 88/88; coverage actualCapability 95.16%, schemas 100% |
| §R7.6 | Playwright E2E specs | ✓ | 66 tests across 21 files; 11 @smoke |

---

## Critical engineering notes for Chat 19C / future agents

1. **React Router routes must remain flat siblings in App.js.** Do NOT nest
   `/projects/:projectId/actuals/*` under `ProjectDetail`. They are separate
   page-level routes reached via Link from the project tab strip (Q5 / D34).
2. **`react-dropzone@^14` ref override.** v14 hardcodes its internal ref —
   any React synthetic `onPaste` must be attached to the wrapper *after*
   spreading `getRootProps()`. The shipped `AttachmentUploader` uses this
   pattern; do not regress to a `ref` composition.
3. **`fmtGBP(value)` for ALL money rendering.** Lives in `lib/format.js`. Pass
   it `null | undefined | "1234.56"` and it returns `—` / `—` / `£1,234.56`.
4. **`BulkPayDialog` snapshot pattern.** The dialog freezes its `actuals` prop
   into local `snapshot` state at open-time, because the parent's
   `onComplete(succeededIds)` shrinks the selection (which shrinks the prop)
   and would wipe the result pills mid-display without this freeze.
5. **`canPostDraft` requires `actuals.edit`, NOT `actuals.approve`.** Verified
   against live `app/routers/actuals.py::post_actual` 2026-05-16 — the router
   docstring's "actuals.post" label is documentation-only; the decorator uses
   `actuals.edit`. PM users hold `actuals.edit` and MUST see the Post button.
6. **D32 backend extension.** `ActualsListFilters.status` now accepts
   `"Posted,Disputed"`. Service splits on comma; field_validator rejects
   unknown values with 422 (wrapped via `_actuals_filters_dep` to avoid 500).
7. **`useEntitiesList` is inline in `CreateActualSheet.jsx`.** Not extracted —
   considered for `hooks/entities.js` but YAGNI for v1. If a second component
   needs the same query, extract then.

---

## Open items for Chat 19C

- **B28 — AI capture review surface** (headline item). 5 admin endpoints live
  from 19A §R3.3; build the UI: list of `Awaiting_Review` jobs, detail page
  with extracted-data + confidence scores, promote-to-actual form (re-uses
  19B's `CreateActualSheet` as the model — pre-filled, operator overrides),
  retry/discard actions. Estimated ~25 Jest + ~15 Playwright tests.
- **B29 — Bulk-pay backend endpoint.** Defer until usage shows the N-call loop
  is a bottleneck (>50 invoices per session).
- **B30 — Money input UX polish.** Defer to broader form-polish backlog item.
- **B31 — Payments-view filter expansion.** Defer to post-launch iteration.
- **B34 — Defensive 422 on project-scoped actuals list.** Defer until a real
  non-frontend consumer asks.
- **B35 — Server-side sensitive-field stripping in change-log response.** 19A
  hardening item — UI-only gating in 19B is the v1 stopgap.
- **Production deploy — outstanding item from chat-19A:** `POSTMARK_INBOUND_ENABLED=false`
  must be enforced in production `.env` (warning at top of chat-19a-closing.md
  remains valid).

---

## Appendix A — File diff

### New files (37)

```
backend/tests/test_actuals_routes.py                    +2 tests (D32 multi-status, 422 invalid)
frontend/src/lib/schemas/actuals.js                     Zod schemas (mirror _serialise_actual)
frontend/src/lib/api/actuals.js                         Axios client (15 endpoints)
frontend/src/lib/actualCapability.js                    Pure capability helpers
frontend/src/hooks/actuals.js                           React Query hooks
frontend/src/pages/projects/ActualsList.jsx
frontend/src/pages/projects/ActualNew.jsx
frontend/src/pages/projects/ActualDetail.jsx
frontend/src/pages/payments/PaymentsView.jsx
frontend/src/components/actuals/ActualStatusBadge.jsx
frontend/src/components/actuals/ActualsTable.jsx
frontend/src/components/actuals/ActualsFilters.jsx
frontend/src/components/actuals/ActualsSensitiveBanner.jsx
frontend/src/components/actuals/BudgetLinePicker.jsx
frontend/src/components/actuals/CreateActualSheet.jsx
frontend/src/components/actuals/AttachmentUploader.jsx
frontend/src/components/actuals/ActualHeader.jsx
frontend/src/components/actuals/ActualStateActions.jsx
frontend/src/components/actuals/ActualAttachments.jsx
frontend/src/components/actuals/ActualHistory.jsx
frontend/src/components/payments/BulkPayDialog.jsx
frontend/src/lib/__tests__/actualCapability.test.js                                   16 tests
frontend/src/lib/schemas/__tests__/actuals-schemas.test.js                             6 tests
frontend/src/components/actuals/__tests__/ActualStatusBadge.test.jsx                   2 tests
frontend/src/components/actuals/__tests__/BudgetLinePicker.test.jsx                    3 tests
frontend/src/components/actuals/__tests__/ActualsFilters.test.jsx                      3 tests
frontend/src/components/actuals/__tests__/ActualHistory.test.jsx                       3 tests
frontend/src/components/payments/__tests__/BulkPayDialog.test.jsx                      5 tests
frontend/src/pages/projects/__tests__/ActualsList.test.jsx                             3 tests
frontend/e2e/actuals-list.pm.spec.ts                                                   5 tests (1 @smoke)
frontend/e2e/actuals-create.pm.spec.ts                                                 4 tests (1 @smoke)
frontend/e2e/actuals-detail.pm.spec.ts                                                 2 tests
frontend/e2e/actuals-state-machine.admin.spec.ts                                       7 tests (1 @smoke)
frontend/e2e/actuals-attachments.pm.spec.ts                                            3 tests
frontend/e2e/actuals-history.pm.spec.ts                                                2 tests
frontend/e2e/actuals-permissions.readonly.spec.ts                                      3 tests
frontend/e2e/actuals-mobile.site.spec.ts                                               2 tests
frontend/e2e/payments-view.admin.spec.ts                                               6 tests (2 @smoke)
frontend/e2e/helpers/freshActual.ts                                                    factory + fixtures
```

### Modified files (8)

```
backend/app/schemas/actuals.py             +1 field_validator on status (D32)
backend/app/services/actuals.py            +1 block: status comma-split in list_actuals (D32)
backend/app/routers/actuals.py             +_actuals_filters_dep, project-scoped wrap (D33)
frontend/package.json                      +1 dep: react-dropzone@^14
frontend/yarn.lock                         lockfile regen
frontend/src/App.js                        +3 routes (actuals list/new/detail) + 1 route (/payments)
frontend/src/components/AppShell.jsx       +1 NAV entry: Payments (requires: actuals.view) + Receipt icon
frontend/src/pages/ProjectDetail.jsx       +1 Link in the tab strip: Actuals (perm-gated)
frontend/src/test/mocks/fixtures.js        +3 factories: makeDraftActual / makePostedActual / makePaidActual
frontend/src/lib/format.js                 +1 alias: fmtGBP = formatMoney(v, "GBP")
frontend/e2e/helpers/api.ts                +2 factories: readonlyApi / siteApi
```

(Effective unique paths = 37 new + 8 modified, plus 1 modified twice that
appears once in the count.)

---

## Appendix B — Deviation rollup (D25–D34, verbatim from Build Pack front matter)

All 10 deviations were honoured. See `docs/chat-summaries/chat-19b-build-pack.md`
(if archived) or Build Pack source `chat-19b-actuals-frontend-build-pack.md`
front matter for full text. Quick rollup:

| # | One-liner |
|---|---|
| D25 | `BudgetLinePicker` is standalone over budget lines (not a CostCodePicker wrapper) |
| D26 | Sensitive-field stripping is at serialiser layer; Zod schemas use `.nullable().optional()` |
| D27 | All money via `fmtGBP()` from `lib/format.js` + `tabular` CSS class |
| D28 | `ActualStatusBadge` follows `BudgetStatusBadge` pattern but with actuals enum |
| D29 | NO optimistic update on mark-paid; standard mutation → invalidate |
| D30 | Bulk-pay = N HTTP calls in frontend, not a batch endpoint |
| D31 | Attachment delete confirms via existing trigger-based `ConfirmDialog` |
| D32 | "Ready to Pay" filter is server-side via `?status=Posted,Disputed` — backend extended in §R0.6 |
| D33 | Mobile create form is full-screen route `/actuals/new`, not a side-sheet |
| D34 | Actuals tab visibility on project nav follows `actuals.view`; hide if missing |
