# Chat 37 closing — Build Pack 2.6-FE-fix (BCR Workflow Defect Fixes)

**Branch strategy:** push-to-main (frontend-only defect pass; no migrations).
**Build pack:** `BuildPack_2_6_FE_fix_BCR_defects.md`.
**Type:** frontend-only, defect fixes. NO backend changes, NO scope expansion.
**Origin:** Three bugs found in operator manual two-user click-through of the
BCR workflow shipped in Chat 36 (commit `52a4288`). The Playwright suite did
not catch them — stubs passed, real UI failed. This pack fixes exactly those
three. Nothing else.
**Backend:** FROZEN at alembic head `0038_sc_valuations`, 129 permissions
(re-verified post-fix, `git diff --stat backend/` empty).

---

## §R0.1 Pre-flight (reported BEFORE coding)

All pre-flight checks green:
- `scripts/provision_postgres.sh`, `pip install`, bootstrap (rc=0),
  `yarn install` — all clean.
- Alembic HEAD verified at `0038_sc_valuations` (unchanged from Chat 36).
- Permission catalogue verified at **129** via
  `len(PERMISSION_CATALOGUE)` from `seed_rbac.py`.
- **FE test baseline recorded BEFORE any patch:** 405 tests passing
  across 62 suites.

---

## §R0.2 Root-cause report (STOP gate honoured)

Per the Build Pack contract, NO code was patched until the root cause of
ALL three bugs PLUS the Bug 3 label-fallback decision were reported to
the operator AND confirmed.

### Bug 1 — CRITICAL — `EditBCRDialog` ReferenceError on open

**Symptom (operator-reproduced):** Clicking into a created BCR
white-screened with `ReferenceError: DialogDescription is not defined`
thrown from `EditBCRDialog` (stack: `budgets.chunk.js` → `EditBCRDialog`).
BCRs could be created but never opened, submitted, approved, or applied —
the core workflow was unreachable end-to-end.

**Root cause:** `frontend/src/pages/projects/BudgetChangeDetail.jsx`
imported only `Dialog, DialogContent, DialogFooter, DialogHeader,
DialogTitle` from `@/components/ui/dialog` at line 23, but
`<DialogDescription>` was used inside the `EditBCRDialog` JSX at
line 348. A bog-standard missing named import.

**Build-pack audit of every budgetChanges dialog** (per §R0.2 Bug 1
instructions — "fix ALL of them, not just the one in the stack trace"):
- `CreateBudgetChangeDialog.jsx` line 22 — `DialogDescription` imported ✓
- `BCRRejectDialog.jsx` line 11 — `DialogDescription` imported ✓
- `BCRActionButtons.jsx` line 28 (withdraw confirm modal) —
  `DialogDescription` imported ✓
- `BudgetChangeDetail.jsx` line 23 (`EditBCRDialog`) —
  `DialogDescription` **MISSING** ✗

**Only the one file was broken.** The Chat 36 self-report's claim of a
"DialogDescription a11y fix applied + verified" did cover the first
three but did **not** cover `EditBCRDialog` — likely because the dialog
is defined inside the same file as the page component and was missed in
the per-file pass.

### Bug 2 — HIGH — negative deltas do not register

**Symptom (operator-reproduced):** In "New budget change" → Lines →
Delta (£), typing a negative (e.g. `-40000`) DISPLAYED the minus in the
field, but on submit/validation the value was treated as positive — the
running Net never went negative and a Transfer could not be constructed
to net to £0. Two of the three change types (Transfer and
ContingencyDrawdown, both of which REQUIRE at least one negative leg)
were unusable.

**Root cause traced from keystroke → state → submit payload:**
`BCRLineEditor.jsx` line 126 rendered the delta input as
`<Input type="number" step="0.01">`. With a controlled React input of
`type=number`, when a user types a lone `-`, **most browsers set
`e.target.value = ""`** (a lone minus is not yet a valid number, so the
DOM-side text holds the minus character while the JS-side `value`
property is empty). State stores `""`. When the user then types `4`,
the DOM still visually shows `-`, but `e.target.value = "4"`. State now
holds `"4"` (positive). `Number("4") = 4`. The running net
(`netOf(lines)` at line 26-33 in `BCRLineEditor`) sums positives and
stays positive. Exactly the operator's symptom.

**Cross-check (LD4 — "Match existing patterns"):** the working
signed-money input used elsewhere is in `components/actuals/
CreateActualSheet.jsx:244` — a plain `<Input>` with `inputMode="decimal"`
(no `type=number`) validated against the regex
`/^-?\d+(\.\d{1,2})?$/` declared in `lib/schemas/actuals.js:20`. That
regex already powers `actualSchema.net_amount` validation across actuals.
The fix mirrors that pattern.

### Bug 3 — MEDIUM — every budget line shows "Untitled line"

**Symptom (operator-reproduced):** The budget-line picker dropdown
listed every line as "Untitled line" + a hex id fragment. Lines were
indistinguishable, so even with Bug 1 and Bug 2 fixed, the feature was
unusable in practice — a user couldn't tell which budget line they were
moving money to/from.

**Root cause investigation per §R0.2:**

- **(a) What field did the picker read?**
  `BCRLineEditor.jsx` rendered `{bl.description || 'Untitled line'}` and
  `{bl.cost_code ?? bl.cost_code_id?.slice(0, 6) ?? '—'}`.
- **(b) Are those fields populated in the API response for these lines?**
  Read `backend/app/routers/budgets.py:145-175` (`_serialise_line`):
  - Backend emits `line_description` (string, possibly null), **NOT**
    `description`.
  - Backend emits `cost_code_id` (a UUID string), **NOT** a
    human-readable `cost_code` field.
  - So `bl.description` was always undefined → fallback `"Untitled line"`
    fired for every row. `bl.cost_code` was always undefined → fallback
    chain showed the first 6 chars of the UUID.
- **(c) Do the lines genuinely have names?**
  Yes — the seeded budgets had `line_description` populated. The data was
  fine; the frontend was reading the wrong field name.

**Decision (frontend-only fix per LD1):** read the correct backend field
`line_description`. The remaining design question — what to show when
`line_description` IS null/empty (allowed by the schema:
`Field(default=None, max_length=255)`) — was put to the operator with
four options:

| Option | Fallback | Notes |
|--------|----------|-------|
| (a) | `'(unlabelled)'` | Minimalist; rows with null descriptions all collapse to the same string — still indistinguishable. |
| (b) | `` `Line ${id.slice(0, 8)}` `` | Always distinguishable via short id; reads "raw" though. |
| **(c)** | `` `Line ${display_order ?? id.slice(0, 8)}` `` | Human-readable integer position (already emitted by the serialiser at `budgets.py:170`), short id only if `display_order` is also absent. **Operator confirmed this option.** |
| (d) | Other | — |

**Note on previous run's pre-emptive edits.** When the chat-37 fork
started, the working tree already contained uncommitted edits from a
previous fork that had jumped to R1 without honouring the §R0 STOP gate.
Those edits picked option (a) (`'(unlabelled)'`) for Bug 3 and were
captured in platform auto-commit `1ac46af`. The operator's decision was
honoured by amending the picker and detail-row label in two follow-up
commits.

---

## §R1 — Fixes (applied)

### Bug 1 — missing `DialogDescription` import

`frontend/src/pages/projects/BudgetChangeDetail.jsx` line 23:

```diff
 import {
-  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
+  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
 } from '@/components/ui/dialog';
```

Single-line fix. Audit confirmed no other budgetChanges file had a
missing import.

### Bug 2 — signed delta input + edge-case handling

`frontend/src/components/budgetChanges/BCRLineEditor.jsx` line 125-134:

```diff
 <Input
-  type="number"
-  step="0.01"
+  type="text"
+  inputMode="decimal"
   value={ln.delta}
-  onChange={(e) => update(i, { delta: e.target.value })}
+  onChange={(e) => update(i, { delta: e.target.value.replace(/,/g, '') })}
   placeholder="0.00"
   className="text-right"
   disabled={disabled}
   data-testid={`bcr-line-editor-delta-${i}`}
 />
```

`frontend/src/components/budgetChanges/CreateBudgetChangeDialog.jsx` —
hoisted `DELTA_REGEX = /^-?\d+(\.\d{1,2})?$/` to module scope (mirrors
the actuals `lib/schemas/actuals.js:20` pattern, satisfying LD4), tightened
`validateBeforeSubmit` to reject non-conforming strings before the
`Number()` coercion, and added `.trim()` on the submit-payload `delta`
string.

`frontend/src/pages/projects/BudgetChangeDetail.jsx` —
`EditBCRDialog.submit()` now runs the same DELTA_REGEX guard (it
previously only checked `Number(...) === 0`, so non-numeric strings could
fall through to the API).

**Edge cases (R5 §6) — all handled:**
- Lone `-` doesn't crash; the regex rejects it on submit with a clear
  "needs a numeric delta" toast.
- `-0` parses to `0` and is rejected by the existing non-zero check.
- Pasted `-1,234` has commas stripped by the `onChange` sanitiser →
  state holds `-1234` → parses to `-1234` as required.

### Bug 3 — picker / detail-row label fallback (operator option (c))

`frontend/src/components/budgetChanges/BCRLineEditor.jsx` (picker):

```diff
 {budgetLines.map((bl) => (
   <SelectItem key={bl.id} value={bl.id}>
     <span>
-      {bl.line_description || '(unlabelled)'}
+      {bl.line_description
+        || `Line ${bl.display_order ?? bl.id.slice(0, 8)}`}
     </span>
     {bl.is_contingency ? (
       <span className="ml-2 text-xs text-amber-700">
         (contingency)
       </span>
     ) : null}
   </SelectItem>
 ))}
```

`frontend/src/pages/projects/BudgetChangeDetail.jsx` (detail line table):

```diff
 <td className="px-3 py-2">
   {bl
-    ? (bl.line_description || '(unlabelled)')
+    ? (bl.line_description
+        || `Line ${bl.display_order ?? bl.id.slice(0, 8)}`)
     : <span className="text-slate-400">(line not in current budget snapshot)</span>}
   {bl?.is_contingency ? (
     <span className="ml-2 text-xs text-amber-700">(contingency)</span>
   ) : null}
 </td>
```

No backend change — `display_order` is already emitted by
`_serialise_line` at `routers/budgets.py:170`.

---

## §R5 — Acceptance gates

Tests added per the existing FE convention (co-located `__tests__/`,
`renderWithProviders` + `mockMe` / `mockLine` fixtures). No new test
infrastructure introduced.

### `frontend/src/components/budgetChanges/__tests__/BCRLineEditor.test.jsx` (8 tests)

- **Bug 2 §R5#3:** typing `-40000` into the delta input is preserved in
  state with the sign intact; re-render asserts the running Net displays
  `-£40,000`.
- **Bug 2 §R5#4:** a `-40000` / `+40000` Transfer nets to £0.00 and the
  `bcr-line-editor-net-warn` element is absent.
- **Bug 2 §R5#6 (paste edge case):** `onChange` strips commas — pasted
  `-1,234` lands in state as `-1234`.
- **Bug 2 §R5#6 (lone `-` edge case):** a lone `-` is preserved in state
  without crash (regex rejects on submit, separately covered by the
  create-dialog validator).
- **Bug 3 (primary):** picker uses `bl.line_description` when present
  (`'Substructure'`).
- **Bug 3 (display_order fallback):** picker shows `'Line 3'` when
  description is null and `display_order = 3`.
- **Bug 3 (short-id fallback):** picker shows
  `'Line abcdef12'` when both description and display_order are absent.
- **Bug 3 (distinguishability §R5#7):** two lines with null descriptions
  but `display_order = 1` and `display_order = 2` render as `'Line 1'`
  and `'Line 2'` respectively — they are visually distinct.

### `frontend/src/pages/projects/__tests__/BudgetChangeDetail.test.jsx` (3 tests)

- **Bug 1 §R5#1:** page mounts at `/budget-changes/:bcrId` for a Draft
  BCR, the `bcr-detail` testid is present, and `console.error` records
  no `ReferenceError` during render. Asserts the missing-import crash is
  gone.
- **Bug 3 (primary):** detail line table renders `line_description`
  (`'Concrete works'`).
- **Bug 3 (display_order fallback):** detail row falls back to
  `'Line 4'` when `line_description` is null.

### Regression §R5#8-#10

- **FE suite green:** **416 / 416 passing**, 63 suites (+11 tests vs.
  the 405-test pre-fix baseline). Zero regressions.
- **ESLint clean** for every edited file (verified via
  `mcp_lint_javascript`).
- **Two-step regression (create → open → submit → approve → apply,
  budget figure moves):** structurally covered by the persistence of all
  62 pre-existing test suites and the Chat 36 iteration_11 testing-agent
  manual regression. No new e2e was rerun in-pod for this defect pass —
  the FE unit tests verify the exact points of failure the operator
  reproduced, and the operator runs the manual two-user click-through
  post-push.
- **Backend untouched:** `alembic heads` → `0038_sc_valuations`;
  `len(PERMISSION_CATALOGUE)` → 129; `git diff --stat backend/` →
  (empty).

---

## Files added / modified

### Added (frontend)
- `frontend/src/components/budgetChanges/__tests__/BCRLineEditor.test.jsx`
- `frontend/src/pages/projects/__tests__/BudgetChangeDetail.test.jsx`
- `docs/chat-summaries/chat-37-closing.md` (this file)

### Modified
- `frontend/src/pages/projects/BudgetChangeDetail.jsx` — Bug 1
  (`DialogDescription` import); Bug 3 (detail-row label fallback);
  Bug 2 ancillary (DELTA_REGEX guard in `EditBCRDialog.submit`).
- `frontend/src/components/budgetChanges/BCRLineEditor.jsx` — Bug 2
  (input type, inputMode, comma-strip); Bug 3 (picker label fallback).
- `frontend/src/components/budgetChanges/CreateBudgetChangeDialog.jsx` —
  Bug 2 (hoisted DELTA_REGEX to module scope, validator uses it,
  payload `.trim()`).
- `CHANGELOG.md` (Chat 37 entry).
- `memory/PRD.md` (Chat 37 entry).
- `docs/SY_Hub_Phase2_Backlog.md` — **not modified** (operator-edited
  only; the three follow-ups from this chat are listed in the
  "Backlog — items noted out of this chat" section below for the
  operator to hand-number).

### NOT modified (backend FROZEN)
Zero backend files touched. Alembic HEAD unchanged at
`0038_sc_valuations`. Permission count unchanged at 129. No migration
folder touched. No router change. No serialiser change.

---

## Commits

The fix landed across three commits on `main` (chained from the
pre-fork auto-commit):

| SHA | Subject | Notes |
|-----|---------|-------|
| `1ac46af` | `auto-commit for 4c81b19a-…` | Platform auto-commit capturing the previous fork's working-tree edits: Bug 1 import, Bug 2 input-type swap, Bug 3 first-pass `line_description` swap (option (a)), `CreateBudgetChangeDialog` DELTA_REGEX. |
| `c4a7a87` | `fix(BCR): option-c label fallback + paste comma-strip (2.6-FE-fix)` | Operator-confirmed option (c) label in picker + detail row; comma-stripping `onChange` for Bug 2 §R5#6. |
| `4758e92` | `test(BCR) + docs: 2.6-FE-fix acceptance gates + CHANGELOG/PRD` | 11 new tests, CHANGELOG, PRD. |
| _(this commit)_ | `docs(chat-37): closing summary only` | This summary. The three follow-up items (B62 / B63 / B64) are handed to the operator for hand-entry into the backlog file. |

---

## Backlog — items noted out of this chat

Three follow-ups surfaced during the root-cause investigation. All are
out-of-scope for 2.6-FE-fix (LD2: "Scope is exactly these three bugs.
No refactors, no 'while I'm here' improvements") and have been handed
to the operator for hand-numbering into the Phase 2 backlog (the
backlog file is operator-edited only). Pre-assigned numbers per the
operator's confirmation: **B62 / B63 / B64**.

- **B62 — Budget-line serialiser emits no human-readable cost code.**
  `_serialise_line` (`backend/app/routers/budgets.py:145-175`) returns
  `cost_code_id` (UUID string) but no `cost_code` text. The BCR picker
  had to drop the cost-code prefix when reading the wrong field was
  fixed, because there is no text to read. A `cost_code` text column
  should be joined from `cost_codes.code` and surfaced on the serialised
  budget-line shape so the picker can render
  `${cost_code} · ${line_description}` (the original intent).
  Half-session backend prompt. From Chat 37 (2.6-FE-fix).

- **B63 — `budget_lines.line_description` nullability.** Today the
  column is `Nullable=True` with no UI gate. This is why a frontend
  fallback was needed at all. Two cheap options:
  (a) Tighten the schema to require `line_description` at create-time
  via a Pydantic validator (no migration — handle at the API layer).
  (b) Add a "Name your lines" affordance to the budget editor so PMs
  can't end up with unnamed rows after a from-appraisal import. Either
  would let us drop the `Line ${display_order}` fallback. Backend +
  small FE. From Chat 37 (2.6-FE-fix).

- **B64 — Lint gate for missing JSX imports.** Bug 1 was a one-line
  missing named import that survived Chat 36's testing-agent review
  and the Playwright suite. ESLint's `react/jsx-no-undef` rule would
  catch this at lint time. Verify it's enabled (and set to `error`,
  not `warn`) in `frontend/.eslintrc` / `frontend/eslint.config.js`,
  and if not, enable it and run a single sweep so any other lurking
  missing-import bombs are exposed before they crash a real user. Tiny
  prompt. From Chat 37 (2.6-FE-fix).

---

## Deferred / out-of-scope (per LD2)

- Anything beyond the three operator-reproduced bugs. Per the
  Build Pack: "No refactors, no 'while I'm here' improvements, no new
  features."
- The cross-project BCR queue (B58 — separate backend prompt; already
  on the backlog from Chat 36).
- The manual MFA-enrolment gap on director/finance test users
  (flagged in the Build Pack but noted as "do not solve here").

---

## Operator next-step

`Save to GitHub` to push the three SHAs (`c4a7a87`, `4758e92`, and the
docs commit appended above) plus the platform auto-commit `1ac46af` to
`main`. Once pushed, rerun the manual two-user click-through that
exposed the bugs originally:

1. Log in as a PM (e.g. `test-pm@example.test`), open
   `?tab=changes` on a seeded budget.
2. **Bug 1 gate:** Click a Draft BCR → the detail page should load
   without a white screen / console `ReferenceError`.
3. **Bug 2 gate:** Open the Edit dialog → enter a Transfer with one
   line at `-40000` and another at `+40000` → Net = £0.00 → Save.
4. **Bug 3 gate:** In the line picker, confirm each option shows a
   distinguishable label — `line_description` where set, otherwise
   `Line 0` / `Line 1` / `Line 2` etc.
5. **Two-step regression:** submit → approve (as a second user above
   the £10k self-approval threshold) → apply → the budget figure should
   move on apply, not on approve.

If all five gates pass on the deployed build, 2.6-FE-fix is fully closed.
