# SY Hub — Build Pack: Prompt 2.5 §R7 — PO Workflow UI + Option B + Nav Fix

**Chat:** 25 (drafting) → 25/26 (build)
**Governs:** Prompt 2.5 §R7. The repo document `SY_Hub_Chat_24_Build_Pack_v1.md §R7`
is the authority on any conflict — re-read it before building. This pack
**adds** two items not in the original §R7 (decided in Chat 25): the **Option B**
approval-landing change (R7.0) and the **navigation fix** (R7.1).
**Acceptance:** G7.1–G7.9 (this pack; supersedes the original G7.1–G7.6 count).
**Predecessor state:** R5.5 + R6 green on `main`. Alembic head `0033_po_receipts`.
Permissions 102. Roles 10. Bundle ~385 kB gz (cap 437).

---

## STANDING RULES (carry from Chat 24/25 — non-negotiable)

1. **"Committed" ≠ "pushed."** Operator clicks Save to GitHub; triage re-pulls
   `main` to confirm before sign-off. Agent cannot push from inside the fork.
2. **Backend sections sign off only with a raw clean-DB migration run** reaching
   head + live `SELECT` proof + the section's tests actually executed.
3. **"Tests passing" can mean the suite never ran.** Confirm test COUNT and that
   the new files COLLECTED, not just "green."
4. **Assertions ≠ evidence.** Print the literal artefact (curl body, SELECT
   output, grep output, jest run summary), never a summary of it.
5. **Verify-don't-trust loop stays.** Expensive in tokens, cheaper than a broken
   backend.
6. **STOP gates are real.** Operator approves each R-section before the next.
   No auto-advance.

---

## SCOPE

### In scope
- **R7.0** Backend: within-budget PO submit lands at `approved` (NOT auto-issue).
  Issue becomes always-explicit. Self-approval guard proven by test.
- **Phase 0** Data-contract verification of all workflow endpoints before UI.
- **R7.1** Navigation fix: working route + nav entry + project-page link to the
  budget grid.
- **R7.2** `<POActionButtons />` — context-aware action set per status × permission.
- **R7.3** `<POApprovalPanel />` — approve/reject with reason; over-budget
  `budget_snapshot` display; sensitive-gated.
- **R7.4** `<POReceiptForm />` — line-by-line qty received + photo upload.
- **R7.5** `<MyApprovalsDashboard />` at `/approvals`.
- **R7.6** Optimistic updates + rollback toast (Sonner); confirm dialogs for
  void/close/delete.

### Out of scope (do NOT build; STOP and report if a step seems to need it)
- Bills / actuals wiring (later Documents & Compliance track).
- Variations (later prompt).
- The full mobile-shell rework (Future_Tasks §12).
- Any new migration unless R7.0 genuinely requires one (it should NOT — see R7.0).
- Bulk approve / bulk receipt (note to backlog if it comes up).
- The R6 visual-polish pass (logged for end-of-build design pass).

---

## R7.0 — BACKEND: Option B (within-budget → `approved`, not auto-issue)

**Decision (Chat 25, operator):** A within-budget PO must land at `approved` on
submit and require a **separate, explicit Issue action** before it reaches
`issued`. Rationale: `approved`-but-not-`issued` is the safety buffer — committed
in the books, supplier not yet told, still pullable.

**Current behaviour to change:** `app/services/po_approvals.py` (~lines 166–190,
"Case 1 — within budget AND caller didn't flag approval_required: auto-issue").
Today this collapses `draft → issued` directly, skipping `approved`.

**Required behaviour:**
- Within-budget submit, no `approval_required` flag → transition to **`approved`**
  (NOT `issued`). No approval row needed (auto-approved), but the landing state
  is `approved`.
- Over-budget submit → `pending_approval` (UNCHANGED — already correct).
- `issue` is now reachable ONLY via the explicit issue endpoint/action, from
  `approved`. Verify the issue endpoint already exists (JOB 1 step 6 issued PATH
  B, so it does) — confirm its exact path in Phase 0.

**Money-contract invariant (MUST hold, prove it):** `committed_value` =
SUM(net) for POs in {`approved`, `issued`, `partially_receipted`, `receipted`}.
Because `approved` is already a committed status, **Option B does NOT move the
commitment contract** — commitment still appears the instant the PO is approved.
Prove with a live SELECT that a within-budget PO contributes to `committed_value`
at `approved`, before any issue.

**Migration:** NONE expected. This is a service-logic change only. If you believe
a migration is needed, STOP and report — do not add one silently. Confirm
`alembic current` = `0033_po_receipts` is UNCHANGED at section end.

**Self-approval guard (prove it — JOB 1 never did):**
JOB 1 only showed a PM (no `pos.approve`) gets a permission 403. It did NOT prove
the distinct guard that stops an approver approving their OWN PO. R7.0 MUST add a
test:
- A `director` (HAS `pos.approve`) CREATES a PO that requires approval.
- That same director attempts to approve it → expect the **self-approval-specific
  rejection** (NOT a generic permission 403 — assert the actual error/detail
  distinguishes "cannot approve own" from "missing permission").
- A SECOND approver (another director / admin / super_admin) approves it
  successfully.
Locate the guard in `app/services/po_approvals.py`. If the guard does not exist,
STOP and report (this is a money-safety control — do not silently skip).

**R7.0 tests** (`backend/tests/test_po_approvals.py` or the existing approval
suite — match the repo's file):
- `test_within_budget_submit_lands_approved_not_issued`
- `test_within_budget_approved_requires_explicit_issue` (approved → issue → issued)
- `test_within_budget_approved_contributes_to_committed_value` (live commitment proof)
- `test_over_budget_submit_still_pending_approval` (regression — unchanged path)
- `test_self_approval_rejected_distinct_from_permission_denied`
- `test_second_approver_can_approve` (the non-creator approves successfully)

**R7.0 STOP-gate evidence (print, do not summarise):**
- raw `alembic current` = `0033_po_receipts` (unchanged)
- the changed function body (before/after of the Case-1 branch)
- pytest COUNT before/after + the six R7.0 test names in the run summary, all green
- a live SELECT showing a within-budget PO's net in `committed_value` at `approved`
- raw curl: within-budget submit → response status `approved`; then issue →
  `issued`

GATE: all above proven → reply `R7.0 GREEN` + artefacts → STOP, await operator
→ then Phase 0. Any failure → STOP, print raw error.

---

## PHASE 0 — DATA-CONTRACT VERIFICATION (hard gate, before any UI)

Run real calls against the live host as the relevant persona. PRINT each
response. The R6 lesson: never build UI on an assumed endpoint.

Verify existence + exact path + response shape for each workflow action. The
paths below are ASSUMED — confirm the ACTUAL path in the repo router
(`app/routers/purchase_orders.py`) and use the real one; report any difference.

| # | Action | Assumed path | Confirm |
|---|---|---|---|
| P0.1 | Submit | `POST /api/v1/purchase-orders/{id}/submit` | exists? body? response status field? |
| P0.2 | Approve | `POST /api/v1/purchase-orders/{id}/approve` | exists? expects reason? |
| P0.3 | Reject | `POST /api/v1/purchase-orders/{id}/reject` | exists? expects reason? |
| P0.4 | Issue | `POST /api/v1/purchase-orders/{id}/issue` | **MUST exist for Option B** — confirm path |
| P0.5 | Receipt create | `POST /api/v1/purchase-orders/{id}/receipts` | body shape (lines[], photos)? |
| P0.6 | Void | `POST /api/v1/purchase-orders/{id}/void` | exists? director/admin only? |
| P0.7 | Close | `POST /api/v1/purchase-orders/{id}/close` | exists? |
| P0.8 | Unlock | `POST /api/v1/purchase-orders/{id}/unlock` | exists? from which state → which? |
| P0.9 | My-approvals list | `GET /api/v1/purchase-orders?status=pending_approval` (or dedicated `/approvals`) | **what actually serves the approver's queue?** print the real query/endpoint + whether it scopes to the current approver |
| P0.10 | `budget_snapshot` | (on the approval row / PO payload) | where does the approval panel read over-budget `budget_snapshot` from? print the shape |
| P0.11 | Sensitive gating | call P0.9 + a PO detail as `read_only` | confirm £ fields null server-side |
| P0.12 | `edit_tier` | (PO detail payload, seen in R6: `edit_tier`) | what values? how should buttons respect FULL / HEADER_ANNOTATION_ONLY / READ_ONLY? |
| P0.13 | **Amend-an-`approved`-PO path** (Option B consequence — see below) | `POST .../unlock` from `approved` → `draft`? or in-place edit at `approved`? | **CRITICAL:** can an `approved` (not-yet-issued) PO be AMENDED, or only voided? Print the actual allowed transitions FROM `approved` in the backend state machine. |

**Why P0.13 matters:** Option B's stated rationale (Chat 25) is that
`approved`-but-not-`issued` is a *changeable or cancellable* buffer. Cancellable =
`void` (exists). **Changeable** requires either an in-place edit at `approved` OR
an unlock `approved → draft → edit → re-submit`. If the backend allows NEITHER,
the buffer only lets you void-and-recreate, which partially defeats the operator's
intent. Phase 0 MUST establish which exists. If neither exists, STOP and report —
do NOT silently ship a buffer you can only void. Surface it to the operator as a
decision (accept void-only for now, or add a small unlock-from-approved backend
patch).

GATE:
- A REQUIRED endpoint missing (P0.4 issue especially) → STOP, report, propose a
  minimal backend addition as a separate pre-R7 patch. Do NOT build UI on it.
- P0.13 amend path absent → STOP, report to operator as a decision (not a silent skip).
- The my-approvals source (P0.9) unclear → resolve it before R7.5; print the
  decision.
- All present → reply `PHASE 0 GREEN` with the printed shapes → STOP, await
  operator → then R7.1.

---

## R7.1 — NAVIGATION FIX (door to the budget grid)

**Problem (found Chat 25):** the budget grid is only reachable by hand-editing
the URL. Three gaps:
- `frontend/src/.../AppShell.jsx` (~line 33) has a `Budgets` nav entry hard-disabled
  (`enabled: false`), greyed out, not clickable.
- `App.js` (~lines 245–250) has NO `/budgets`-family route under a project;
  the catch-all `*` renders the stale "not yet available in Phase 1" copy.
- `pages/ProjectDetail.jsx` (~lines 205–220) links to cost-codes / appraisals /
  actuals but NOT budgets.

**Required:**
- Add an in-context link from Project Detail → the project's budgets
  (`/projects/{projectId}/budgets`), alongside the existing cost-codes /
  appraisals / actuals links.
- Confirm the route(s) that reach `BudgetsList` and `BudgetDetail`/`BudgetGridV2`
  are registered and reachable (the deep paths work today — make the entry points
  click-reachable, don't break the working deep route).
- The top-level disabled `Budgets` sidebar entry: EITHER enable it to route to a
  sensible budgets landing, OR leave disabled and rely on the project-context
  link — **operator preference unknown; default to enabling the project-context
  link only and leaving the global sidebar entry as-is, and report which you did.**
  Do NOT enable a global entry that routes nowhere useful.
- Do NOT touch the stale "Phase 1" catch-all copy here (it's logged to polish
  backlog §22) unless removing it is necessary to register the route — if so,
  note it.

**R7.1 tests (Jest):** project-detail renders a budgets link to
`/projects/{id}/budgets`; the budget route resolves to the grid component (not the
catch-all). URL-contract pin if any new path string is introduced.

GATE: link reachable end-to-end by click → `R7.1 GREEN` + the click-path printed
→ STOP, operator eyeball (they could not reach it before) → then R7.2.

---

## R7.2 — `<POActionButtons />` (workflow brain)

Context-aware: renders ONLY the actions valid for the PO's current `status` AND
the current user's permissions AND `edit_tier`. Single source of truth for the
status machine in the UI.

**Action matrix** (confirm against backend transitions in Phase 0; backend is
authority):

| status | actions shown | permission gate |
|---|---|---|
| `draft` | Submit, Edit, Delete | `pos.create`/`pos.edit`/`pos.delete` |
| `pending_approval` | Approve, Reject, Unlock | `pos.approve` (+ self-approval guard hides/disables Approve for the creator); Unlock per P0.8 |
| `approved` | **Issue**, Void, _(Amend — only if P0.13 confirms an unlock/edit path)_ | `pos.issue`; Void = `pos.void`; Amend per P0.13 |
| `issued` | Receipt, Void | `pos.receipt`; `pos.void` |
| `partially_receipted` | Receipt, Void | `pos.receipt`; `pos.void` |
| `receipted` | Close | `pos.close` |
| `closed` | none (terminal) | — |
| `voided` | none (terminal) | — |

Rules:
- An action the user lacks permission for is NOT rendered (not just disabled),
  EXCEPT where a disabled+tooltip is clearer (e.g. self-approval: show Approve
  disabled with "You cannot approve your own PO"). State the choice per action.
- `edit_tier === 'READ_ONLY'` → no mutating actions at all.
- `edit_tier === 'HEADER_ANNOTATION_ONLY'` → only the annotation-level actions
  per backend; confirm in Phase 0.
- Buttons trigger the R7.6 optimistic-update + confirm-dialog flow.

**R7.2 tests:** per-status × per-persona render matrix (FULL PM, director/approver,
read_only) — assert exactly the expected button set; self-approval Approve
disabled for creator-approver; terminal states show no actions.

GATE: `R7.2 GREEN` + render-matrix test names → STOP → R7.3.

---

## R7.3 — `<POApprovalPanel />`

Shown in the approve/reject flow for a `pending_approval` PO.
- Displays the over-budget `budget_snapshot` (from P0.10): per-line
  `cost_code`, `current_budget`, `actuals_to_date`, `committed_value`,
  `this_po_net`, `over_by`, `projected_total`, `is_overrun`. **All £ values via
  `<SensitiveValue/>`** (read_only → em-dash).
- Approve: optional/required reason per P0.2; POST approve.
- Reject: reason per P0.3; POST reject → PO returns to the rejected state
  (confirm: draft? rejected? — Phase 0).
- The creator (if they hold `pos.approve`) sees the panel READ-ONLY with Approve
  disabled (self-approval guard) — never a path to approve their own.

**R7.3 tests:** snapshot renders all snapshot fields; read_only → £ em-dash;
approve calls P0.2 with reason; reject calls P0.3; creator-approver cannot approve.

GATE: `R7.3 GREEN` → STOP → R7.4.

---

## R7.4 — `<POReceiptForm />`

Shown when a PO is `issued` or `partially_receipted`. Line-by-line.
- One row per PO line: ordered qty, already-received qty, input for qty-received-now.
- Validate: qty-now > 0 (per `ck_porl_quantity_positive`), and not exceeding
  outstanding (ordered − already-received) — confirm whether backend enforces
  over-receipt; if it does, surface its error; if not, client-guard and note to
  backlog.
- Photo upload: inline metadata (matches `purchase_order_receipt_photos`); the
  receipt POST carries photo(s) per P0.5 (no standalone multipart endpoint —
  Future_Tasks §20). Show thumbnail preview with `loading="lazy"` + alt +
  broken-src fallback (reuse the R6 thumbnail pattern).
- On full receipt → backend auto-flips to `receipted` (proven JOB 1 step 8);
  reflect the new status without a manual refresh.

**R7.4 tests:** renders a row per line with outstanding qty; qty-now ≤ outstanding
guard; POST shape matches P0.5; photo metadata included; status reflects the
backend flip.

GATE: `R7.4 GREEN` → STOP → R7.5.

---

## R7.5 — `<MyApprovalsDashboard />` at `/approvals`

- New route `/approvals`. Add a nav entry (or a notification-driven link).
- Lists POs awaiting the CURRENT user's approval, sourced per P0.9. If P0.9 is a
  generic `?status=pending_approval`, confirm it is scoped to POs the approver is
  actually entitled to approve (Pattern α + self-approval excluded — the approver
  should NOT see their own PO as actionable here).
- Each row: PO number (link to detail), supplier, project, net (sensitive-gated),
  over-budget badge if `is_overrun`. Click → PO detail with the approval panel.
- Empty state ("No POs awaiting your approval"), loading skeleton, error+retry.

**R7.5 tests:** lists pending POs for the approver; excludes the approver's own
POs; read_only persona sees £ em-dash (or no access — confirm); empty state;
URL-contract pin for P0.9's path.

GATE: `R7.5 GREEN` → STOP → R7.6.

---

## R7.6 — Optimistic updates + confirm dialogs

- All workflow mutations (submit/approve/reject/issue/receipt/void/close/delete)
  use react-query optimistic update: update cache immediately, roll back + Sonner
  error toast on failure, success toast on success. Invalidate the affected PO +
  budget-line queries (commitment values change on approve/issue/void/close — keep
  the R6 grid in sync).
- Confirm dialogs (destructive only): Void, Close, Delete. Each names the PO and
  the consequence ("Void PO-…? This is terminal and releases the commitment.").
- Confirm the commitment-affecting transitions invalidate the R6
  `useBudgetLinePOs` / bulk `useBudgetPOs` caches so the grid's committed/pending
  columns refresh.

**R7.6 tests:** optimistic update applies then rolls back on a mocked failure +
toast fires; confirm dialog blocks the mutation until confirmed; cache
invalidation triggers for budget-line queries on approve.

GATE: `R7.6 GREEN` → STOP → tests/bundle sweep.

---

## TESTS — SWEEP (after R7.6)

- Full Jest run: print COUNT before/after; confirm ALL new R7 suites COLLECTED
  (name the files) and ran; 0 fail.
- Full backend pytest for the touched suites (R7.0): print COUNT + names.
- URL-contract pins for every NEW path string introduced (submit/approve/reject/
  issue/void/close/unlock/approvals as applicable) — add to the PO URL-pin file.
- Manual smoke at 380px on the approval panel + receipt form (mobile site users
  will receipt on phones — hard constraint #3). Screenshot the receipt form at
  380px.

## BUNDLE

- All R7 frontend code in the lazy `suppliers-po` chunk (or the budget chunk where
  the action buttons live) — main bundle unchanged.
- Print main bundle gz; MUST stay < 437 kB cap; report headroom (was ~385–395).

---

## ACCEPTANCE CRITERIA (G7.1–G7.9)

- **G7.1** Within-budget submit lands `approved`, not `issued`; explicit Issue
  required (Option B). Proven by R7.0 test + live curl.
- **G7.2** Self-approval guard proven: an approver cannot approve their own PO
  (distinct from a permission denial); a second approver can.
- **G7.3** Budget grid reachable by click (Project Detail → Budgets), not just by
  URL editing.
- **G7.4** `<POActionButtons />` renders exactly the valid action set per status ×
  permission × edit_tier across all three personas.
- **G7.5** `<POApprovalPanel />` shows `budget_snapshot`, sensitive-gated; approve/
  reject work; creator-approver cannot approve.
- **G7.6** `<POReceiptForm />` does line-by-line qty + photo; full receipt flips to
  `receipted`; qty guarded.
- **G7.7** `/approvals` lists the approver's queue, excludes their own POs,
  sensitive-gated.
- **G7.8** Optimistic updates roll back on failure with a toast; destructive
  actions confirm; R6 grid commitment columns refresh after commitment-affecting
  transitions.
- **G7.9** Money contract unchanged: `committed_value` = SUM(net) over {approved,
  issued, partially_receipted, receipted}; commitment appears at `approved`,
  releases on void/close. Re-proven by a live SELECT after the R7 flow.

---

## SELF-REPORT FORMAT (each R-section)

```
R7.x GREEN — <one line>.
Evidence:
  - [raw artefact 1]
  - [raw artefact 2]
  ...
Tests: <count before> → <count after> (+N); new suites collected: <names>.
STOP — awaiting operator. Not starting R7.(x+1).
```

At full close only: bundle gz + headroom, full jest/pytest counts, then Save to
GitHub (operator clicks; triage re-pulls to confirm landed).

---

## STOP GATES SUMMARY

R7.0 → Phase 0 → R7.1 → R7.2 → R7.3 → R7.4 → R7.5 → R7.6 → sweep. Operator
approves between each. No auto-advance. Operator eyeballs R7.1 (nav), R7.3
(approval panel), R7.4 (receipt form) on the live preview before their gates pass.

## CHUNKING NOTE

R7.0 + Phase 0 + R7.1 is a natural first chat. R7.2–R7.6 + sweep may need a
second chat. Do NOT force the full set into an exhausted chat. Close cleanly with
a handoff if context runs short.
