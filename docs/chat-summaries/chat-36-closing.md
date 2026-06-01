# Chat 36 closing — Build Pack 2.6-FE (BCR Workflow Frontend)

**Branch strategy:** push-to-main (frontend slice; no migrations).
**Build pack:** `BuildPack_2_6_FE_BCR_Workflow.md`.
**Type:** frontend-only (no backend changes, no migrations).
**Scope:** Surface the entire Budget Change Request (BCR) lifecycle in
the UI — queue, detail, create, edit, reject, withdraw, apply, and
change-log — with strict adherence to the backend contract and zero
backend modifications. Backend FROZEN at alembic head
`0038_sc_valuations`, 129 permissions.

---

## §R0 Pre-flight (reported BEFORE coding)

All pre-flight checks green:
- `scripts/provision_postgres.sh`, `pip install`, bootstrap (rc=0),
  `yarn install` — all clean.
- Alembic HEAD verified at `0038_sc_valuations` (unchanged).
- Permission catalogue verified at **129** via
  `len(PERMISSION_CATALOGUE)` from `seed_rbac.py`.

---

## §R0.2 ENDPOINT COVERAGE MAP (operator-confirmed STOP gate)

Per the Build Pack STOP-gate contract, NO component code was written
until the map was reported AND the operator confirmed it. Every
endpoint and every permission mapped to a surface; no blank rows.

### Endpoints (10)

| # | Method | Path                                    | Perm                        | Surface(s) |
|---|--------|-----------------------------------------|-----------------------------|------------|
| 1 | POST   | `/api/v1/budget-changes`                | `budget_changes.create`     | C → G |
| 2 | GET    | `/api/v1/budget-changes?budget_id&…`    | `budget_changes.view`       | A |
| 3 | GET    | `/api/v1/budget-changes/{id}`           | `budget_changes.view`       | B |
| 4 | PATCH  | `/api/v1/budget-changes/{id}`           | `budget_changes.edit`       | B (edit mode, Draft only) → G |
| 5 | POST   | `/api/v1/budget-changes/{id}/submit`    | `budget_changes.submit`     | B (Draft only) |
| 6 | POST   | `/api/v1/budget-changes/{id}/approve`   | `budget_changes.approve`    | B (Submitted only; self-approval guard) |
| 7 | POST   | `/api/v1/budget-changes/{id}/reject`    | `budget_changes.approve`    | B → D (required reason) |
| 8 | POST   | `/api/v1/budget-changes/{id}/withdraw`  | `budget_changes.create`     | B (creator-only, Draft/Submitted) |
| 9 | POST   | `/api/v1/budget-changes/{id}/apply`     | `budget_changes.apply`      | B (Approved only) |
| 10| GET    | `/api/v1/budgets/{budget_id}/change-log`| `budget_changes.view`       | E |

### Permissions (6)

| Permission | Gates In UI |
|------------|-------------|
| `budget_changes.view`    | A queue · B detail · E change-log · BudgetDetail tab visibility |
| `budget_changes.create`  | C New-change CTA · Withdraw on B (own BCR, Draft/Submitted) |
| `budget_changes.edit`    | B Edit affordance (Draft only) |
| `budget_changes.submit`  | B Submit-for-approval button |
| `budget_changes.approve` | B Approve + Reject buttons (Submitted only; self-approval guard hides Approve and Reject when `creator && gross >= threshold`) |
| `budget_changes.apply`   | B Apply-to-budget button (Approved only) |

The handoff summary said "8 endpoints"; the router actually has **10**
(it omitted `list` and `withdraw`). Map presented enumerated all 10.

---

## §R0.2 PIN — endpoint 9 (apply) semantic re-confirmation

Operator requested a re-confirmation from the backend before R1 coding
proceeded. Read `services/budget_changes.py` end-to-end:

- **`approve_bcr` (lines 507–538)** transitions Submitted → Approved
  only:
  - Runs the LD2 self-approval guard
    (`sum(abs(delta)) >= threshold`) and raises
    `BudgetSelfApprovalError` on violation.
  - Calls `_stamp_transition(..., new_status="Approved",
    action="Approve")` and returns.
  - **Does NOT** touch `budget_lines.approved_changes`.
  - **Does NOT** call `_recompute_line` / `recompute_summary`.
  - **Does NOT** advance to `Applied`.

- **`apply_bcr` (lines 580–650)** is the ONLY mutator:
  - Requires `bcr.status == "Approved"` (raises
    `BudgetStateError` otherwise).
  - Acquires `SELECT … FOR UPDATE` on referenced
    `budget_lines` rows for FRESH reads.
  - Re-asserts parent budget in `_ALLOWED_PARENT_STATUSES`
    (Active / Locked).
  - All-or-nothing writes `approved_changes += delta`.
  - Calls `budgets_svc.recompute_summary(db, parent)`.
  - Stamps `Applied`.

**Verdict reported to operator:** two-step Approve → Apply is REQUIRED
and CORRECT. The Approved-but-not-applied state is the explicit
design (race-safe FRESH-read at apply time so a later BCR sees the
most recent state). The "awaiting apply" UI affordance is the right
shape. Operator green-lit R1 on this basis.

---

## §R0 — BACKEND GAP raised (STOP per backend-frozen rule)

While preparing R1, the list endpoint contract was checked:

```python
# app/routers/budget_changes.py:120-137
@router.get("/budget-changes")
def list_budget_changes(
    budget_id: uuid.UUID = Query(...),   # ← REQUIRED, single budget
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ...
):
```

`services.budget_changes.list_bcrs` also hard-requires `budget_id`.
**No cross-budget / cross-project query path exists.** The PO
approvals surface has BOTH a per-project list (`GET
/projects/{id}/approvals/pending`) AND a cross-project list (`GET
/approvals/pending`); BCR was built without the equivalent.

Per the backend-frozen rule, the gap was STOPPED to the operator with
three resolution options:

- (a) Drop cross-project scope; build /budget-changes as a budget-picker landing.
- (b) Client-side fan-out (N parallel requests). REJECTED explicitly by operator.
- (c) STOP the slice and route the gap back to the backend track.
- (d) Hybrid — per-budget queue today + log a specced backend item for the deferred cross-project surface.

**Operator chose (d).**

### B51 raised
"BCR list lacks cross-project / pending endpoints. PO approvals
already has the pattern (`GET /approvals/pending` +
`GET /projects/{id}/approvals/pending`). Add
`GET /budget-changes/pending` +
`GET /projects/{id}/budget-changes` mirroring it. Unblocks the
standalone BCR approval queue (deferred LD1 surface). Half-session
backend prompt."

---

## §R1 — Surfaces shipped (scope (d))

### Surface A — `BudgetChangeQueue` (per-budget queue)

`components/budgetChanges/BudgetChangeQueue.jsx`. Mounted as the
"Changes" tab on `BudgetDetail` (`?tab=changes`). Eight filter chips
(Open / All / Draft / Submitted / Approved / Applied / Rejected /
Withdrawn). The "Open" composite is a client-side filter over the
unfiltered fetch (bounded by the backend 200-cap). Empty-state offers
a "Show all" shortcut. New-change CTA opens Surface C.

### Surface B — `BudgetChangeDetail` (workflow page)

`pages/projects/BudgetChangeDetail.jsx`. Route added in `App.js`:
`/budget-changes/:bcrId` (lazy-loaded in the `budgets` chunk).
Renders header (reference / status pill / type / title / reason /
net impact / timeline of created → submitted → approved → applied /
rejected with rejection reason banner), line table (cost code,
description, contingency badge, signed delta), and the action bar
(`BCRActionButtons`). Embeds `EditBCRDialog` (Draft-only inline
edit calling PATCH).

### Surface C — `CreateBudgetChangeDialog`

`components/budgetChanges/CreateBudgetChangeDialog.jsx`. Modal form
for `POST /budget-changes`. Mirrors backend invariants client-side
for fast feedback:

- **Transfer** — ≥2 lines, net = £0.
- **ContingencyDrawdown** — ≥2 lines, net = £0, every negative
  source line must reference a `is_contingency` budget line.
- **Adjustment** — net ≠ £0.

Backend remains the authority — 422s surface as toasts.

### Surface D — `BCRRejectDialog`

`components/budgetChanges/BCRRejectDialog.jsx`. Required-reason
modal for `POST /budget-changes/{id}/reject` (backend gates on
`Field(..., min_length=1)`). Confirm button disabled until reason
is non-empty after trim.

### Surface E — `BudgetChangeLogPanel`

`components/budgetChanges/BudgetChangeLogPanel.jsx`. Mounted as the
"Change log" tab on `BudgetDetail` (`?tab=change-log`). Read-only
audit trail using `GET /api/v1/budgets/{budget_id}/change-log` —
newest first, 200-cap, includes Rejected / Withdrawn / Applied
terminals with timestamps and rejection reasons (when present).

### Surface F — `BCRStatusPill`

`components/budgetChanges/BCRStatusPill.jsx`. Six-status colour map
matching the existing `StatusBadge.jsx` convention:

- Draft     — slate
- Submitted — amber
- Approved  — sky
- Applied   — emerald
- Rejected  — rose
- Withdrawn — muted slate

### Surface G — `BCRLineEditor`

`components/budgetChanges/BCRLineEditor.jsx`. Shared line builder
reused by Create + Edit. Budget-line picker (Radix Select) + signed
delta input + live net total with type-aware invariant hints (net=£0
warning for Transfer/Contingency; "must be non-zero" warning for
Adjustment; contingency-source warning when a negative line points
at a non-contingency budget line).

---

## `BudgetDetail` 3-tab shell

`pages/projects/BudgetDetail.jsx` rebuilt around a `?tab=` URL
contract. Tabs:

- `lines` (default) — `BudgetGridV2`
- `changes` — Surface A
- `change-log` — Surface E

Tabs gated by per-tab perm (`budgets.view` / `budget_changes.view`).
Mirrors PurchaseOrderList `?tab=approvals` precedent. Legacy
`?line=` / `?drilldown=` deep-link rewrite to `?expanded=` preserved.

---

## Self-approval guard (LD2) — mirrors backend exactly

Initial implementation (per Build Pack §R1) gated Approve on the
binary `creator` check. Testing-agent iteration_11 flagged this as
strictly more restrictive than the backend (a PM-creator could not
self-approve a £200 BCR via the UI even though the API would allow
it — backend rule is `sum(abs(delta)) >= threshold` GROSS, not
binary creator). Fix applied:

- `hooks/systemConfig.js` adds `useBudgetSelfApprovalThreshold()`
  reading `GET /api/v1/system-config/budget.self_approval_threshold_gbp`
  (default £10k fallback if the request fails).
- `BCRActionButtons.jsx` now computes
  `gross = sum(Math.abs(Number(ln.delta)))` and only renders the
  disabled twin + hides the Reject button when
  `creator && gross >= threshold`. Tooltip on the disabled button
  surfaces the actual gross and threshold values. Matches
  `services/budget_changes.py:520-532` precisely.

Backend remains the authority — a 403 `BudgetSelfApprovalError` is
the safety net if the client-side threshold is stale.

---

## Two-step Approve → Apply UI

When a BCR is `Approved`, `BCRActionButtons` renders:

1. The `bcr-awaiting-apply-hint` banner — "Approved — awaiting apply.
   The parent budget has NOT yet been updated. Click Apply to budget
   to push the deltas and recompute totals. A separate apply step is
   intentional so concurrent BCRs always see the most recent budget
   state."
2. The emerald `bcr-actions-apply-btn` button.

Makes the §R0.2-PIN design explicit to the user.

---

## React Query cache discipline

`useBCRTransition` mutations invalidate `bcrKeys.detail`,
`bcrKeys.all`, and `['budget-change-log']` on every verb. The
`apply` verb additionally coarse-invalidates `['budgets']` +
`['budget']` so `BudgetGridV2` (and the `BudgetHeader` totals)
re-fetch the `approved_changes` / `current_budget` / `variance`
columns after `apply_bcr` runs `recompute_summary`. Mirrors the PO
commitment-verb pattern at `hooks/purchaseOrders.js:235`.

---

## a11y + React warning cleanup (P3/P4 fixes from iteration_11)

- All four Radix Dialog usages now carry a `<DialogDescription>`
  (CreateBudgetChangeDialog, BCRRejectDialog, EditBCRDialog,
  withdraw confirm dialog) — silences the
  "Missing Description or aria-describedby={undefined} for
  {DialogContent}" Radix a11y warning.
- Select components default to `undefined` rather than `''` so they
  remain controlled from mount — silences the
  "Select is changing from uncontrolled to controlled" React
  warning. Verified empty `errors` array in devtools console.

---

## Testing

`testing_agent_v3_fork` iteration_11 (frontend only — backend
frozen): **15/15 review scenarios PASS, 100% frontend success
rate, 0 backend changes, 0 mocked APIs.**

Scenarios verified:
- Login as `test-pm@example.test`, navigate to `?tab=changes`.
- 3-tab bar visibility + URL sync (`?tab=lines/changes/change-log`).
- Queue empty-state + filter chips + show-all shortcut.
- BCR-0001 (API-seeded Transfer £5k/£10k-gross Draft) opens at
  `/budget-changes/<id>` with correct testids.
- Draft action matrix (edit / submit / withdraw visible; approve
  not visible).
- Submit transition (Draft → Submitted).
- Self-approval guard at £10k boundary (`gross >= threshold`
  hides Approve + Reject and renders the disabled twin).
- Create dialog Transfer (+500/-500 lines, net=£0, no warning)
  end-to-end through to the queue.
- Adjustment net-zero validation (warning shows at delta=0, clears
  at delta=100).
- Change Log tab shows all 3 BCRs.
- Withdraw flow: dialog → confirm → Withdrawn pill → terminal
  action set (no buttons).
- Status pill colour map: Draft slate / Submitted amber /
  Approved sky / Applied emerald / Rejected rose / Withdrawn
  muted slate.
- API path pin: every BCR network request uses
  `/api/v1/budget-changes…` — 0 path violations.

Post-fix self-test (screenshot + console-error capture) verified
the three P3/P4 follow-ups landed clean.

---

## `test_credentials.md` update

Added BCR section pinning `test-pm@example.test` as the recommended
test user. PM role has all 6 `budget_changes.*` perms AND bypasses
MFA enrollment. The `super_admin` / `director` / `finance` roles
enforce MFA and sit on `token_type=mfa_pending` after login until
enrolled — `/auth/me` returns `permissions=[]` for them, which made
them unusable for BCR testing this slice. Documented the seeded
budget IDs (`b2a265ef-…` project, `5a329b39-…` budget) and the
seeded `BCR-0001` Draft Transfer.

---

## Files added / modified

### Added (frontend)
- `frontend/src/lib/api/budgetChanges.js`
- `frontend/src/hooks/budgetChanges.js`
- `frontend/src/hooks/systemConfig.js`
- `frontend/src/lib/budgetChangeCapability.js`
- `frontend/src/components/budgetChanges/BCRStatusPill.jsx`
- `frontend/src/components/budgetChanges/BCRLineEditor.jsx`
- `frontend/src/components/budgetChanges/BCRRejectDialog.jsx`
- `frontend/src/components/budgetChanges/CreateBudgetChangeDialog.jsx`
- `frontend/src/components/budgetChanges/BCRActionButtons.jsx`
- `frontend/src/components/budgetChanges/BudgetChangeQueue.jsx`
- `frontend/src/components/budgetChanges/BudgetChangeLogPanel.jsx`
- `frontend/src/pages/projects/BudgetChangeDetail.jsx`
- `docs/chat-summaries/chat-36-closing.md` (this file)

### Modified
- `frontend/src/App.js` (lazy import + route for
  `/budget-changes/:bcrId`)
- `frontend/src/pages/projects/BudgetDetail.jsx` (3-tab shell with
  `?tab=` URL contract; embeds Surface A + Surface E)
- `CHANGELOG.md` (Chat 36 entry)
- `memory/PRD.md` (Chat 36 entry)
- `memory/test_credentials.md` (BCR section)

### NOT modified (backend FROZEN)
Zero backend files touched. Alembic HEAD unchanged at
`0038_sc_valuations`. Permission count unchanged at 129.

---

## Deferred / out-of-scope (per operator (d) decision)

- Standalone `/budget-changes` cross-project queue page. Blocked
  on **B51** (backend endpoints missing). Surface stub NOT shipped
  to keep this slice clean. Once B51 lands, this is a thin
  build — same `BudgetChangeQueue` component, different list
  endpoint, no filter `budget_id`.

---

## Operator next-step

`Save to GitHub` to push the slice to `main`. Commit SHA(s) will be
visible in the platform's commit listing post-push. The B51 backend
prompt can be started in a fresh chat once the operator wants the
deferred director queue surfaced.
