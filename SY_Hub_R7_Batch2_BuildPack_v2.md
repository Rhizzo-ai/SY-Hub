# SY-Hub — R7 Batch 2 (Emergent build pack) — v2

> **v2 audit changelog (triage, Chat 28)** — re-read end-to-end against `main`.
> Five findings fixed; four operator decisions locked. Grounded-facts section
> re-verified accurate (306-line component, 7 deferred testids, stale "five"
> comment at test line 46, lowercase `edit_tier`, reject-dialog reason-required
> at jsx line ~291, TanStack Query/Table installed, e2e scripts present).
>
> - **[HIGH] R7.6 optimistic layer** — v1 said "extend Batch 1's already-wired
>   send-back optimistic pattern." NO such pattern exists on `main`:
>   `usePoTransition` (hooks/purchaseOrders.js) is plain `onSuccess`-invalidation,
>   and both POActionButtons.jsx line 48 and the hook comment (lines 149-152)
>   say optimistic is deferred *to* Batch 2. Rewritten to "build fresh."
> - **[HIGH] AC5 committed-cache refresh (LOCKED: option b)** — on a
>   commitment-changing verb, refresh the Budgets grid's committed column, not
>   just the PO-by-line cache. The PO transition hook holds only `poId` (no
>   `budgetId`/`lineId`), so use coarse `['budgets']` namespace invalidation —
>   precedent already exists at budgets.js line 245. Spelled out in R7.6 + AC5.
> - **[MED] R7.5 dashboard (LOCKED: per-project now)** — named the data source
>   (`useProjectPOs(projectId, { params })`); all-projects global view deferred
>   to backlog (no global PO-list hook exists; needs new query + likely backend
>   endpoint → out of a frontend-only batch).
> - **[MED] regression guard** — once `DEFERRED_TESTIDS` empties, the existing
>   loop-over-array guard passes trivially (loops zero times). Instruction added
>   to REPLACE it with positive render assertions. AC1 "near-empty" → "empty."
> - **[MED] edit_tier gating (LOCKED)** — Edit gate = internal user + project
>   access + edit permission. Exact `edit_tier` string values + which value gates
>   draft-edit vs issued-edit handed to Claude Code to read off the backend
>   contract (pack does not invent them).
>
> New backlog items added at §CARRIED FORWARD: all-projects approvals dashboard;
> delivery/collection acceptance-note feature.

**Scope:** re-enable the PO action buttons Batch 1 deferred, now that the backend
endpoints exist. Frontend-only. Builds R7.4 (receipt form), R7.5 (per-project
approvals dashboard), R7.6 (confirm-dialog + Void wiring + optimistic layer), and
the header-only Edit + Delete forms. Each re-enabled button trims its testid from
`DEFERRED_TESTIDS` **in the same commit it gets wired**.

**Predecessor state:** `main` HEAD post-P1 (`412fe5c`). Backend PO endpoints
verified live this session: `PATCH /purchase-orders/{id}` (header-only),
`DELETE /purchase-orders/{id}` (422 on non-draft — draft-only delete enforced
server-side), `void`, `receipts`. Frontend 387 Jest green. Playwright `testDir:
./e2e`, persona-suffixed specs (`*.pm.spec.ts` etc.), `@smoke`-tagged for
`yarn e2e:smoke`.

**Edit-form scope: OPTION A (header-only).** `POPatch` is header-only; line
mutation is a SEPARATE future backend mini-pack. Batch 2 Edit form edits header
fields only. Do NOT build line-item editing.

**Gate model:** build R7.4–R7.6 + Edit/Delete, ONE STOP. No auto-advance.

---

## GROUNDED FACTS (verified on `main` this session)

### DEFERRED_TESTIDS — exact current list (7 entries)
`frontend/src/components/po/__tests__/POActionButtons.test.jsx` (the guard
comment at line 46 says "five" but the list at lines 48-56 has SEVEN — the
comment is stale, the list is authoritative):
```
po-actions-edit-btn
po-actions-delete-btn
po-actions-edit-issued-btn
po-actions-receipt-btn
po-actions-receipt-partial-btn
po-actions-void-btn
po-actions-void-issued-btn
```
The regression guard (test describe block ~line 262) loops `DEFERRED_TESTIDS`
and asserts NONE render on ANY status×persona combo. As each is wired, REMOVE it
from `DEFERRED_TESTIDS` in the SAME commit AND add its positive render assertion
to the matrix test. **When the array is fully emptied, the loop guard becomes
vacuous (zero iterations = trivially green) — DELETE the empty-loop guard block
and rely on the per-button positive render assertions instead (see AC1).**

### Current matrix — `POActionButtons.jsx` (306 lines)
Renders today: `submit-btn` (draft), `approve-btn`/`approve-self-disabled`/
`reject-btn` (pending_approval), `issue-btn`/`send-back-btn` (approved),
`close-issued-btn`/`close-partial-btn`/`close-btn` (issued/partial/receipted).
Status flags already defined: `isDraft`, `isPending`, `isApproved`, `isIssued`,
`isPartial`, `isReceipted` (lines 116-121). Send-back + reject already use a
Dialog pattern (`po-send-back-dialog`, `po-reject-dialog`); the reject dialog's
confirm button is `disabled={!rejectReasonTrimmed || reject.isPending}` (jsx
~line 291) — this is the reason-required template R7.6's Void dialog must copy.
`edit_tier` (lowercase string from backend) gates EDITING ONLY; workflow buttons
are status×perm gated independent of edit_tier.

### Transition + cache hooks — `frontend/src/hooks/purchaseOrders.js`
- `usePoTransition(poId, verb)` — plain `useMutation` with
  `onSuccess: () => invalidate poKeys.detail(poId) + poKeys.all`.
  **No optimistic layer, no budget-line/budgets invalidation today.** The hook
  comment (lines 149-152) states budget-line cache invalidation for
  commitment-changing verbs is explicitly Batch 2 work.
- PO list hooks: `useProjectPOs(projectId, { params })` (project-scoped, passes
  `params` through to `poApi.listProjectPOs`); `useBudgetLinePOs(lineId)`,
  `useBudgetPOs(budgetId)`. **There is NO global / all-projects PO-list hook.**
- `usePOApprovals(poId)` and `POApprovalPanel` (Batch 1, R7.3) exist.
- `useCreateReceipt(poId)` exists; invalidates `poKeys.detail` + `poKeys.receipts`.

### Budgets cache — `frontend/src/hooks/budgets.js`
- `budgetsKeys.detail(budgetId)` drives the budget detail/grid (the committed
  column lives here). Coarse precedent: budgets.js line 245 already does
  `qc.invalidateQueries({ queryKey: ['budgets'] })`.

### Backend contracts (header-only Edit; draft-only Delete)
- `PATCH /purchase-orders/{id}` — header fields only. Edit form binds header.
- `DELETE /purchase-orders/{id}` — **422 on non-draft**. Delete button mounts
  ONLY on draft (mirrors the existing Batch 1 matrix discipline).
- Void + receipt endpoints exist and behave (verified live).
- **`edit_tier` values + tier→button mapping: Claude Code to confirm off the
  backend contract before/at review (see Edit + Delete §).**

---

## R7.4 — Receipt form

Re-enable `po-actions-receipt-btn` + `po-actions-receipt-partial-btn` (issued /
partially_receipted). Form posts to the receipts endpoint via `useCreateReceipt`.
On success, invalidate the PO query AND the committed-column cache — a receipt
moves committed→actual money, so the Budgets grid's committed figure is stale
until refreshed. Use coarse `['budgets']` invalidation (the receipt hook has no
`budgetId`/`lineId` on hand; coarse matches the budgets.js:245 precedent). Trim
both testids from `DEFERRED_TESTIDS` + add positive matrix assertions in the same
commit.

**Tests:** Jest — receipt-btn renders on issued+partial, NOT on draft/pending/
approved/closed; form submit calls the hook; persona gating matches the workflow
perm. E2E — `po-receipt.pm.spec.ts`: issued PO → receipt flow → status flips.

---

## R7.5 — Approvals dashboard (PER-PROJECT — locked)

A **per-project** list surface for POs in `pending_approval` that the current
persona can action. Data source: `useProjectPOs(projectId, { params: { status:
'pending_approval' } })`. Reuse `POApprovalPanel` (Batch 1) per row or link to it.
Read-only list + action affordance; no new mutation logic beyond what Batch 1
shipped, and no new query hook (reuse `useProjectPOs`).

> If `listProjectPOs` does not yet honour a `status` param server-side, Claude
> Code to flag at review; client-side filter on the returned list is an
> acceptable Batch-2 fallback (the per-project PO count is small).

**All-projects global approvals view is OUT OF SCOPE** (no global PO-list hook
exists; needs a new query + likely a backend list-by-status endpoint). Logged at
§CARRIED FORWARD.

**Tests:** Jest — renders pending POs for the project, hides non-pending,
respects perm (a persona without approve perm sees the list but not the action).
E2E — `po-approvals.pm.spec.ts`: dashboard shows a pending PO, approve from the row.

---

## R7.6 — Confirm-dialog + Void wiring + optimistic layer

- **Void:** re-enable `po-actions-void-btn` + `po-actions-void-issued-btn` behind
  a **required-reason** confirm dialog. Mirror the existing `po-reject-dialog`
  exactly: confirm `disabled` until a trimmed reason is entered; `*-cancel` /
  `*-confirm` testids. Posts to the void endpoint; on settle, invalidate PO +
  committed-column cache (void releases commitment).
- **Confirm-dialog:** destructive verbs (Void, Delete) route through a confirm
  dialog. Reuse the send-back/reject `Dialog` shape already in the file — do NOT
  introduce a new dialog primitive.
- **Optimistic layer — BUILD FRESH.** There is no existing optimistic pattern to
  extend: `usePoTransition` is plain `onSuccess`-invalidation today (see GROUNDED
  FACTS). For commitment-changing verbs (void, send-back, receipt) add:
  `onMutate` → `cancelQueries` + snapshot + optimistic `setQueryData` on
  `poKeys.detail(poId)`; `onError` → rollback from snapshot; `onSettled` →
  invalidate `poKeys.detail(poId)`, `poKeys.all`, AND **`['budgets']` (coarse)**
  so the committed column refreshes. The budgets.js:138-154 / 170-192 optimistic
  blocks are the in-repo reference shape to follow.

**Tests:** Jest — void requires a reason (confirm disabled until reason entered);
optimistic update applies then rolls back on mock error; settle invalidates
`['budgets']`. E2E — `po-void.pm.spec.ts`: issued PO → void with reason → status
flips, commitment released.

---

## Edit + Delete forms (Option A — header-only)

- **Edit:** re-enable `po-actions-edit-btn` (draft) + `po-actions-edit-issued-btn`
  (issued, if `edit_tier` permits). Header-only form → `PATCH`. **Gate =
  internal user + has access to this project + has the PO-edit permission**, then
  `edit_tier` decides draft-edit vs issued-edit availability. Use the existing
  lowercase-string `edit_tier` convention. **Claude Code to confirm the exact
  `edit_tier` enum values and which value enables `edit-issued-btn` vs
  `edit-btn`** — do not invent them; bind to whatever the backend returns. Trim
  both testids.
- **Delete:** re-enable `po-actions-delete-btn` — **draft only** (backend 422s
  non-draft). Behind the confirm dialog. Trim the testid.

**Tests:** Jest — edit-btn renders per perm + edit_tier; delete-btn renders ONLY
on draft, never on issued+; delete behind confirm. E2E — `po-edit.pm.spec.ts`
(edit header field, persist), `po-delete.pm.spec.ts` (delete draft; assert issued
PO has no delete affordance).

---

## OPTIONAL — `e2e:po-batch2` script

Add to `frontend/package.json` scripts:
```
"e2e:po-batch2": "playwright test --grep @po-batch2"
```
Tag the new specs (`receipt/approvals/void/edit/delete`) with `@po-batch2` for
fast iteration. Keep `@smoke` on the lifecycle-critical ones so they also run in
`e2e:smoke`. (Grep-tag convention confirmed against existing `e2e:smoke` script.)

---

## ACCEPTANCE CRITERIA

- AC1 — all 7 `DEFERRED_TESTIDS` entries removed (array EMPTY); each wired button
  has a positive matrix render assertion; the empty-loop regression-guard block is
  DELETED (not left iterating an empty array).
- AC2 — Delete mounts ONLY on draft (never issued+); backend 422 discipline mirrored.
- AC3 — Edit is header-only (no line-item editing); gated by internal + project
  access + edit perm, then `edit_tier`.
- AC4 — Void requires a reason; routes through confirm dialog (reject-dialog shape).
- AC5 — commitment-changing verbs (void, send-back, receipt) refresh the Budgets
  committed column via coarse `['budgets']` invalidation on settle, plus
  `poKeys.detail` + `poKeys.all`.
- AC6 — Jest suite green; report COUNT (was 387). E2E: new specs written + the
  lifecycle spec still green.
- AC7 — bundle size reported (Chat 19C had ~13 kB gz headroom under cap — confirm
  Batch 2 stays under).

---

## SELF-REPORT (raw artefacts)

1. `git log --oneline -3` (working tree; operator pushes).
2. The final `DEFERRED_TESTIDS` array (must be EMPTY) + confirmation the empty-loop
   guard block was removed.
3. Jest tail with COUNT (before 387 → after N).
4. The status×persona×testid matrix test output proving each re-enabled button
   renders where expected and NOT where it shouldn't (esp. delete draft-only).
5. The literal `onSettled`/`onMutate`/`onError` block for the optimistic verbs,
   showing the `['budgets']` invalidation (AC5 evidence — assertion ≠ artefact).
6. The new E2E spec filenames + a `yarn e2e:smoke` (or `e2e:po-batch2`) pass tail.
   (Operator runs the full local Playwright pre-push — Emergent provides one smoke
   run + screenshot.)
7. Bundle size (gz) vs cap.

---

## STOP GATE

After self-report, STOP. Operator runs local Playwright (`yarn e2e:po-batch2` +
`yarn e2e:smoke`) → Claude Code independent review (incl. `edit_tier` enum
confirmation + R7.5 `status`-param server support) → push.

---

## CARRIED FORWARD (do NOT action here)
- **All-projects approvals dashboard** — global PO-list-by-status view across
  every project the persona can action. Needs a new global query hook + likely a
  backend list-by-status endpoint. NEW backlog item (Chat 28 decision).
- **Delivery / collection acceptance note** — generate a shopping-list /
  delivery/collection acceptance note off a PO, assign it, and
  email/message/notify the assignee. Proper feature (note generation + assignee +
  notification plumbing, which isn't switched on yet). Spec under the
  supplier/delivery work. NEW backlog item (Chat 28 decision).
- Line-item mutation backend mini-pack (Option B) — separate, if/when needed.
- P0.2 metadata enrichment (`receipt_id` on Status_Change audit row) — backlog.
- `alembic downgrade --sql` CI canary — backlog.
- 2 cosmetic from P1 review: rename `test_downgrade_upgrade_round_trip_preserves_schema`
  (no longer round-trips 0025 post-R5); clarify the `_lock_appraisal_for_update`
  wrapper docstring. Fold into a cleanup pass.
- **P2 (Claude Code P1 finding):** verify no governance router defers the commit
  after `create_new_version` (deferred commit reopens a cross-worker race). Audit
  governance handlers; wrap in immediate try/commit/except if any defer.
- `test_projects.py` 93-error `appraisal_scenarios` FK carry-forward — dedicated pass.
