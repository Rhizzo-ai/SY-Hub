# Chat 29 — closing summary (2026-05-28)

Polish-pass-only chat. No new functional surface; one structural bug
discovered + repaired pre-PR, one polish mini-pack delivered + pushed,
one pre-existing CI portability problem surfaced for triage.

---

## §A. Headline

- **Auth-shape regression (operator → agent, 7 files).** A latent
  Chat-24 §R5 wiring choice combined with a Batch-2 `POApprovalsTab`
  copy-paste regression flipped the auth context shape that several
  newer components were reading. Operator caught it during local
  smoke; agent isolated the root cause across the 7 affected callers
  before any push. Repaired in-tree, verified by re-rendering each
  affected route, and rolled into **PR #19**.
- **PR #19 merged at `76528b3`.** Carries the auth-shape repair +
  Batch-2 settling work. Clean merge to `main`.
- **Polish-pass `r7-polish-mini-v2` — five items, all green.**
  - **R1** — `COMMITMENT_VERBS` dead-weight pruned (`issue` removed;
    surviving set `{void, sendBack, approve, close}`).
  - **R2** — `DEFERRED_TESTIDS === []` tautology in
    `POActionButtons.test.jsx` replaced with a self-anchoring snapshot
    over the live `data-testid="po-*-btn"` set plus a `describe.each`
    parametric existence check.
  - **R3** — `POEditDialog` `read_only` defence-in-depth short-circuit
    (inert early-return after all hooks; mirrors the backend's
    `read_only`-tier PATCH 403 even if the parent gate ever regresses).
  - **R4** — Approve/close `['budgets']` invalidation PIN tests
    (new file `frontend/src/hooks/__tests__/purchaseOrders.budgetsInvalidation.test.jsx`).
    Version-agnostic matcher; STOP-gated PIN-FAIL message; **destructive
    mutate confirmed** — commenting out the
    `qc.invalidateQueries({ queryKey: ['budgets'] })` line flipped
    both tests red with the expected dump
    (`{"queryKey":["purchase-order","po-1"]} | {"queryKey":["purchase-orders"]}`),
    restoring the line flipped both green.
  - **R5** — `.gitignore` appended `backend/var/inbound/` under a new
    `# Playwright AI-capture inbound fixtures (test artefacts)` block.
    Already-tracked PDFs left in place per pack instruction.
- **Auto-commits + push.** Platform-level auto-commit captured the
  polish work as two intermediate commits, **`243c841`** (R1 + R2 + R3
  + doc errata) and **`965b3ff`** (R4 + R5 + CHANGELOG). Operator
  reviewed the diff and pushed as **`c69f43e`**.
- **CI surfaced 17 backend test failures — pre-existing, NOT
  introduced by Chat 29.** Discovered during the polish-pass CI run;
  root-cause is hard-coded `/app/...` absolute paths in
  `test_audit_remediation_p0.py` + `_p1.py`. See §C below + Phase 2
  backlog item #15.

---

## §B. Test counts (literal)

**Backend pytest**

| Run                         | Passed | Xpassed | Failed |
|-----------------------------|-------:|--------:|-------:|
| Pre-Chat-29 (Chat 28 close) |    934 |       3 |      0 |
| Chat 29 close — local       |  1 004 |       3 |      0 |
| Chat 29 close — CI runner   |    987 |       3 |     17 |

The 17 CI-only failures are all under
`backend/tests/test_audit_remediation_p0.py` + `_p1.py` — root cause
is path portability, not regression. Local pytest stays green.

**Frontend Jest** (literal `yarn craco test --watchAll=false`
captured at Chat 29 close):

```
Test Suites: 61 passed, 61 total
Tests:       405 passed, 405 total
Snapshots:   1 passed, 1 total
Time:        34.386 s
```

Trajectory:

| Run                              | Passing |
|----------------------------------|--------:|
| Pre-Chat-29 (Chat 28 close)      |     387 |
| Post PR #19 merge (`76528b3`)    |     388 |
| Post polish-pass (`c69f43e`)     | **405** |

Polish-pass delta = **+17** (R2 snapshot + 15 parametric per-testid
checks + R3 read-only short-circuit pin + R4's two PIN tests; some
existing suites also re-counted under the new snapshot machinery).

**R4 destructive mutate proof — literal output:**

```
FAIL src/hooks/__tests__/purchaseOrders.budgetsInvalidation.test.jsx
  ✕ approve: invalidates a query-key containing "budgets" on settle (16 ms)
  ✕ close: invalidates a query-key containing "budgets" on settle (9 ms)

  ● approve …
    [R7-polish §R4 PIN FAIL] approve did not invalidate any queryKey
    containing "budgets". invalidateQueries call log:
    {"queryKey":["purchase-order","po-1"]} | {"queryKey":["purchase-orders"]}

  ● close …
    [R7-polish §R4 PIN FAIL] close did not invalidate any queryKey
    containing "budgets". invalidateQueries call log:
    {"queryKey":["purchase-order","po-1"]} | {"queryKey":["purchase-orders"]}

Tests: 2 failed, 2 total
```

After restoring the `qc.invalidateQueries({ queryKey: ['budgets'] })`
line:

```
PASS src/hooks/__tests__/purchaseOrders.budgetsInvalidation.test.jsx
  ✓ approve: invalidates a query-key containing "budgets" on settle (16 ms)
  ✓ close: invalidates a query-key containing "budgets" on settle (8 ms)

Tests: 2 passed, 2 total
```

`git status --short` after restore: empty. Working tree clean.

---

## §C. CI failures (17) — root-cause + standing rule

**Symptom.** On the GitHub Actions runner, 17 tests in
`backend/tests/test_audit_remediation_p0.py` + `_p1.py` fail with
`FileNotFoundError` cascades (and downstream auth-401 noise from the
fixtures that depended on them).

**Root cause.** Each affected test opens repo source files via a
hard-coded **absolute** path:

```python
# backend/tests/test_audit_remediation_p0.py:135
path = "/app/backend/app/routers/appraisals.py"
with open(path) as f:
    lines = f.readlines()
```

…and the same shape at lines 634 (`po_receipts.py`), 663
(`auth/tokens.py`), 895 (`auth/routers/auth.py`) — plus the partner
file `test_audit_remediation_p1.py`. The path
`/app/backend/...` only resolves inside Emergent's container (where
the repo is mounted at `/app`). On the GitHub Actions runner the
checkout lives at `/home/runner/work/SY-Hub/SY-Hub/`, so every
`open(path)` raises and the tests fail.

**Not a Chat-29 regression.** The two test files were added in
commits **`020a8e3`** (the audit-remediation P0 batch, pre-Chat-28)
and **`700f184`** (the auto-commit that followed). CI has been red on
that backend job since those landed — Chat 29 simply ran CI for the
first time in a while and made the existing red surface visible.

**Fix shape (deferred, ~30 min, backend-test-only).** Replace each
absolute literal with a `__file__`-relative resolution:

```python
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]   # backend/tests/ → /app
path = REPO_ROOT / "app" / "routers" / "appraisals.py"
```

Tracked as Phase 2 backlog **#15** (see `docs/SY_Hub_Phase2_Backlog.md`).
Owner deferred to the Track 2 wrap-up audit (Chat 30+) with MD /
Louise, or to a Claude Code checkpoint pass — not blocking, because
local pytest has caught real regressions throughout Tracks 2 + 3.

---

## §D. Standing-rules codifications added this chat

These are process invariants the chat surfaced; they belong in the
agent-handoff contract going forward.

1. **The platform auto-commit hook can fire between the handoff-summary
   write and session end.** Chat 29's handoff summary stated R4 + R5
   were "NOT STARTED / IN PROGRESS" — but auto-commit **`965b3ff`**
   had already captured both before the session closed.
   **Standing rule:** trust `git log --oneline` over the prose
   handoff. Always run `git status --short` + `git log --oneline
   ${last_known_merge}..HEAD` before believing a handoff that says
   "X was not yet done."

2. **The PR diff at push time MUST be eyeballed for stray files.**
   PR #19 carried the 9 intended files **plus** 9 unintended inbound
   PDF fixtures under `backend/var/inbound/` and a benign
   `.emergent/emergent.yml` job-id rotation. R5 above prevents
   recurrence for the inbound fixtures; the `.emergent` yml drift is
   benign noise but the eyeball-the-diff rule stands.

3. **Self-report claims of "all N items done" must be verified
   per-item before push.** On the first polish-pass run the agent
   self-reported R4 + R5 as complete but had substituted markdown-doc
   edits in their place. The substitution was caught at the
   diff-review stage. **Standing rule:** for every item the
   self-report marks "done," the operator (or a follow-up tool call)
   resolves the literal artefact — the test file's contents, the
   `.gitignore` diff, the destructive-mutate output — before push.

---

## §E. Carry-forward to Chat 30

See the Chat 30 opener artefact (produced by Claude separately).
Headline carry-forwards from here:

- **Phase 2 backlog #15** — CI path portability fix (above).
- **PR-diff eyeball protocol** — formalise as a pre-push checklist
  item in `agents/agents.md` or the operator runbook.
- **No outstanding code work from the polish pack.** Polish-pass is
  fully discharged; PIN tests + `.gitignore` rule are in place to
  prevent silent regressions on `COMMITMENT_VERBS` shape +
  inbound-fixture leakage.

---

## §F. Files touched in Chat 29 (post PR #19 merge)

Auto-committed in **`243c841`** + **`965b3ff`**, pushed as **`c69f43e`**:

```
.github/workflows/ci.yml                                   (2)
CHANGELOG.md                                              (54)
backend/tests/test_audit_log.py                            (2)
backend/tests/test_audit_remediation.py                    (2)
backend/tests/test_audit_remediation_p0.py                 (2)
backend/tests/test_audit_remediation_p1.py                 (2)
backend/tests/test_auth_rbac.py                            (2)
backend/tests/test_c3_governance_smoke.py                  (2)
backend/tests/test_entities_api.py                         (2)
backend/tests/test_mfa.py                                  (2)
backend/tests/test_notifications.py                        (2)
backend/tests/test_password_complexity.py                  (2)
backend/tests/test_reference_data.py                       (2)
backend/tests/test_retro_wires.py                          (2)
backend/tests/test_scheduler_jobs.py                       (2)
backend/tests/test_sessions_history_reset.py               (2)
backend/tests/test_system_config.py                        (2)
backend/tests/test_user_edit.py                            (2)
docs/SY_Hub_2.3_Checkpoint3_Handoff.md                     (6)
docs/chat-summaries/chat-18-closing.md                     (2)
docs/chat-summaries/chat-26-closing.md                    (14)
frontend/e2e/helpers/api.ts                                (2)
frontend/e2e/helpers/login.ts                              (2)
frontend/playwright.config.ts                              (2)
frontend/src/components/po/POEditDialog.jsx               (19)
frontend/src/components/po/__tests__/POActionButtons.test.jsx           (47)
frontend/src/components/po/__tests__/__snapshots__/POActionButtons.test.jsx.snap (21)
frontend/src/hooks/__tests__/purchaseOrders.budgetsInvalidation.test.jsx (131, new)
frontend/src/hooks/__tests__/purchaseOrders.optimistic.test.jsx          (2)
frontend/src/hooks/purchaseOrders.js                                    (16)
.gitignore                                                              (3)
[+ this chat-summary file, the Phase 2 backlog #15 append, and a
 CHANGELOG §"Chat 29 close — CI findings" addendum land in the
 working tree at Chat 29 close, awaiting operator push.]
```
