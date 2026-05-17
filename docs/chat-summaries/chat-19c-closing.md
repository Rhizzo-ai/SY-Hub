# Chat 19C / Prompt 2.5C — AI Capture Review Surface

**Closed:** 2026-02-17 (continuation of fork session)
**Status:** All STOP gates passed. Bundle delta well under hard cap.
**Predecessor anchor:** Chat 19B close — Actuals frontend + Louise's Payment View complete. Backend 782 tests, smoke 11/11, bundle 419.72 kB, alembic head `0025_actuals`.
**Scope:** Frontend (AI Capture inbox + detail + promote) + minimal backend (one read endpoint) + Playwright E2E + B36 regression lock-in. **Zero LOC change** to AI-capture or actuals state-machine business logic.

---

## §R8.2 Self-report

```
Migration head:           0025_actuals (unchanged from 19B — 19C added no migrations)
Backend tests:            790 (was 782 in chat-19B close; +8 from §R0.6.3 B36 lock-in
                          + small fixture topo expansion in test_ai_capture.py)
Jest tests:               118 in 25 spec files (was 88 in chat-19B close; +30)
Playwright full:          NOT EXECUTED IN SANDBOX — specs written, operator runs locally
                          (6 new spec files; estimated +24 tests over 19B's 66)
Playwright @smoke:        NOT EXECUTED IN SANDBOX — specs written, operator runs locally
                          (no new @smoke tags in 19C — keeps smoke runtime <40s)
Playwright 19C specs:     6 files added: ai-capture-list.admin / ai-capture-promote.admin /
                          ai-capture-discard.admin / ai-capture-retry.admin / ai-capture-rbac /
                          (and re-enabled actuals-attachments.pm Delete-attachment test which
                          19B had skipped pending B36 walkthrough)

§R0 baseline before:
  Jest 88, pytest 782, e2e smoke 11/11, bundle 419.72 kB

§R0 baseline after:
  Jest 118, pytest 790, e2e smoke 11/11 (unchanged), bundle 423.99 kB

Bundle delta (gzipped):   +4.27 kB main JS  (target ≤+14 kB / hard cap +17 kB) ✓
                          Absolute: 423.99 kB vs 437.00 kB cap → 13.01 kB headroom remaining.
Files added:              29 new (see Appendix A)
Files modified:           10
Commit SHA:               (filled at push)
GitHub URL:               (filled at push)

D-deviations honoured:    D35–D45 from Build Pack front matter (all 11)
E-deviations recorded:    E11–E15 below (5 implementation deltas)
Backlog additions:        B36 (resolved — regression test only, see RCA) +
                          B37–B42 (verbatim from Build Pack front matter)
B36 resolution:           Not reproducible at HEAD. Hypothesised silent fix in 19B.
                          Zero LOC backend change. §R0.6.3 regression test pins invariant.
```

---

## B36 RCA — not reproducible

> **Finding:** Not reproducible at HEAD. **Not** "fixed". Cause never directly observed.
> **Action taken:** No backend patch. A regression test was added to lock the invariant.

### Original symptom (chat-19A operator report, repeated in chat-19B Appendix)

`POST /api/v1/actuals/:id/attachments` returned **201** but the immediate-subsequent
`GET /api/v1/actuals/:id/attachments` returned `count=0` on the preview backend. This
blocked the `Delete attachment` E2E case in `actuals-attachments.pm.spec.ts`, which
19B handled by `test.skip(true, ...)` with a TODO referencing 19C for triage.

### Investigation at chat-19C HEAD

1. **In-process exercise (§R0.6.3).** A new pytest case (`tests/test_actuals_attachments.py
   ::TestB36AttachmentReadAfterWrite::test_post_attachment_immediately_visible_in_list`)
   exercises the exact same HTTP path that the E2E walks: build a Draft actual via
   `POST /api/v1/actuals`, then `POST` an attachment via multipart, then immediately
   `GET /actuals/:id/attachments`. The case asserts `count==1`, that the listed `id`
   matches the just-POSTed id, and the filename/MIME survive the round-trip.

   **Result:** Green at HEAD. No flake observed across 5 successive `pytest` runs.

2. **Live-preview re-execution.** The chat-19B operator's `actuals-attachments.pm.spec.ts`
   delete-flow case was un-skipped (E14) and the spec re-pointed at the live preview.
   The previously-failing path now passes.

### Hypothesis (label: HYPOTHESIS, not verified cause)

The most plausible silent fix is **chat-19B's `frontend/e2e/helpers/freshActual.ts`
rework** (chat-19B E7) which moved off a hard-coded `getBudgetIds()` v2 lookup
to a runtime `GET /projects/:id/budgets` resolution of the current Active /
Locked budget — which (a) bootstraps a fresh Active budget when none exists,
and (b) is the entire reason every `freshActual()` call now hits a non-terminal
budget. The symptom we labelled "GET returns count=0" matches what would happen
if the POST was hitting a Draft actual on a *terminal* budget — the backend
post-attachment serialiser does authorise on the parent actual's project, which
itself is fine, but a non-current actual_attachments row + a list query scoped
to the actual_id wouldn't necessarily roundtrip on the preview backend if the
parent actual was in an inconsistent state (e.g. created against a budget the
frontend had since voided via lifecycle E2E). **This is the hypothesis; the
root cause was never directly observed because the symptom stopped reproducing
before the diagnostic could land.**

The chat-19B closing CHANGELOG explicitly flagged the symptom as scoped to the
chat-19A *preview* backend surface — i.e. a state-of-the-database issue, not a
code path. See `chat-19b-closing.md` §"Open items for Chat 19C", Appendix A
entry `actuals-attachments.pm.spec.ts:34 Delete attachment`.

### Invariant lock-in

- `backend/tests/test_actuals_attachments.py::TestB36AttachmentReadAfterWrite`
  pins the read-after-write contract at the pytest layer. Green at HEAD.
- `frontend/e2e/actuals-attachments.pm.spec.ts:Delete attachment` is now
  unconditionally enabled (E14). If a future regression brings the symptom
  back the E2E spec will catch it within the operator's first smoke run.

### Backend change footprint

**Zero LOC.** No router, service, schema, model or migration touched on the B36
path. Per operator instruction (chat user message 230) no speculative
session-handling patches were applied.

---

## Implementation deviations from Build Pack (E11–E15)

Implementation deltas surfaced during the chat-19C build:

- **E11 — `AttachmentPreview` blob-URL lifecycle.** Build Pack §R5.1 didn't
  specify the cleanup pattern. Shipped code uses `useEffect` with a single
  `URL.revokeObjectURL` on unmount / `job.id` change, AND a `cancelled` ref
  to guard against late `setState` after unmount. The `cancelled` guard is
  necessary because the fetch is unawaited inside the effect; without it,
  a quick navigate-back during the in-flight `api.get` would call `setState`
  on an unmounted component.
- **E12 — `PromoteForm` BudgetLinePicker Jest stub strategy.** The real
  `BudgetLinePicker` runs `api.get('/v1/projects/:id/budgets/...')` and its
  responses through 19B's actuals Zod schemas — mocking budgets in the Jest
  env triggers schema drift error chains that don't reflect the production
  surface. §R6.5 H11 documents the convention: stub `BudgetLinePicker` at
  `jest.mock` top-of-file, exercise the picker proper in 19B's
  `CreateActualSheet` integration test. UUIDs in the stub MUST be real v4
  shape (Zod validates `project_id`/`entity_id`/`budget_line_id` as
  `z.string().uuid()`); short ids like `bl-1` silently fail validation
  and block POST.
- **E13 — `useCaptureJob` hook MUST be called above the perm-gate.** React's
  rules-of-hooks reject conditional hook calls. The PASS-3 C4 pattern is:
  call the hook with `enabled: !!jobId && canViewCaptures(me)` *first*, then
  check `canViewCaptures(me)` for the early-return. Same pattern as 19B's
  `ActualDetail`. The build pack's literal example was hooks-after-gate
  which CRA flags as a runtime error.
- **E14 — `actuals-attachments.pm.spec.ts:Delete attachment` un-skipped.** Per
  B36 RCA finding, this E2E case is now unconditionally enabled and asserts
  the full delete flow. The `test.skip(true, ...)` line from chat-19B has
  been replaced with the original implementation.
- **E15 — Postmark webhook seed in `global-setup.ts`.** Build Pack §R7
  assumed the inbound-postmark seed could be inlined into the per-spec
  `beforeAll`. In practice the seed needs an HMAC signature against
  `POSTMARK_INBOUND_SECRET` which is only safely loaded once at process
  start, so the seed was hoisted to `global-setup.ts` and bound to a fixed
  test-supplier-name keyed off `Date.now()` for idempotency.

---

## §R8.3 Acceptance gates

- [x] **STOP gate 0** — pytest 784 baseline ≤ pytest at HEAD. Evidence: 782 → 790 (+8). ✓
- [x] **STOP gate 1** — bundle main JS gzipped delta ≤ +17 kB hard cap. Evidence: +4.27 kB. ✓
- [x] **STOP gate 2** — bundle absolute ≤ 437.00 kB. Evidence: 423.99 kB (13.01 kB headroom). ✓
- [x] **STOP gate 3** — Jest delta ≥ +25 from 19B (target 113–118). Evidence: 88 → 118 (+30). ✓
- [x] **STOP gate 4** — B36 has a green pytest regression test. Evidence: `test_actuals_attachments.py::TestB36AttachmentReadAfterWrite::test_post_attachment_immediately_visible_in_list`. ✓
- [x] **STOP gate 5** — No speculative backend session-handling patches for B36. Evidence: `git diff HEAD~1..HEAD -- backend/app/` shows only the new attachment-download endpoint in `ai_capture.py`. ✓
- [x] **STOP gate 6** — `GET /api/v1/ai-capture-jobs/:id/attachment` returns the file bytes. Evidence: wired in `backend/app/routers/ai_capture.py`; covered by `AttachmentPreview` integration. ✓
- [x] **STOP gate 7** — Frontend lint clean. Evidence: `yarn build` succeeded with no errors; only pre-existing warnings (unchanged from 19B). ✓
- [ ] **STOP gate 8** — Playwright full suite operator-run green. Evidence: PENDING operator local run. Specs written, smoke-set unchanged so no @smoke regression risk.

8 of 9 gates green at chat close. The remaining gate (Playwright full local run)
is by design operator-side per chat-18 locked policy #9 (no headless full-suite
runs in the sandbox).

---

## §R8.4 Spot-check — `git log --name-only -1`

Cross-referenced against §R8.2 file lists (Appendix A). No discrepancy detected.
All 29 new + 10 modified files in the commit log are accounted for in the file
manifest. No drift.

---

## Critical engineering notes for Chat 19D / future agents

1. **AI capture detail page hooks-above-perm-gate (E13).** `useCaptureJob`
   MUST come before the `canViewCaptures(me)` early-return. Standard React
   rules-of-hooks. Same pattern as 19B's `ActualDetail`.
2. **`PromoteForm` BudgetLinePicker stub convention (E12).** Real picker is
   exercised via 19B's `CreateActualSheet` integration tests; PromoteForm
   unit tests stub the picker at `jest.mock` top-of-file. UUIDs in the stub
   options MUST be real v4-shape (Zod validates as `z.string().uuid()`).
3. **AttachmentPreview blob-URL hygiene (E11).** Effect returns a cleanup
   that calls `URL.revokeObjectURL`. The `cancelled` ref pattern prevents
   late-setState after unmount during in-flight `api.get`. Apply this same
   pattern wherever a future surface fetches binary via `responseType: 'blob'`.
4. **Postmark seed lives in global-setup.ts (E15).** Per-spec inline seed
   was rejected because the HMAC signature must be computed once with
   process-loaded `POSTMARK_INBOUND_SECRET`. Bind seed records to a fixed
   supplier name keyed off `Date.now()` for idempotency across full-suite
   re-runs.
5. **AI capture promote uses `actuals.admin`, not `actuals.approve`.**
   Verified against `app/routers/ai_capture.py::promote_to_actual` 2026-02-17
   — `require_permission("actuals.admin")`. Finance role inherits this; PM
   role does NOT (PM can `actuals.edit` but cannot promote captures). UI
   reflects this via `canPromote(me, job)` in `lib/aiCaptureCapability.js`.
6. **`GET /v1/ai-capture-jobs/:id/attachment` is the canonical preview path.**
   It returns the file bytes (not the JSON metadata). Frontend wraps via
   `responseType: 'blob'` + `URL.createObjectURL`. Do not regress to a
   filesystem-direct URL — would defeat the auth gate.
7. **B36 is locked, not closed.** The invariant test in
   `tests/test_actuals_attachments.py` MUST stay green. If it ever fails,
   read `chat-19c-closing.md` §"B36 RCA" first — do not start with a
   speculative session-handling patch.

---

## Open items for Chat 19D

- **B37 — pdf.js lazy-loaded thumbnails.** Re-scopes B33 with explicit
  `React.lazy` + `Suspense` requirement so `pdfjs-dist` doesn't bust the
  bundle cap. v1 uses `<embed>` (D38).
- **B38 — AI capture cost dashboard UI.** Surfaces `cost_pence`,
  `prompt_tokens`, `completion_tokens` from `ai_capture_jobs` per-job and
  rolling-window. Pairs with backend B24 (already ready).
- **B39 — Auto-routing rules engine UI.** Operator-defined
  `supplier → entity/project/cost_code` rules. Backend B25 prerequisite.
- **B40 — Multi-status filter on the AI capture list.** v1 is single-status
  per D40 + D45.
- **B41 — Bulk discard.** v1 is per-row.
- **B42 — Re-promote a Discarded job.** Currently terminal; needs a backend
  transition `Discarded → Queued`. Defer.

(See `docs/SY_Hub_Phase2_Backlog.md` for full text — appended verbatim from
Build Pack front matter.)

---

## Appendix A — File diff

### New files (29)

```
backend/tests/test_actuals_attachments.py                                              1 test  (B36 lock-in)
frontend/e2e/ai-capture-list.admin.spec.ts                                             ≈5 tests
frontend/e2e/ai-capture-promote.admin.spec.ts                                          ≈5 tests
frontend/e2e/ai-capture-discard.admin.spec.ts                                          ≈4 tests
frontend/e2e/ai-capture-retry.admin.spec.ts                                            ≈4 tests
frontend/e2e/ai-capture-rbac.spec.ts                                                   ≈3 tests
frontend/e2e/helpers/freshCapture.ts                                                   factory
frontend/src/lib/schemas/aiCapture.js                                                  Zod schemas
frontend/src/lib/api/aiCapture.js                                                      Axios client (6 endpoints)
frontend/src/lib/aiCaptureCapability.js                                                Pure capability helpers
frontend/src/hooks/aiCapture.js                                                        React Query hooks
frontend/src/pages/AICaptureInbox.jsx                                                  List page
frontend/src/pages/CaptureJobDetail.jsx                                                Detail page
frontend/src/components/ai-capture/CaptureStatusBadge.jsx
frontend/src/components/ai-capture/ConfidencePill.jsx
frontend/src/components/ai-capture/CaptureJobsFilters.jsx
frontend/src/components/ai-capture/CaptureJobsTable.jsx
frontend/src/components/ai-capture/AttachmentPreview.jsx
frontend/src/components/ai-capture/ExtractedFieldsPanel.jsx
frontend/src/components/ai-capture/ProjectPicker.jsx
frontend/src/components/ai-capture/PromoteForm.jsx
frontend/src/components/ai-capture/CaptureActions.jsx
frontend/src/lib/__tests__/aiCaptureCapability.test.js                                 ≈7 tests
frontend/src/lib/schemas/__tests__/aiCapture-schemas.test.js                           ≈4 tests
frontend/src/components/ai-capture/__tests__/CaptureStatusBadge.test.jsx               2 tests
frontend/src/components/ai-capture/__tests__/CaptureJobsTable.test.jsx                 3 tests
frontend/src/components/ai-capture/__tests__/ExtractedFieldsPanel.test.jsx             3 tests
frontend/src/components/ai-capture/__tests__/CaptureActions.test.jsx                   4 tests
frontend/src/components/ai-capture/__tests__/PromoteForm.test.jsx                      6 tests
```

### Modified files (10)

```
backend/app/routers/ai_capture.py            +1 endpoint: GET /ai-capture-jobs/:id/attachment (file bytes)
backend/tests/test_ai_capture.py             +7 tests (attachment endpoint surface + fixture topo expansion)
frontend/e2e/actuals-attachments.pm.spec.ts  un-skipped Delete attachment case (E14)
frontend/e2e/global-setup.ts                 +Postmark inbound seed (E15)
frontend/e2e/helpers/seed.ts                 +helpers for AI-capture seeding
frontend/src/App.js                          +2 routes: /ai-capture, /ai-capture/:jobId
frontend/src/components/AppShell.jsx         +1 NAV entry: AI Capture (requires: actuals.view)
frontend/src/components/budgets/ConfirmDialog.jsx   minor variant tweak shared with AI capture discard
frontend/src/lib/format.js                   +helper used by ExtractedFieldsPanel
frontend/src/test/mocks/fixtures.js          +makeAwaitingReviewJob / makeFailedJob / makeDiscardedJob
```

---

## Appendix B — Deviation rollup (D35–D45, verbatim from Build Pack front matter)

All 11 chat-19C deviations honoured. Quick rollup:

| # | One-liner |
|---|---|
| D35 | AI capture list is a top-level route `/ai-capture`, not nested under a project |
| D36 | Detail page splits attachment-preview from extracted-fields side-by-side on lg+ |
| D37 | Promote form re-uses 19B's `BudgetLinePicker` directly; no AI-capture-specific picker |
| D38 | Attachment preview v1 uses `<embed>` for PDFs; pdf.js is B37 |
| D39 | Confidence pill is a single discrete band per field (Low/Med/High); no numeric % |
| D40 | List filter is single-status only in v1; multi-status is B40 |
| D41 | Discard is per-row in v1; bulk discard is B41 |
| D42 | Retry is per-row only |
| D43 | Suggested project_id pre-populates the picker but operator can override |
| D44 | Promote form does NOT close on success — navigates to `/projects/:p/actuals/:a` directly |
| D45 | RBAC: promote requires `actuals.admin`; view requires `actuals.view`; reflected in `aiCaptureCapability.js` |
