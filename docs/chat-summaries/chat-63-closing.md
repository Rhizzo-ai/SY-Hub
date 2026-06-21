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
