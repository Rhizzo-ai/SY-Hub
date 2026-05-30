# R7 — Track 2 Commercial Engine: Build-Complete Declaration

**Status:** CLOSED — pod pre-flight confirmed 2026-05-28 (Chat 30)
**Date:** 2026-05-28
**Closing commit:** `d81bbef` (origin/main HEAD = Chat 29 doc push `c5cbd67`
+ benign `.emergent/emergent.yml` tweak `d81bbef`; no source code above `c69f43e`)
**Issued by:** Chat 30 (triage), on the verified pod evidence below.

---

## 1. What R7 / Track 2 was

Track 2 (Commercial Engine) is the financial-control core of SY-Hub:
entities → appraisals → budgets → purchase orders / commitments → actuals,
with the governance and audit layer threading through all of it. R7 is the
final milestone of that track — Purchase Orders and the commitment/approval
flow that closes the loop between a budgeted line and committed spend.

## 2. What is shipped and verified

| Area | State at close | Evidence |
|---|---|---|
| Appraisals (SDLT/RLV/finance engines) | Live, governed (2.3 C1–C3) | pytest, E2E |
| Budgets core (backend, 2.4A) | Live — 14 endpoints, migration `0024` | pytest |
| Budgets frontend (2.4B-i) | Live — grid, drawer, lock/close, versioning | Jest |
| Purchase Orders + approvals (R7) | Live — create/approve/close/void/send-back | pytest + Jest + Playwright |
| Commitment recompute on PO state change | Live — DB trigger `fn_budget_line_recompute_commitments` | pytest |
| Auth-shape integrity across PO surfaces | Repaired (PR #19), regression-pinned | `AuthContext.shape.test.jsx` |
| `['budgets']` cache invalidation on PO settle | Pinned, destructive-mutate proven | `purchaseOrders.budgetsInvalidation.test.jsx` |

**Test posture at close (verified on pod, Chat 30 pre-flight):**
- Backend pytest: **1027 passed / 3 xpassed / 0 failed** — **1030 distinct
  tests collected** (the +70 vs Chat 28's 934 is REAL distinct test
  functions, confirmed via `pytest --collect-only`, not a counting artefact)
- Frontend Jest: **405 passed**, 1 snapshot
- Playwright: 18 specs written
- Permissions: 102 · Roles: 10 · Alembic head: `0034_audit_sendback`

**Polish pass `r7-polish-mini-v2` fully discharged** (Chat 29): dead-verb
prune, tautology→snapshot guard, read-only defence-in-depth, budgets-
invalidation PIN tests, inbound-fixture `.gitignore`. No code work remains.

## 3. Known, accepted, NON-blocking carry-outs

These are deliberately deferred — they do **not** block R7-close. They are
already logged in `docs/SY_Hub_Phase2_Backlog.md`:

- **#15 — CI path portability.** 17 backend tests fail on the GitHub
  Actions runner (not locally) due to hard-coded `/app/...` paths in the
  audit-remediation test files. Pre-existing since `020a8e3`, ~10 commits
  back. ~30-min mechanical fix. *Local pytest is green; this is a CI-runner
  artefact, not a product defect.* **Recommend fixing before the MD/Louise
  walkthrough** so CI is green on the day — see audit pack §"Pre-meeting".
- **#12 — Author-can-approve separation.** Today a PM can activate a budget
  they created themselves. Explicitly flagged for the MD/Louise review.
  **This is a decision the audit asks for — not a defect.**
- **B19 — Unbudgeted-cost director sign-off route.** Design pass needed;
  explicitly blocked on this Track-2 wrap review. **Also a decision the
  audit asks for.**
- Actuals/commitments service depth, cash-flow time-phasing, idempotency
  keys, scheduler infra, Xero hooks — all Track 5/6 scope, untouched by
  design.

## 4. Why R7 is closeable now

The work R7 set out to do is done and guarded by tests that fail loudly if
someone breaks them. The open items above are either (a) a CI-runner
hygiene fix that doesn't touch the product, or (b) business-process
decisions that *require* MD and Louise — which is precisely the next gate.
Holding R7 open for those would be holding it open for the very meeting
it's the prerequisite to.

---

**Footer — close CONFIRMED.** Chat 30 pod pre-flight (2026-05-28)
verified: clean working tree; top commit of `origin/main` is the Chat 29
doc push (`c5cbd67`) plus a benign one-line `.emergent/emergent.yml` tweak
(`d81bbef`) — no source code landed above `c69f43e`; `pytest --collect-only`
shows **1030 distinct tests** (1027 passed / 3 xpassed), proving the +70 vs
Chat 28 is real; frontend **405 passed**. R7 / Track 2 build is closed.
