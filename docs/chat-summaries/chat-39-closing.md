# Chat 39 — Build Pack 2.6-FIX closing summary

**Pack:** Build Pack 2.6-FIX — Budget Integrity & BCR Fix-Pack
**Branch base:** main @ `0038_sc_valuations`, 129 permissions, 10 roles
**Head after this pack:** `0039_committed_single_writer`
**Permissions:** 129 (unchanged — confirmed via `SELECT COUNT(*) FROM permissions`)
**Roles:** 10 (unchanged)
**Backlog file (`docs/SY_Hub_Phase2_Backlog.md`):** NOT touched.

---

## What landed (Chat 39 §R2 scope, frozen)

### Backend integrity fixes
- **A1 — single writer of `committed_not_invoiced`.** Migration `0039`
  rewrites `fn_budget_line_recompute_commitments` so it only writes
  `committed_value`. Python (`services/budgets_reconciliation.recompute_for_line`)
  is now the sole writer of `committed_not_invoiced`, using the formula
  `retention_pending + po_committed_not_invoiced`. The Python filter
  mirrors the trigger's WHERE clause column-for-column. Application PO
  mutation paths now call a new `recompute_for_po(db, po_id)` helper
  after each `db.flush()` to keep the column fresh.
- **A2/A3 — lock parity.** `recompute_for_line` now acquires the
  parent-budget FOR UPDATE lock first, then the BudgetLine FOR UPDATE
  lock — same order as `apply_bcr`. The valuation certify path picks
  this up automatically via its `recompute_for_line` call.
- **A4 — explicit `budget_line_id` on valuation certify.** The
  Pydantic body requires the field (FastAPI emits 422 on omission).
  The service-side shim raises `ValuationStateError`. The silent
  `LIMIT 1` first-line guess is gone.

### Frontend defects
- **B-CONTINGENCY.** Backend `_serialise_line` now emits
  `is_contingency` as a real boolean. Frontend Zod
  `BudgetLineSchema` adds `is_contingency: z.boolean().default(false)`.
  Contingency-drawdown source-line validator in
  `CreateBudgetChangeDialog` now passes (it was rejecting every line
  because of `!undefined === true`). The "(contingency)" tags in
  `BudgetChangeDetail` / `BCRLineEditor` render as designed.
- **B-DATA.** `BudgetChangeDetail.jsx:226` now resolves cost code via
  `useCostCodes` + `buildCostCodeMap` (mirrors `BudgetGridColumns`
  pattern), instead of binding to the non-existent `bl?.cost_code`.
- **C-UNCAT.** `useCostCodes` query now sets
  `placeholderData: keepPreviousData` so the map doesn't blank on
  post-mutation refetch. `groupLinesByCategory` returns a single
  "Loading…" bucket when the map is empty and lines carry valid
  `cost_code_id` values, so the grid never flashes "— Uncategorised —"
  during a refetch.

---

## §R5 tests (named EXACTLY as specified — no consolidation)

| # | Path | Notes |
|---|------|-------|
| 1–4 | `backend/tests/test_budget_integrity_committed.py` | Test #2 includes explicit retention-RELEASE transition coverage |
| 5–7 | `backend/tests/test_budget_recompute_locking.py` | Test #5 is a genuine two-connection psycopg-3 `FOR UPDATE` + `statement_timeout` probe — no mocks |
| 8–10 | `backend/tests/test_valuation_budget_line_required.py` | Test #10 directly asserts the silent guess path is removed |
| 11–12 | `backend/tests/test_budget_line_serialisation.py` | Regression pin on cost_code_id (B-DATA) + is_contingency (B-CONTINGENCY) |
| 13–14 | `frontend/src/components/budgetChanges/__tests__/CreateBudgetChangeDialog.contingency.test.jsx` | Drives the validator directly; exported `validateBeforeSubmit` from the dialog |
| 15 | `frontend/src/pages/projects/__tests__/BudgetChangeDetail.costcode.test.jsx` | Mocks `useCostCodes`, asserts the resolved code renders |
| 16 | `frontend/src/components/budgets/grid/__tests__/budgetCategoryGroup.test.js` | Loading guard regression pin |

---

## §R6 acceptance gates

- [x] §R0.1 pre-flight executed in the prior session; operator GO received.
- [x] **A1**: single writer of `committed_not_invoiced` verified; both
  buckets survive concurrent actual + PO activity. Tests 1–4 green
  (assert financial state, not status codes).
- [x] **A2/A3**: `recompute_for_line` + valuation certify hold parent-budget
  FOR UPDATE; tests 5–7 green; Test #5 is a real two-connection probe.
- [x] **A4**: `budget_line_id` required (422 on omit); no silent guess.
  Tests 8–10 green.
- [x] **B-CONTINGENCY**: contingency drawdown source-line guard accepts
  contingency-flagged lines and rejects non-contingency lines. Tests 13–14 green.
- [x] **B-DATA**: BCR detail shows the real cost code. Test 15 green.
- [x] **C-UNCAT**: grid does not flash "— Uncategorised —" on refetch. Test 16 green.
- [x] **A6**: investigated, findings below, NO code changed.
- [x] **Migration 0039**: applies clean (verified `alembic downgrade -1` →
  `alembic upgrade head` round-trip on the live DB). Head advances
  `0038_sc_valuations` → `0039_committed_single_writer`. Reversible
  downgrade restores the previous trigger body verbatim.
- [x] **Backend suite double-run on warm DB.**
  - Run 1: **1228 passed, 3 xpassed** in 226.82s.
  - Run 2 (second run clears warm-DB errors): **1228 passed, 3 xpassed**
    in 224.18s. Identical counts.
- [x] **Frontend suite**: **421 passed across 66 suites** (was 405 pre-pack;
  +16 new tests, no regressions).
- [x] **CHANGELOG entry written** (this section under `## Chat 39`).
- [x] **Permission count unchanged (129)** — re-verified post-fix.
- [x] **Backlog NOT touched** — new findings / out-of-scope items are
  PLAIN TEXT below.

---

## §A6 — CIS-in-rollup (INVESTIGATE-ONLY, no code change)

**Question (re-stated):** is CIS correctly payment-side only (a
withholding at payment, not a cost reduction)? If cash-payable should
reflect CIS withholding anywhere, where would the ledger entry go?

**Read trail.** `services/actuals.py:166-280` computes
`cis_deduction_amount` and stores it on the Actual row; the column is
separate from `net_amount`. `services/budgets_reconciliation.recompute_for_line`
sums `Actual.net_amount` (PRE-deduction per Build Pack 2.8b §R0.2)
and subtracts `retention_pending` only. CIS is NOT subtracted from
`actuals_to_date`. `services/payment_notices.py:135,215` carries
`cis_deducted` on the auto-created Payment notice.

**Finding.** The current architecture is semantically correct: CIS is
a *withholding* at the payment cycle (the contractor owes HMRC the
deducted amount on the subcontractor's behalf — it is NOT a cost
reduction to the project). The project budget tracks **cost incurred**
(gross_this_cert on the actuals chain); the Payment notice tracks
**cash payable to supplier** (gross − retention − CIS). These two
ledgers live in different places intentionally, and the cost-tracker's
omission of CIS from `actuals_to_date` is the design — not a bug.

**Operator decision required (none required from Emergent).** If at
some point we want a cash-payable view that nets retention + CIS at
the budget level, the natural place is a *new* derived column (e.g.
`cash_payable_to_date`) on `budget_lines`, populated by a second
recompute pass that sums Payment-notice `net_payable` / `cis_deducted`
across the line's actuals. We do NOT recommend folding CIS into
`actuals_to_date` — that would conflate cost and cash, breaking the
cost-tracker's existing contract with the variance bands.

---

## Out-of-scope items (§R3 — operator adds to backlog by hand)

The Build Pack §R3 lists six items that are deliberately not patched
in this pack. Re-listing here as plain text for operator triage:

- **A5** — dead `commitments.*` permissions (audit found unused entries).
- **A7** — count-based reference numbering should be replaced with a
  proper PostgreSQL sequence (race-free across concurrent inserts).
- **A8** — Withdraw audit stamp columns + Apply action-verb label.
- **B-DESIGN** — teal token drift: `sy-teal-600` / `sy-teal-700` vs
  `sy-teal` across the design tokens.
- **B-MONEY** — two duplicate `fmtGBP` implementations (consolidate).
- **B-SIZE** — `ProjectDetail.jsx` is 831 lines; extract sub-components.

## New findings from this pack (operator triage)

- The `_pick_budget_line_for_subcontract` helper is now a hard-fail
  shim. If the operator decides the certify endpoint should support
  per-subcontract default line mapping, that is a feature add: it
  would store `default_budget_line_id` on the `subcontracts` row and
  fall through to it when the request omits the field. **NOT a
  defect** — current behaviour is intentional per Chat 39 §R2 A4.
- Test-helper updates touch 4 files (`test_subcontract_valuations_service.py`,
  `test_subcontract_valuations_api.py`, `test_retention_releases_service.py`,
  `test_payment_notices_service.py`) to pass an explicit
  `budget_line_id` resolved from the test project's first budget
  line. These mirror real-world caller behaviour under the stricter
  API contract — they are NOT bypasses of the new rule.

---

## Push (operator)

Two commits ready to land:
1. Code + tests + migration (backend services, frontend components,
   16 new tests across 7 files, migration `0039`, test-helper
   updates, head-sentinel test bumps).
2. CHANGELOG + this closing doc.

Operator clicks **Save to GitHub**. If the backlog file shows a
conflict on the PR: do NOT force-push — open the PR via Create
Branch & Push. The backlog file was NOT touched in this pack.
