# Chat 63 — Closing Summary: C2, Seal the Illusory Budget Freeze (B-variant)

**Type:** Critical money-adjacent bug fix. Backend only. No migration, no model
change, no frontend.
**Decision:** Locked by Rhys in Chat 63 — **B-variant**.
**Touch scope:** one new error class, one service guard + comment/metadata
change, one route mapping line, one new test file.

---

## 1. What was broken

Budget statuses: `Draft, Active, Locked, Superseded, Closed`.

```
TERMINAL_BUDGET_STATUSES      = {"Superseded", "Closed"}            # hard freeze
LINE_FROZEN_BUDGET_STATUSES   = {"Locked", "Superseded", "Closed"} # line edits blocked
```

Every normal budget-line / item write flows through `_load_budget_for_write` /
`_load_line_for_item_write` and is correctly blocked on
`LINE_FROZEN_BUDGET_STATUSES`. Actuals posting re-checks
`TERMINAL_BUDGET_STATUSES` (the B27 fix). Those paths were already correct.

**The hole (C2):** `clear_unbudgeted` — the director "acknowledge unbudgeted
spend" action (B102) — deliberately bypassed the gatekeeper. It took a raw
`select(Budget)...with_for_update()` directly, with an inline comment claiming
the acknowledgement "should still be possible" even if the budget had gone
Locked or Closed. So a **Closed** ("sealed") budget could still be mutated
through this one path. That was an undocumented inline judgement call by the
original author — never an actual product decision.

## 2. The decision — B-variant (vs A / B)

Three options were on the table:

- **A — block all frozen statuses** (`LINE_FROZEN_BUDGET_STATUSES`): simplest,
  but it would forbid a director from acknowledging genuine spend on a **Locked**
  budget. Locked is reversible (it has an unlock transition), so a hard block
  there is heavier than the business needs.
- **B (status quo made explicit) — allow everything:** rejected; it leaves
  Closed/Superseded ("sealed history") quietly mutable, which is the bug.
- **B-variant (chosen):** block **terminal** seals only
  (`TERMINAL_BUDGET_STATUSES` = Superseded/Closed → 409), keep **Locked**
  allowed but **audited** (`on_frozen_budget: true`). Late spend on a sealed
  budget must go onto a NEW budget version, never a quiet edit.

**Buildertrend parity** confirmed the five-state model (Draft / Active / Locked
/ Superseded / Closed) and that a soft-locked baseline can still receive an
audited director sign-off, while a closed job is sealed — which is exactly the
B-variant asymmetry.

The net effect: `clear_unbudgeted` is the one money path that blocks on
`TERMINAL_BUDGET_STATUSES` **only**, not the full `LINE_FROZEN` set. This
asymmetry is intentional and must not be "simplified" to reuse
`LINE_FROZEN_BUDGET_STATUSES`.

## 3. What changed

- **`app/services/budget_errors.py`** — new `BudgetSealedError(BudgetStateError)`.
  Subclasses `BudgetStateError` so existing broad `except BudgetStateError`
  still catches it, but the clear-unbudgeted route maps it to **409** rather
  than 422.
- **`app/services/budget_lines.py::clear_unbudgeted`** — terminal-seal guard
  added under the budget lock, after the under-lock idempotency re-check and
  before any mutation; raises `BudgetSealedError` on Superseded/Closed. The
  stale "allow_frozen / should still be possible" comment was replaced with an
  accurate note. Audit metadata gained `budget_status_at_clear` and
  `on_frozen_budget` (`status in LINE_FROZEN_BUDGET_STATUSES`).
- **`app/routers/budgets.py::clear_unbudgeted_line`** — `except BudgetSealedError
  → 409` placed BEFORE the `except BudgetStateError → 422` branch (order matters
  — the subclass must be caught first), import + docstring line added.
- **`tests/test_c2_unbudgeted_freeze.py`** — NEW, 12 tests.

## 4. Gate evidence (hard-stop, money-adjacent)

- **Live Postgres up:** provisioned via `scripts/provision_postgres.sh`;
  `/api/health` → **200**.
- **Migration clean:** alembic head unchanged at **`0049_unbudgeted_order_lines`**
  (this fix adds NO migration).
- **Full pytest, warm DB, second of two runs (raw):**
  `19 failed, 1683 passed, 1 skipped, 3 xpassed, 2 warnings in 311.41s` — **0
  errors**. The new `test_c2_unbudgeted_freeze.py` is **12/12 green**. The 19
  failures are the standing baseline (permission-count assertions + stale
  alembic-head assertions); none are in the C2 touch area. (The first warm run
  showed 90 cross-module teardown ERRORs in `test_appraisals.py` /
  `test_appraisal_governance.py` — those modules pass cleanly in isolation and
  sort alphabetically BEFORE the C2 file, so the errors are a pre-existing
  full-suite data-pollution artifact, independent of C2; they cleared entirely
  on the warm second run.)
- **Live echo on real rows:**
  - **Closed** budget → clear → **409**, row UNCHANGED (`unbudgeted_cleared_at`
    still NULL, `requires_attention` still true), **0** clear-audit rows.
  - **Locked** budget → clear → **200**, `unbudgeted_cleared_at` set, audit row
    with `budget_status_at_clear: "Locked"`, `on_frozen_budget: true`.
- **Pod stability:** single continuous postmaster (no recycle during the gate
  run).

## 5. Notification trigger (logged, not built)

When the notifications mini-track lands: a `clear_unbudgeted` on a **Locked**
budget (`on_frozen_budget: true`) is a candidate notify-the-directors trigger —
a director signed off real spend against a frozen baseline. Log alongside B112.
Not built in this pack.

---

# C1-back — Budget Double-Counts Committed Cost (backend + backfill)

Same chat (63). C1 was split: **C1-back** (this work — the reconciliation maths
fix + link validation + data backfill, backend only) and **C1-front** (the
force-the-choice UI / over-PO warning — backlogged, NOT built here).

## 1. Decisions (locked, Rhys)

- A bill's `linked_commitment_id` points at a **PurchaseOrderLine** (not a whole
  PO) and must sit on the **same budget line** as the bill (Option A).
- `invoiced_against_commitment` becomes a **DERIVED** figure (computed fresh
  inside `recompute_for_line` from the linked bills), **not** a hand-maintained
  running tally. No +/- increments added to the actuals transitions.
- Over-PO check, force-the-choice UI, and recurring POs are OUT of scope
  (backlogged).

## 2. The bug

`committed_not_invoiced = retention_pending + (po_committed −
invoiced_against_commitment)`, but nothing ever wrote
`invoiced_against_commitment` — it stayed 0. So a £10k PO + its £10k bill read
as £20k (the same £10k in both committed and actuals). The double-count.

## 3. The fix (touch scope)

- **`app/services/budgets_reconciliation.py`** — new
  `_invoiced_against_commitment_for_line` (sum of counted bills linked to a PO
  line on the same budget line); `_po_committed_not_invoiced_for_line` now reads
  the DERIVED value (not the stale column) and clamps the PO term at zero
  (`max(committed − invoiced, 0)`); `recompute_for_line` persists the derived
  value back onto the column (single-writer).
- **`app/services/actuals.py`** — new `_validate_linked_commitment`, called on
  the create path (before flush) and on `update_draft_actual` (after the setattr
  loop, whenever EITHER `budget_line_id` OR `linked_commitment_id` is in the
  payload — closes the move-line trap), reading the FINAL row values.
- **`app/services/actual_errors.py`** — new `CommitmentLinkError`
  (`http_status = 422`, `code = "commitment_link_invalid"`), auto-mapped to 422
  by the existing generic `_raise_for` in `app/routers/actuals.py` (no router
  edit needed — the handler catches the base `ActualError` and uses
  `exc.http_status`).
- **`alembic/versions/0050_backfill_invoiced_against_commitment.py`** — NEW
  data-only backfill (revision id `0050_backfill_invoiced_commit`, ≤32 chars for
  the `alembic_version` column). Reuses `recompute_for_line` via a Session bound
  to the migration connection so backfill ≡ live path; idempotent; no-op
  downgrade.
- **`tests/test_c1_committed_double_count.py`** — NEW, 16 tests.
- **`tests/test_packages_service.py`** — the head-pin assertion bumped
  0049→0050 and the test renamed `test_TM_1_alembic_head_is_0050` (mechanical
  maintenance accompanying the new migration; operator-approved).
- The actuals transition bodies, `recompute_summary`, the lock order, the
  retention logic, `COUNTED_STATUSES`, and `PO_COMMITTED_STATUSES` were all left
  untouched.

## 4. Gate evidence (hard-stop, money-adjacent + live-data backfill)

- **Live Postgres up:** provisioned via `scripts/provision_postgres.sh`;
  `/api/health` → **200**.
- **Migration clean:** `alembic upgrade head` applies
  `0050_backfill_invoiced_commit` (backfill recomputed 10 budget lines); new
  head printed; `downgrade -1` → 0049 then `upgrade head` → 0050 round-trips
  without error.
- **Full pytest, warm DB, second of two runs (raw):**
  `20 failed, 1698 passed, 1 skipped, 3 xpassed, 2 warnings in 311.15s`. The new
  `test_c1_committed_double_count.py` is **16/16 green**. The +1 vs the standing
  19-failure baseline was the head-pin in `test_packages_service.py`, bumped
  0049→0050 in the same commit — returning the suite to the clean 19-failure
  baseline (permission-count assertions + stale older-revision head-pins; none
  in the C1-back touch area).
- **Live echo on real rows:**
  - £10k PO + £10k linked posted bill: BEFORE (broken cache) committed_not_
    invoiced=10000 + actuals=10000 = **£20k double-count**; AFTER recompute
    committed_not_invoiced=**0**, actuals=**10000** → **£10k** (£20k→£10k
    correction shown explicitly).
  - Standalone (NULL-link) £3k bill: flows to actuals only;
    `invoiced_against_commitment` unchanged; committed untouched.
  - Backfill on a seeded broken line: committed_not_invoiced 10000→**0**,
    invoiced_against_commitment 0→**10000**.
- **Pod stability:** single continuous postmaster (no recycle during the gate
  run).

## 5. Notification trigger (logged, not built)

When notifications land: a bill posted that takes total-invoiced PAST its PO
line (over-PO) is a candidate notify-the-PM/director trigger. Pairs with the
backlogged over-PO warning. Log alongside B112; not built here.
