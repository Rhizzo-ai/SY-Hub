# Chat 64 — Closing Summary: C1-front, Force-the-Choice Bill-Entry UI

**Type:** Frontend-led, with ONE small additive read-only backend field.
**Audit reference:** Full-platform audit **2026-06-19, finding C1** (budget
double-counts committed cost). C1-front is the UI partner to **C1-back** (Chat
63, backend + backfill) and closes finding C1 end-to-end.
**Decisions locked by:** Rhys (operator).
**Migration:** NONE. The new field is derived at serialisation time, not stored.
Alembic head unchanged at **`0050_backfill_invoiced_commit`** (143 permissions,
10 roles).
**Backlog:** `docs/SY_Hub_Phase2_Backlog.md` left untouched (operator-only).

---

## 1. Why this existed

C1-back fixed the budget double-count by deriving "invoiced against commitment"
fresh from bills whose `linked_commitment_id` points at a `PurchaseOrderLine` on
the same budget line, and enforces that link on create AND update (422
`CommitmentLinkError`). But the bill-entry form never *set*
`linked_commitment_id` — the schema accepted it, the UI ignored it — so every
manually-entered bill was implicitly "standalone" and Louise had no way to tie a
bill to the PO it pays down. C1-front makes that choice explicit and mandatory.

## 2. The four locked operator decisions (all built)

1. **Show remaining per PO line** — each eligible PO-line option displays
   "£X remaining of £Y" (requires the additive backend field, §3).
2. **Standalone wording = exactly "No PO available."**
3. **Budget line with no open PO lines → auto-standalone + note** (no tick
   forced; the submit gate is satisfied automatically).
4. **Changing the budget line after a PO line was picked → clears the choice**
   and shows a brief reset note.

## 3. What changed

### Backend — derived, read-only `remaining_amount` on PO lines
- `app/services/purchase_orders.py`: new `remaining_by_line(db, lines)` —
  `remaining = po_line.net_amount − Σ(linked bills in COUNTED_STATUSES)`,
  clamped at zero, via a single `GROUP BY linked_commitment_id` query.
  `COUNTED_STATUSES` (Posted/Paid/Disputed) is **imported** from
  `budgets_reconciliation`, never re-declared — so it can never drift from the
  budget engine (asserted by a test).
- `_ser_line` / `serialise` gained an optional `remaining_by_line_id` kwarg
  (default `None`); `remaining_amount` was added to `_LINE_SENSITIVE`, so it is
  nulled for callers without `pos.view_sensitive` exactly like `net_amount`. All
  ~9 existing `serialise()` callers are unchanged and emit
  `remaining_amount: null` (backward-compatible).
- `routers/purchase_orders.py`: `GET /v1/budget-lines/{line_id}/purchase-orders`
  builds the remaining map (only for PO lines on the route's `line_id`) and
  threads it into each `serialise()` call. Route signature, permission,
  Pattern-α 404 and response envelope unchanged. No other endpoint computes the
  map → they still emit `remaining_amount: null`.

### Frontend — the force-the-choice picker
- `src/hooks/purchaseOrders.js`: new `usePurchaseOrdersForBudgetLine` (mirrors
  `useActualsForBudgetLine`'s budget-line-keyed, gated, 30s-stale shape).
- `src/components/actuals/CommitmentLinePicker.jsx`: radio group of eligible PO
  lines (parent PO status ∈ `PO_COMMITTED_STATUSES` AND
  `line.budget_line_id === budgetLineId`) + a final **"No PO available"** option.
  Empty → auto-standalone + note. Fully-invoiced lines (`remaining "0.00"` AND
  fully receipted) render greyed/disabled, not hidden. Money via `formatMoney`
  (null → no "£null" suffix).
- `src/components/actuals/CreateActualSheet.jsx`: holds `linkedCommitmentId` +
  UI-only `isStandalone` locally (NOT RHF fields — `linked_commitment_id` is an
  optional uuid, seeding `""` would fail Zod). Submit is **blocked** with an
  inline picker error until a PO line is chosen OR standalone is ticked. Budget-
  line change clears the choice + shows a transient reset note. Standalone omits
  `linked_commitment_id`; a chosen line sends it. **No schema change** —
  `linked_commitment_id` was already optional on both create and update schemas.

## 4. Design-first discipline — two real Build-Pack defects caught before build

1. **`serialise()` has no DB session.** The Build Pack placed the remaining
   computation inside the serialiser. Corrected: compute the map once in the
   endpoint (which *has* the session, in a single aggregated query) and thread
   it in via `remaining_by_line_id`.
2. **Unverified array query-param.** The pack proposed a `?status=` array filter
   to narrow POs server-side, but the wire form of an array param is unverified
   in this stack (no `paramsSerializer` in `api.js`). Used client-side filtering
   on `PO_COMMITTED_STATUSES` instead — same result, no guesswork on the wire.

## 5. Tests
- Backend `backend/tests/test_po_line_remaining.py` — **11**: no bills→full; one
  Posted reduces; over-invoiced clamps to 0; Draft/Void don't reduce; different-
  line bill doesn't reduce; serialiser null without sensitive / string with
  sensitive; api-level endpoint carries `remaining_amount` (and null for read-
  only); `COUNTED_STATUSES` lock-step guard.
- Frontend **13**: `CommitmentLinePicker.test.jsx` (9) +
  `CreateActualSheet.commitment.test.jsx` (4) — loading/empty/populated/select/
  standalone/fully-invoiced/null-money/error; the submit gate; standalone omits
  the link; PO-line sends it; budget-line-change reset note.

## 6. Gate evidence
- **Automated browser pre-check: 7/7.** Gate blocks without a choice (inline
  error verbatim); "£6,000.00 remaining of £10,000.00" matches backend;
  standalone submit POST omits `linked_commitment_id`, PO-line submit POST sends
  the chosen line id; Landscaping (no POs) shows the standalone note and submits;
  budget-line change shows the reset note + clears the choice; the fully-invoiced
  line is greyed/disabled and unselectable.
- **Operator live eyeball: passed.**
- Backend money proofs (Postgres): £10k − £4k Posted → `"6000.00"`; +£7k Paid →
  over-invoiced → clamped `"0.00"`; null without `pos.view_sensitive`; endpoint
  £200 line − £50 Posted → `"150.00"`, read-only → `null`.

## 7. Verified on origin/main
- Feature files present (backend service/router/test; frontend hook/picker/
  CreateActualSheet wiring + the two RTL files).
- The one-off demo seeder used for the live click-through did **not** land in the
  repo.
- `project_manager` still correctly lacks `budgets.view_sensitive` — the
  **preview-only** RBAC grant (needed so the only headless-capable test user
  could see budget lines, since full-budget-scope roles are MFA-enforced) did
  **not** escape to the codebase. It lived solely in the throwaway preview DB.

## 8. Forward hooks (logged, NOT built)
- **`B-OVER-PO-WARN`** — "bill exceeds its PO line remaining" warning + a
  candidate notify-the-PM/director trigger. C1-front only *displays* remaining;
  it never blocks or warns on over-spend.
- **Edit-existing-bill PO re-link UI** — C1-front is the *create* path only; the
  patch path is already validated server-side.
- **`B-BUDGET-DRILLDOWN`** — budget line → underlying POs/bills drill-down;
  design-TBD, likely folds into BudgetLinesGrid v2.

## 9. Critical-fix scoreboard (full-platform audit, 2026-06-19)
| # | Critical finding | Status |
|---|------------------|--------|
| **C1** | Budget double-counts committed cost | **CLOSED** — C1-back (Chat 63, backend + backfill) + C1-front (Chat 64, UI) |
| **C2** | Illusory budget freeze (`clear_unbudgeted`) | **CLOSED** — Chat 63 (B-variant) |
| **C3** | Corporate SDLT flat-rate undercharge | **CLOSED** — C3 |
| **C4** | *Last remaining critical from the 2026-06-19 audit* | **OPEN — next** |

With C1 closed, **C4 is the last remaining critical** from the audit.
