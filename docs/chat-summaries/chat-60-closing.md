# Chat 60 — Closing Summary

**Build Pack:** B107 — Cost-Code-First Commercial Frontend
**Depends on:** B105/B106 backend (Chat 59, gate-cleared on `main`)
**Scope:** Frontend only. No backend file, no migration, no Python change.
**Backlog:** `docs/SY_Hub_Phase2_Backlog.md` left untouched (operator-only).

---

## 1. What was built

Frontend companion to the B105/B106 money path. Three pillars, all to the
pack:

1. **PO create form → cost-code-first.** The per-line budget-line dropdown is
   replaced by a reused, now-searchable `CostCodePicker`. Each line sends
   `cost_code_id` (the underlying `cost_codes.id`, §0.4) and never
   `budget_line_id`; `cost_code_subcategory_id` is always `null` for B107.

2. **Budget-grid unbudgeted pills + gated director clear.** A display-only
   `UnbudgetedPill` mirrors the server floor gate (RED "Sign-off required"
   at/over £1,000 committed, AMBER "Unbudgeted" below), on desktop and mobile.
   A `budgets.clear_unbudgeted`-gated `ClearUnbudgetedDialog` posts the
   body-less `clear-unbudgeted` endpoint and invalidates the grid.

3. **Structured submit-error surface.** `POSubmitErrorPanel` branches on
   `detail.type` for the three B105/B106 wire shapes
   (`unbudgeted_ack_required`, `po_line_incomplete`, `budget_line_race` with a
   one-click retry). No object is ever `JSON.stringify`d at the user.

Supporting wiring: `useUnbudgetedAckFloor` (config hook), `useClearUnbudgeted`
+ `clearUnbudgeted` (api) + `canClearUnbudgeted` (capability), and a required
zod-schema fix (`is_unbudgeted` / `unbudgeted_cleared_at` /
`unbudgeted_awaiting_ack` were being stripped from `BudgetLineSchema`).

## 2. Variant decisions (pack §7.3 / §7.4 / §2)

- **§7.3 subcategory:** cost-code-only — always sends `null`.
- **§7.4 mint hint:** FULL variant — the form fetches the budget's existing
  lines and shows a precise per-line "will mint (floor £X)" hint; generic
  fallback when the budget isn't loadable.
- **§2 floor:** sourced live from `budget.unbudgeted_ack_floor_gbp` (£1,000);
  the constant is a fallback only.

## 3. Live-fix follow-ups (surfaced during §10)

- **FIX 1 — ResizeObserver overlay.** The Popover/cmdk combobox tripped the
  benign "ResizeObserver loop…" notice, which CRA escalated to a red overlay.
  `lib/resizeObserverFix.js` wraps the observer callback in
  `requestAnimationFrame` (root cause) plus a scoped capture-phase catch of
  only the two benign RO strings. Not a global error swallow.
- **FIX 2 — budget dropdown.** The free-text "Budget id" paste field (a 422
  footgun) is replaced by a `<select>` from `useProjectBudgets`, with
  auto-select of a single / current-Active budget.
- **FIX 3 — blank-qty £0 line (§10.5).** `validatePoLines` blocks Create draft
  when quantity is blank/≤0 or unit price is blank/negative; a blank qty is
  MISSING, never coerced to 0. Backend `po_line_incomplete` path stays as the
  server net.

## 4. Verification status

**Live-verified on the preview (`test-pm`, no MFA):**

- PO create form renders cost-code-first ("Cost code" column, no budget-line
  dropdown).
- Cost-code picker: type-to-search filters on code + name; selecting populates
  the line; each line has an independent picker. No error overlay (FIX 1).
- Budget dropdown auto-selects the project's budget (FIX 2).
- Blank / zero quantity is blocked on the form with a friendly message; a
  complete line (qty 1 × £100) creates a draft → PO detail page (FIX 3).
- PO draft creation succeeds once a `po` number prefix exists.

**NOT yet live-verified (component-tested only) — eyeball §10.6–10.9:**

- Budget-grid AMBER (below floor) and RED (over floor) pills.
- Director "Clear (sign off)" action clearing the pill.
- Permission-gate negative (pill shows, no clear button for non-holders).
- Mobile pills.

Reason: the preview environment recycled frequently (re-running the R7 seed,
recreating the Active budget and wiping seeded suppliers / cost-code mappings /
PO prefix every few minutes), so the grid scenario couldn't be held stable long
enough to finish 6–9. These pass component tests; they are to be eyeballed on a
stable preview after this push.

**Environment / data notes for the next session:**

- Construction-scope users (e.g. `test-pm`) currently see **no** budget lines
  on this project (no `cost_code_sections.included_in_construction_scope=true`),
  so the grid pills must be eyeballed with a **full-scope** account.
- The only `clear_unbudgeted` holders (super_admin, director) AND finance are
  **MFA-enforced** (`MFA_ENFORCED_ROLES`), so the grid/clear checks require a
  one-time TOTP enrolment. Suggested: `test-director` (clear) and `test-finance`
  (negative gate — full scope, no clear perm).

## 5. Tests

- New suites: `UnbudgetedPill`, `poPayload` (+ `validatePoLines`),
  `POSubmitErrorPanel`, `ClearUnbudgetedDialog`,
  `BudgetGridColumns.unbudgeted`, `POLineEditor`; `CostCodePicker.test.jsx`
  extended (search + value emission).
- Three grid suites had `useClearUnbudgeted` added to their `@/hooks/budgets`
  mocks.
- FE suite: **866 → 891 (+25), 890 pass / 1 fail.** The single failure is the
  pre-existing `pages/admin/__tests__/PackagesList.test.jsx` (unrelated).
  Lint clean.

## 6. Guardrails honoured

- Frontend only — zero backend / migration / Python changes.
- `docs/SY_Hub_Phase2_Backlog.md` untouched.
- No git writes by the agent (push via "Save to GitHub").

## 7. Out of scope / flagged (unchanged from the pack)

- Package-line cost-code-first UI → B107b.
- AI quote→PO cost-code suggestion → proposed B107c.
- Notification wiring → B112 (trigger comments left in code at the
  ack-required surface and the clear-success handler).
- Subcategory picker → deferred (§7.3).
