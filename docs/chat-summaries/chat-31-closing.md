# Chat 31 — Closing Summary

**Date:** 2026-05-31
**Track:** 2 (Commercial Engine) — director-review follow-through
**Outcome:** MD + Louise Track 2 review (2026-05-28) processed. Decision 1
shipped end-to-end as Build Pack 2.4C. Decision 2 deferred. Backlog
expanded by five items (B43–B47). Chat 32 picks the next Build Pack.

---

## 1. What this chat did

Chat 31 was a director-review **follow-through** session: take the two
named decisions from the MD + Louise Track 2 review pack (held after
Chat 30 closed Track 2 / R7), ship the one that was ready, and log the
other to the backlog. No new product features were specced in this chat
beyond what the review explicitly approved.

The two decisions on the table were:

- **Decision 1 — Backlog #12 / Segregation of Duties on budget
  approval.** Steer from the review: a budget's creator must not
  self-approve at or above a configurable value threshold; below the
  threshold, self-serve is fine. Build Pack 2.4C drafted, approved,
  and shipped this chat.
- **Decision 2 — B19 / spend with no budget line.** Steer from the
  review: flag on the cost itself, require named director sign-off,
  log who and when. **Deferred** to the Actuals work stream
  (commitments / actuals already own the cost-line linkage path);
  tracked under B19 in `docs/SY_Hub_Phase2_Backlog.md`.

## 2. Decision 1 shipped — Build Pack 2.4C (Budget Approval Controls)

R1–R5 implemented verbatim per Build Pack:

- **R1 (config).** New `system_config` row
  `budget.self_approval_threshold_gbp` (Decimal, default £10,000.00,
  category Budget, super_admin-editable via existing
  `system_config.admin` permission). Typed getter
  `get_budget_self_approval_threshold(db)` with in-code fallback to the
  default if the row is absent.
- **R2 (`activate()` guard).** Side-effect-free local-variable total
  `= Σ(original_budget + approved_changes)` across freshly-loaded
  `BudgetLine` rows; no `recompute_summary`, no read of cached
  `budgets.total_budget`. Comparison `total >= threshold` (£10k itself
  is blocked). NULL `created_by_user_id` fails open. Super-admin
  creators are **not** exempt.
- **R2.3 (exception + mapping).** New `BudgetSelfApprovalError`
  distinct from `BudgetStateError`. Router maps it to **HTTP 403**
  (authorisation refusal); `BudgetStateError` continues to map to 409
  (state-machine violation).
- **R5 (tests).** Eight new tests in `TestBudgetSelfApprovalGuard`
  covering boundary (`==threshold`), above-threshold, below-threshold,
  other-user activation, super-admin not exempt, service raises the
  new error (asserted **not** `BudgetStateError`), and config getter
  reads-DB / falls-back. NULL-creator fail-open guarded by source-level
  inspection because `budgets.created_by_user_id` is `NOT NULL` in
  the current schema (the defensive in-code check is retained for any
  future migration that drops the NOT NULL).

**Test outcome.** WARM-DB 2nd-run pytest:
**`1035 passed, 2 xfailed, 1 xpassed, 2 warnings in 165.12s`.** Zero
regressions in legacy lifecycle tests (those use £250k seeded budgets
with admin self-activation — handled via a module-scoped
`_bump_self_approval_threshold` autouse fixture in the three affected
test modules that only *raises* the threshold and restores on
teardown). Seed reconciliation count 39 → 40.

**Commits.**
- `199c857` — R1–R5 nine-file change (zero noise).
- `9871219` — test-hygiene fix: tightened `_isolate_threshold` teardown
  assertion to `== 200` (was `in (200, 422)`; would have masked a
  silently-failed restore and could have leaked a low threshold into
  the next test).
- **CI #35 GREEN** post-push.

**Deviations from the spec (logged in `CHANGELOG.md`).**
- Config key renamed underscored → dotted (`budget.self_approval_threshold_gbp`)
  at the R1 STOP gate to match existing budget-key convention. User-
  approved in chat.
- Pre-2.4C auto-commit `352eb08` (made by the platform *before* 2.4C
  R1 began) swept hostname-rename / `scripts/seed_r7_*` /
  `test_reports/helpers/*` noise onto local main. Operator decision:
  pushed as-is. Cleanup tracked as **B47**.

## 3. Decision 2 deferred — B19

The "spend with no budget line" flow needs the actuals / commitments
linkage path before the director-sign-off ergonomics can be implemented
sensibly. Lifted into the backlog as **B19** (already present from the
review pack) with the agreed steer ("flag on the cost itself, require
named director sign-off, log who and when") locked in. To be picked up
when the Actuals work stream resumes.

## 4. Backlog growth — B43 through B47

Five items added this chat:

- **B43** — Stage 2 per-role / per-user budget approval limits
  (current 2.4C is Stage 1: single global threshold).
- **B44** — Front-end admin UI for editing `system_config` (currently
  edit only via PUT `/system-config/{key}`).
- **B45** — Front-end message for the new HTTP 403 self-approval
  refusal (so PMs see a guided "ask a Director" prompt instead of a
  raw error).
- **B46** — `/budgets/{id}/activate-preview` endpoint that runs the
  SoD guard without mutating status (UX warm-up before clicking
  Activate; suggested in the chat 32 enhancement note).
- **B47** — Repo cleanup: remove the hostname-rename /
  `scripts/seed_r7_*` / `test_reports/helpers/*` noise files that
  auto-commit `352eb08` swept onto main.

(B43, B44, B45 were already named in the 2.4C Build Pack as Stage-2
deferrals; logged here for traceability. B46 and B47 are new this
chat.)

## 5. State at close

- **CI:** GREEN (CI #35, the 2.4C push).
- **Backend:** 1035 tests passed (was 1027 at Chat 30 close; +8 from
  `TestBudgetSelfApprovalGuard`), 1 xpassed, 2 xfailed.
- **Frontend:** 405 Jest passed (unchanged — 2.4C is backend-only).
- **Permissions:** 102. Roles: 10. (No new permission — reuses
  existing `system_config.admin`.)
- **system_config seed count:** 40 (was 39).
- **origin/main HEAD:** post-2.4C push (see commit SHA pasted in the
  chat after Save-to-GitHub).

## 6. Saved to repo this chat

- `backend/app/services/budgets.py` — `activate()` guard.
- `backend/app/services/budget_errors.py` — `BudgetSelfApprovalError`.
- `backend/app/services/system_config.py` — getter + key constant.
- `backend/app/seed_system_config.py` — seed row.
- `backend/app/routers/budgets.py` — 403 mapping + `_state_change`
  catch.
- `backend/tests/test_budgets.py` — `TestBudgetSelfApprovalGuard` (8
  tests) + module-scope threshold-bump fixture.
- `backend/tests/test_actuals_routes.py`,
  `backend/tests/test_budgets_line_delete.py` — module-scope
  threshold-bump fixtures (legacy £250k self-activation modules).
- `backend/tests/test_system_config.py` — seed count 39 → 40.
- `CHANGELOG.md` — 2.4C entry.
- `memory/PRD.md` — 2.4C entry.
- `docs/chat-summaries/chat-31-closing.md` — this file.

## 7. Carry-forward into Chat 32

- **B43, B44, B45, B46, B47** as above.
- All Chat 30 carry-forwards still open: R7.5 `q` filter FE wiring,
  `backend/var/inbound/*.pdf` cleanup, Chat 27 audit-remediation P2
  items, `test_projects.py` FK cleanup (root of the warm-DB first-run
  errors — still real, still costing a re-run every time).
- **Chat 32 picks the next Build Pack** — candidates from the user's
  priority list: 2.5D (cost dashboard), 2.6 (subcontractor),
  2.7 (subcontracts + variations), 2.8 (multi-status polish), or
  any B43–B47 promoted into a Build Pack.
