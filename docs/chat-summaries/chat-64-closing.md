# Chat 64 — Closing Summary: C1-front, Force-the-Choice Bill-Entry UI

**Type:** Frontend-led, with ONE small additive read-only backend change.
**Depends on:** C1-back (Chat 63) — shipped on `main`. This is its frontend
partner.
**Migration:** NONE. The new backend field is derived at serialisation time,
not stored. Alembic head unchanged at **`0050_backfill_invoiced_commit`**.
**Permissions:** NONE added. Finance already holds `pos.view` +
`pos.view_sensitive`.

---

## 1. Why this existed

C1-back fixed the budget double-count by deriving "invoiced against commitment"
fresh from bills whose `linked_commitment_id` points at a `PurchaseOrderLine`
on the same budget line, and it enforces that link on create AND update (422
`CommitmentLinkError`). But the bill-entry form (`CreateActualSheet.jsx`) never
set `linked_commitment_id` — the schema accepted it, the form ignored it. So
every manually-entered bill was implicitly "standalone" and Louise had no way
to tie a bill to the PO it pays down.

This pack makes the choice **explicit and mandatory**: when entering a bill on a
budget line, the user must either pick one of the open PO lines on that line, or
tick an explicit "No PO available".

## 2. Operator decisions built (locked, Chat 64)

1. **Remaining per PO line** is shown (requires the backend addition below).
2. **Standalone wording = exactly "No PO available".**
3. **Budget line with no open PO lines** → auto-treated as standalone with a
   short note; no tick forced.
4. **Changing the budget line after a PO line was picked** → clears the choice
   automatically and shows a brief reset note.

## 3. What changed

### Backend — derived, read-only `remaining_amount` on PO lines

- **`app/services/purchase_orders.py`**
  - NEW `remaining_by_line(db, lines)` — `{po_line_id: remaining}` where
    `remaining = net_amount − Σ counted-status linked bills`, clamped at zero,
    via a SINGLE `GROUP BY linked_commitment_id` query. `COUNTED_STATUSES`
    (Posted/Paid/Disputed) is **imported** from `budgets_reconciliation`, never
    re-declared, so it can never drift from the budget engine.
  - `_ser_line` / `serialise` gained an optional `remaining_by_line_id` kwarg
    (default `None`). `remaining_amount` was added to `_LINE_SENSITIVE`, so it
    is nulled for callers without `pos.view_sensitive` exactly like `net_amount`
    (sensitivity nulling takes precedence over the map). All ~9 existing
    `serialise()` callers are unchanged and emit `remaining_amount: null`
    (backward-compatible).
- **`app/routers/purchase_orders.py`** — `list_pos_by_budget_line_endpoint`
  now builds the remaining map (only for PO lines whose `budget_line_id` matches
  the route's `line_id`) and passes it into each `serialise()` call. Route
  signature, permission, Pattern-α 404 behaviour and response envelope are
  unchanged. No other endpoint computes the map → they still emit
  `remaining_amount: null`.

### Frontend — the force-the-choice picker

- **`src/hooks/purchaseOrders.js`** — NEW `usePurchaseOrdersForBudgetLine`,
  mirroring `useActualsForBudgetLine`'s shape (budget-line-keyed query, gated on
  the line id, 30s staleTime). Own query key so the create-form picker and the
  R6 expand grid don't collide.
- **`src/components/actuals/CommitmentLinePicker.jsx`** — NEW. Radio-group of
  eligible PO lines + a final **"No PO available"** option. Eligibility filtered
  **client-side**: parent PO status ∈ `PO_COMMITTED_STATUSES`
  (lock-step comment to the backend tuple) AND `line.budget_line_id ===
  budgetLineId`. Empty → auto-standalone + note. Fully-invoiced lines
  (`remaining "0.00"` AND fully receipted) shown greyed/disabled, not hidden.
  Money rendered via `formatMoney` (null → no "£null" suffix). The `?status=`
  server filter is deliberately **not** used (unverified array-param wire form).
- **`src/components/actuals/CreateActualSheet.jsx`** — renders the picker under
  the budget-line block; holds `linkedCommitmentId` + UI-only `isStandalone`
  locally (NOT RHF fields — `linked_commitment_id` is an optional uuid, seeding
  `""` would fail Zod). **Gate:** submit is blocked with an inline picker error
  ("Choose the purchase order this bill pays, or tick 'No PO available'.") until
  a PO line is chosen OR standalone is ticked. Budget-line change clears the
  choice + shows a transient reset note (guards the initial set). Standalone
  omits `linked_commitment_id`; a chosen line sends it. No other field, default,
  or strip logic touched.

## 4. Tests added

- **`backend/tests/test_po_line_remaining.py`** — the 10 spec'd cases (+1
  backward-compat): no bills→full; one Posted reduces; over-invoiced clamps to
  0; Draft/Void don't reduce; different-line bill doesn't reduce; serialiser
  null without sensitive / string with sensitive; api-level endpoint carries
  `remaining_amount` (and null for read-only); counted-status lock-step guard.
- **`frontend/.../CommitmentLinePicker.test.jsx`** — loading; empty→auto-
  standalone+note; populated remaining render; select line; select "No PO
  available"; fully-invoiced disabled; null money renders no "£null"; error
  surfacing.
- **`frontend/.../CreateActualSheet.commitment.test.jsx`** — gate blocks until a
  choice is made; standalone omits the link; PO-line sends it; budget-line
  change clears + shows the reset note.

## 5. Gate evidence

- **Backend (live Postgres):** `tests/test_po_line_remaining.py` → **11 passed**.
  Money-correctness, printed via the case assertions:
  - £10,000 line + £4,000 Posted linked bill → `remaining_amount = "6000.00"`
    (`test_02`); + a £7,000 Paid bill → over-invoiced → clamped `"0.00"`
    (`test_03`).
  - Serialised without `pos.view_sensitive` → `remaining_amount: null`
    (`test_07`); with it → the string figure (`test_08`).
  - `GET /v1/budget-lines/{id}/purchase-orders`: PO line net £200, £50 Posted
    linked bill → `remaining_amount "150.00"` for finance; `null` for read_only
    (`test_09`).
- **Backend regression (affected surface only):** PO api + PO unit +
  reconciliation = **76 passed**; actuals service + routes = **74 passed**. The
  serialiser/endpoint change broke nothing.
- **Frontend:** the two new RTL files → **13 passed**.
- **Preview:** `webpack compiled successfully`; the bill-entry sheet renders the
  new picker. The live click-through gate is the operator's.
- **No scope creep:** no migration, no permission, no enum; no change to actuals
  money maths, budget recompute, PO lifecycle, or `_validate_linked_commitment`.

### Environment note (Emergent container)

The Emergent container ships MongoDB, not Postgres, and its writable layer is
periodically wiped (it erased `/usr/lib/postgresql` mid-session). PG was stood
up locally (`postgresql-15` + `python -m app.bootstrap` to head `0050`) to run
the suites above; the full-suite **19-failure baseline** is the operator's CI
figure and is verified there, not reproduced in this ephemeral container. The
new tests are pure-session / standard RTL and run anywhere PG + Jest exist.

## 6. Forward hooks (logged, NOT built)

- **`B-OVER-PO-WARN`** — "bill exceeds its PO line remaining" warning, and a
  candidate notify-the-directors/finance trigger (over-PO → notify). This
  feature only *displays* remaining; it never blocks or warns on over-spend.
- **Edit-existing-bill PO re-link UI** — C1-front is the *create* path only. The
  patch path is already validated server-side; an edit-form picker is a separate
  future item.
