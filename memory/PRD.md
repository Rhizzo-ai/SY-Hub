# SY-Hub Platform — PRD

## Original problem statement

Execute strict prompts (Build Packs) to extend the SY-Hub backend per the
SY Homes Phase 1 / Phase 2 brief. Each prompt has 15 locked decisions, an
exact migration count, an exact endpoint count, and a target test delta.
Frontend / actuals / commitments / Xero are out of scope until later prompts.

## Stack
- FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL 16
- Pytest with cookies-only auth contract (no Bearer headers)
- Pattern α tenant scoping: project-id resolution + `_visible_project_ids`
  filter, mirroring `routers/appraisals.py`. **No** `tenant_id` columns on
  Track-2+ tables (exception: `purchase_orders.tenant_id` is denormalised
  for list-time tenant filtering — see Chat 24 R2).
- Audit append-only via `audit_log` + `audit_log_no_modify()` trigger.

## What's been implemented

### 2026-02-01 — Chat 32 (Prompt 2.7) Subcontractors, CIS Verifications & Supplier Documents ✓ COMPLETE

Backend-only build per Build Pack 2.7. Push-to-main (operator verifies
on GitHub web). All 28 acceptance gates green.

- **§R1 Migration `0035_subcontractors`.** Idempotent enum extensions
  (`permission_action += 'verify'`; `permission_resource += 'cis',
  'supplier_documents'`); new PG enum `supplier_type` (`Supplier`,
  `Subcontractor`); 5 new columns on `suppliers`
  (`supplier_type` NOT NULL default `'Supplier'` — clean backfill;
  `cis_subtype` String(30) nullable, app-constrained;
  `cis_registered` Boolean NOT NULL default false;
  `utr` String(13) nullable, sensitive;
  `current_cis_status` String(20) nullable, service-maintained cache);
  new table `subcontractor_cis_verifications` (append-only,
  match_status CHECK Gross/Net/Unmatched, supplier_id+verified_on DESC
  index); new table `supplier_documents` (lightweight; doc_type CHECK
  vs 7 allowed values; soft-delete via is_archived). Downgrade drops
  new tables, columns, and the supplier_type enum (PG cannot drop
  enum values — documented asymmetry per 0029 pattern). Live
  round-trip down/up verified.
- **§R2 Permissions.** `_perms_for("cis", include=["view",
  "view_sensitive","verify"], sensitive={"view_sensitive","verify"})`
  + `_perms_for("supplier_documents", include=["view",
  "view_sensitive","create","edit","archive"],
  sensitive={"view_sensitive","archive"})`. **102 → 110.** Role
  mapping mirrors suppliers.create role-set (super_admin, director,
  finance, project_manager) for cis.verify + ALL 5 supplier_documents
  perms (test gate 27 literal); cis.view_sensitive mirrors
  suppliers.view_sensitive (3 roles); cis.view extended to
  site_manager + read_only (broader read).
- **§R3 Services.**
  - `services/suppliers` extended: `_validate_supplier_type`,
    `_validate_cis_subtype` (rejects on Plain Supplier),
    `_validate_utr` (whitespace-strip + 10-digit check),
    `list_suppliers(supplier_type=…)` filter, `_AUDIT_COLS` includes
    the 5 new columns. `current_cis_status` defaults `Unverified` for
    new Subcontractors, NULL for plain Suppliers; NOT settable via
    update payload. UTR added to `SENSITIVE_RESPONSE_FIELDS`.
  - `services/cis` new module:
    `record_verification` (rejects on non-Subcontractor →
    `ValueError`, validates match_status ∈ {Gross,Net,Unmatched},
    coerces dates/decimals, **only writer of**
    `supplier.current_cis_status`, emits audit `Create`),
    `list_verifications` (newest first by verified_on),
    `get_current_verification`. NO update/delete helpers exposed
    (append-only contract).
  - `services/supplier_documents` new module: mirrors suppliers
    service patterns 1:1 — `create_document`, `list_documents`
    (excludes archived by default, `include_archived` flag),
    `get_document`, `update_document`, `set_archived` (idempotent;
    audits Archive/Restore). `file_ref` + `notes` gated in
    serialiser via `SENSITIVE_RESPONSE_FIELDS`.
- **§R4 Routers.**
  - `routers/suppliers` extended: `?supplier_type=` query param on
    GET (router→service ValueError→422); 4 new create/update body
    fields (`supplier_type`, `cis_subtype`, `cis_registered`, `utr`
    — `utr` max_length=30 at body layer to accept whitespace-decorated
    input; service strips and validates against 10-digit contract).
    Serialiser surfaces all subcontractor fields; `utr` gated.
  - `routers/cis` new (prefix `/cis`): `POST /verifications` (201,
    gate `cis.verify`, cross-tenant → 404, non-subcontractor → 409,
    other ValueError → 422; 201 response includes
    verification_number regardless of view_sensitive since creator
    just wrote it); `GET /verifications?supplier_id=…` (gate
    `cis.view`; strips `verification_number` without
    `cis.view_sensitive`); `GET /verifications/current`. **No PATCH,
    no DELETE.**
  - `routers/supplier_documents` new (prefix `/supplier-documents`):
    POST (201), GET list, GET one, PATCH, POST archive +
    POST unarchive. Cross-tenant → 404. All routers mounted under
    `/api/v1` in `server.py` alongside existing suppliers router.
- **§R5 Tests.** **42 new test functions** across 5 files
  (`test_subcontractors.py` 13, `test_cis_service.py` 7,
  `test_cis_api.py` 7, `test_supplier_documents.py` 11,
  `test_permissions_2_7.py` 4). All 28 build-pack acceptance gates
  covered. Baseline-drift literals bumped (chat-15 §3 pattern) in
  `test_auth_rbac` (super_admin 102→110, director 98→106, read_only
  12→13), `test_bootstrap` (head sentinel 0034_→0035_),
  `test_migration_0025_actuals`, `test_migration_0028_user_preferences`,
  `test_patch_3` (102→110), `test_retro_wires` (102→110).
  **Pytest 2nd-run WARM-DB: 1071 passed, 3 xpassed, 0 failed,
  0 errors, 196.53s.** Regression floor 1038 honoured.
- **Scope honoured.** No frontend (later split 2.7-FE). No auto-expiry
  flagging (LD2 / backlog **B48**). No payment-blocking on lapsed
  CIS (belongs with 2.8 valuations). Legacy `suppliers.cis_status`
  column left in place — `current_cis_status` is the authoritative
  cache; dropping the legacy column is OUT OF SCOPE (documented
  deviation in migration docstring). `supplier_documents.file_ref` is
  a reference string only; binary upload pipeline migrates to Track 5
  (backlog **B49**). Per-project supplier ratings backlog **B50**.
- **Commit:** `09d5367`. NOT pushed-confirmed (per Build Pack 2.7
  opener — operator verifies push on GitHub web).



### 2026-05-31 — Track 2.4C Budget Approval Controls (SoD) ✓ COMPLETE

Build Pack 2.4C R1–R5. Segregation-of-duties: a budget's creator cannot
self-activate at/above a configurable threshold (default £10,000).

- **R1 — Config.** New `system_config` row
  `budget.self_approval_threshold_gbp` (Decimal, default 10000.00,
  category Budget, super_admin-editable). Typed getter
  `get_budget_self_approval_threshold(db)` with in-code fallback
  `DEFAULT_BUDGET_SELF_APPROVAL_THRESHOLD_GBP = Decimal("10000.00")`.
  Seed reconciliation count 39 → 40.
- **R2 — `activate()` guard.** In `app/services/budgets.py::activate()`:
  side-effect-free local-variable total
  = Σ(`original_budget` + `approved_changes`) across freshly-loaded
  `BudgetLine` rows (no `recompute_summary`, no read of cached
  `total_budget`). Comparison `total >= threshold`. NULL
  `created_by_user_id` fail-open. Super-admin **not** exempt.
- **R2.3 — Exception + mapping.** New `BudgetSelfApprovalError` →
  router maps to **HTTP 403** (authorisation refusal).
  `BudgetStateError` stays 409.
- **R5 — Tests.** `TestBudgetSelfApprovalGuard` (8 tests, all passing):
  boundary `==threshold` blocked, `>threshold` blocked, `<threshold`
  allowed, other-user activation allowed, NULL-creator guard asserted
  by source inspection (column is NOT NULL today), super-admin not
  exempt, service raises `BudgetSelfApprovalError` (not
  `BudgetStateError`), getter reads DB + falls back to default.
- **Test fixtures.** Three legacy modules (`test_budgets.py`,
  `test_actuals_routes.py`, `test_budgets_line_delete.py`) added a
  module-scope `_bump_self_approval_threshold` autouse fixture that
  **only raises** the threshold to £999,999,999 (via PUT
  `/system-config/{key}`, which invalidates the backend cache),
  restoring on teardown.
- **Pytest WARM-DB 2nd run:**
  `1035 passed, 2 xfailed, 1 xpassed, 2 warnings in 165.12s`.
- **Commits:** `199c857` (R1–R5 nine-file change), `9871219`
  (test-hygiene fix). **Push pending** — see CHANGELOG push-hygiene
  flag re: pre-existing auto-commit `352eb08` noise.

Files: `app/routers/budgets.py`, `app/seed_system_config.py`,
`app/services/budget_errors.py`, `app/services/budgets.py`,
`app/services/system_config.py`, `tests/test_actuals_routes.py`,
`tests/test_budgets.py`, `tests/test_budgets_line_delete.py`,
`tests/test_system_config.py`.

Backlog spawned: **B43** Stage 2 per-role / per-user approval limits,
**B44** threshold admin UI, **B45** FE 403 self-approval refusal message.



### 2026-02-27 — R7 Batch 2 follow-on mini-pack (backend) ✓ COMPLETE

Adds the missing `GET /projects/{project_id}/purchase-orders` endpoint
— a latent Chat 24 R5 gap that surfaced visibly with Batch 2's R7.5
approvals dashboard (the frontend `listProjectPOs` always hit this
URL).

- **R0 — Endpoint.** Thin wrapper in `app/routers/purchase_orders.py`
  adjacent to the existing `POST /projects/{project_id}/purchase-orders`
  (lines 360-407). Path-bound `project_id: uuid.UUID`; same query
  params as the un-scoped `GET /purchase-orders` (`supplier_id`,
  `status`, `q`, `limit`, `offset`); same `_perm_dep` + `pos.view`
  gate; same response shape `{items,total,limit,offset}`; delegates
  to `svc.list_pos(...)`. Route inventory docstring updated.
- **R1 — Tests.** 4 new tests in
  `tests/test_purchase_orders_api.py::TestR7Batch2FollowOnListProjectPOs`:
  scoped-results (project A vs B), status-filter, perm-gate
  (unauthenticated → 401), unknown-project → 200 + empty.
- **AC1–AC4 — All green.** Pytest warm-DB: 934 passed
  (before 930 → +4), 3 xpassed, 93 errors (all `test_projects.py`,
  pre-existing). Frontend bundle delta zero (main `4cb90fd2.js`
  hash identical). No migration, no new perm, no role grant, no
  frontend changes.



### 2026-02-27 — R7 Batch 2 (frontend) ✓ COMPLETE

R7 Batch 2 turns the seven Batch-1-deferred PO action testids back on
behind real forms / confirm dialogs / optimistic mutations. ONE STOP
at end per build pack `SY_Hub_R7_Batch2_BuildPack_v2.md`.

- **R7.4 — Receipt form.** New `POReceiptDialog` posts to
  `useCreateReceipt` (line qtys + received_date + delivery_note_ref +
  notes). Wired behind `po-actions-receipt-btn` (issued) and
  `po-actions-receipt-partial-btn` (partial). `useCreateReceipt` now
  coarse-invalidates `['budgets']` on success (AC5 — receipt moves
  committed → actual).
- **R7.5 — Per-project approvals dashboard tab.** New
  `POApprovalsTab` mounted as a tab on `PurchaseOrderList`
  (`?tab=approvals`). Uses `useProjectPOs(projectId, { params: {
  status: 'pending_approval' } })` + client-side filter fallback. Row
  Review affordance deep-links to `/purchase-orders/{id}?tab=approvals`
  (Batch-1 `POApprovalPanel` takes it from there). All-projects view
  parked at §CARRIED FORWARD.
- **R7.6 — Confirm-dialog + Void + optimistic layer.** New
  `POVoidDialog` (required-reason, clones reject-dialog shape) wired
  behind `po-actions-void-btn` (approved) and
  `po-actions-void-issued-btn` (issued/partial). Rebuilt
  `usePoTransition` with `onMutate`/`onError`/`onSettled`: void +
  sendBack apply an optimistic `status` patch (rollback on error);
  void/sendBack/issue/approve/close all coarse-invalidate `['budgets']`
  on settle.
- **Edit + Delete (Option A — header-only).** New `POEditDialog`
  (header-only PATCH; bound to backend `edit_tier` enum: `full` /
  `header_annotation_only` / `read_only` from
  `services/po_authz.py:EditPermission`). New `PODeleteDialog`
  (draft-only, mirrors backend 422 on non-draft). `po-actions-edit-btn`
  gates on `edit_tier === 'full'` + `pos.edit`;
  `po-actions-edit-issued-btn` gates on `edit_tier ===
  'header_annotation_only'` + `pos.edit_issued`;
  `po-actions-delete-btn` mounts only on draft.
- **AC1 — `DEFERRED_TESTIDS` array EMPTY, regression-guard block
  DELETED.** All 7 previously-deferred testids are wired; the
  empty-loop guard would have been vacuously green and was removed
  per the pack. Each re-enabled button has a per-status positive
  render assertion.
- **Tests.** Jest 387/387 green (unchanged from baseline — net of
  the 32 removed deferred-loop iterations vs new R7.4/R7.5/R7.6/Edit/
  Delete assertions). Five new E2E specs (`po-receipt.pm`,
  `po-approvals.pm`, `po-void.pm`, `po-edit.pm`, `po-delete.pm`)
  tagged `@po-batch2` + `@smoke`. New `yarn e2e:po-batch2` script.
- **Bundle.** main 395.24 kB gz (cap 437 kB → 41.76 kB headroom).
  `suppliers-po` chunk 14.57 kB gz.



### 2026-02-13 — Audit Remediation TIER P1 (v1 build pack) ✓ (R5 HALTED)

R0 reconciliation → R1–R6 built. R5 (destructive Alembic downgrade)
HALTED for operator decision per build-pack contract. No schema change.
Permissions 102 / roles 10 unchanged. Alembic head unchanged at
`0034_audit_sendback`. **Warm-DB suite: 928 passed, 3 xpassed, 0 failed,
93 errors (all `test_projects.py`, pre-existing).**

- **R0 — Reconciliation gate.** Pre-P0 tree at `130ccfc`: cold run 999
  passed clean / warm run 906 passed + 93 errors (all
  `test_projects.py` — same 93 as post-P0). Confirms the 93 errors are
  pre-existing, not P0-induced. The 2 audit_log failures I'd flagged
  earlier were transient state pollution — today's runs show 0 failures.
- **R1 — `mfa_pending` blocked from `/mfa/disable` and
  `/mfa/backup-codes/regenerate`.** Both swapped from
  `Depends(get_enrollment_user)` → `Depends(get_current_user)`.
  `verify_password` / `verify_totp` gates stay as defence in depth.
  Live evidence: 401 "Invalid token type" with `mfa_pending`; 204 (or
  400 "MFA not enrolled") with `access` — proving the dep passes the
  legitimate token through.
- **R2 — 3 order-dependent flaky tests quarantined** with
  `@pytest.mark.xfail(strict=False, reason=…)` + entry in
  `Future_Tasks.md` §23.
- **R3 — Source-row lock on `create_new_version`.** Layering: Option A
  (shared service helper). NEW `app/services/appraisal_locks.py` exports
  `lock_appraisal_for_update(db, id)`. The P0.1 router helper now
  delegates to it. `create_new_version` calls it BEFORE
  `source.is_current = False`. `create_scenario` audited — does NOT
  flip source's `is_current`, so no lock added (per build-pack rule).
  Two-session proof: A holds → B `NOWAIT` → `OperationalError`; A
  commits → B acquires.
- **R4 — `deps.py:144` docstring fixed** — no longer lists
  `/password/change` (or any of the now-moved security-critical
  endpoints).
- **R5 — P1.10 destructive Alembic downgrade — Option 1 (NotImplementedError)
  APPLIED (operator decision, 2026-02-13).**
  `0027_default_line_items_backfill.py` downgrade replaced with `raise
  NotImplementedError(...)` + module-docstring note. NO new migration.
  0025 round-trip test retargeted to `0027_default_line_items_backfill`
  so it stops AT (does not execute) 0027's downgrade. Runbook entry at
  `/app/docs/SY_Homes_Future_Tasks.md` §24. The `alembic downgrade --sql`
  CI canary remains backlog.
- **R6 — `CHANGELOG.md` entries spliced** for both Chat 26 (§R7.0b +
  §R7 Batch 1) and Audit Remediation TIER P0 and TIER P1.
- **P0 + P1 test file: 25/25 green.**

### 2026-02-13 — Audit Remediation TIER P0 (v2 build pack) ✓

All four P0 (critical) findings from the Claude-Code audit, re-grounded
to `main`. Working tree only; awaiting operator gate before push. No
schema change. **Warm-DB suite: 920 passed, 2 pre-existing failures
(`test_audit_log.py::TestCsvJsonExport`) + 93 pre-existing errors
(`test_projects.py` FK in `appraisal_scenarios`) — verified pre-existing
by stashing P0 deltas: same 2 failures persist. P0 file itself: 16/16
green in isolation AND inside the full warm-DB run.**

- **P0.1 — Appraisal row lock**: new `_lock_appraisal_for_update`
  helper takes `SELECT ... FOR UPDATE` on the appraisal row + every
  cost line (Pattern-α scope) inside the caller's transaction. Called
  at the top of all 13 mutating handlers. Concurrency proof: session
  A holds the lock → session B's `SELECT FOR UPDATE NOWAIT` raises
  `OperationalError`; A commits → B succeeds.

- **P0.2 — Receipt audit actor + line lock**:
  `_recompute_po_status_after_receipt_change` is now keyword-only on
  `actor_user_id`; both callers pass `user.id`. The audit row no
  longer attributes Status_Change to `po.updated_by` (header's last
  editor) — it attributes to the receipter. The line scan inside the
  helper now `.with_for_update()` so the all-fully-received check
  serialises across concurrent receipts on different lines of one PO.

- **P0.3 — `mfa_pending` typed + locked out of `/password/change`**:
  `tokens.py` `Literal` now enumerates all three token types. The
  `/password/change` dep moved from `get_enrollment_principal`
  (accepts `mfa_pending`) to `get_current_principal` (access-only).
  Live evidence: `/password/change` → 401 with `mfa_pending`;
  `/auth/me` + `/mfa/enroll/start` still 200 with `mfa_pending`.

- **P0.4 — `/mfa/verify` rate limit**: new `mfa_verify_per_user`
  bucket = `(5, 60)` in `rate_limit.LIMITS`. The `enforce(...)` call
  sits **between** the token-type check and the User lookup at
  `auth.py:459`, so malformed / expired tokens 401 first and don't
  consume a slot. 429 carries `Retry-After`. Live evidence: 5 OK →
  6th denied (ok=False, retry > 0).

Carried-forward P1 items (audit-pack §OPERATOR DECISIONS CARRIED
FORWARD) — NOT done in P0:
- `/mfa/disable` + `/mfa/backup-codes/regenerate` still accept
  `mfa_pending` (same shape as the `/password/change` hole pre-P0).
  Same "pre-MFA token shouldn't perform security-critical account
  changes" argument applies.
- Audit P1.10 — destructive Alembic downgrade deletes real user
  data; needs explicit operator decision (patch downgrade vs forward-
  fix) when P1 is scoped.

### 2026-02-12 — Chat 26 §R7 Batch 1 fix-up (live-eyeball gate) ✓

Live operator eyeball found three classes of dead/broken buttons that
the Jest matrix had codified as expected — because both ends of the
matrix were wrong in the same way. Working tree only; awaiting gate.

- **Removed from Batch 1 (now hidden, deferred to Batch 2):**
  `po-actions-edit-btn`, `po-actions-delete-btn`,
  `po-actions-edit-issued-btn`, `po-actions-receipt-btn`,
  `po-actions-receipt-partial-btn`, `po-actions-void-btn`,
  `po-actions-void-issued-btn`. Root causes per ticket:
  * Edit / Delete / Edit-issued / Receipt → target routes don't
    exist; clicks landed on the App.js `*` catch-all `not-found-page`.
  * Void → backend `POVoidBody.reason` is `Field(..., min_length=1)`;
    sending `{}` 422s. The reason dialog ships with R7.6.

- **Slim Batch-1 matrix that DOES ship (verified live via Playwright
  as `test-pm` with spot-check `pos.approve` grant):**
  ```
  draft               → Submit
  pending_approval    → Approve, Reject     (self-approval guard)
  approved            → Issue, Send back    (send-back NOT guarded)
  issued              → Close
  partially_receipted → Close
  receipted           → Close
  closed / voided     → (none)
  ```

- **Regression guard** in `POActionButtons.test.jsx` —
  `deferred-to-Batch-2 buttons must render on NO state × persona`:
  8 states × 4 personas × 7 deferred testids = 32 assertions firing
  every CI run. When Batch 2 wires a button back in, the corresponding
  testid must be removed from `DEFERRED_TESTIDS` in the same commit.

- **Spot-check seed** (`/app/scripts/seed_r7_batch1_pos.py`):
  - Re-run is idempotent: wipes prior POs on the project, restores the
    five-PO matrix (draft / pending×2 / approved×2). PO numbers
    advance (e.g. PO-0006…PO-0010 on second run); IDs change but
    states are restored cleanly.
  - MFA self-heal step disables MFA on every `test-*@example.test`
    user (super-admin enrolment auto-fires on each restart).
  - Spot-check grant: gives `pos.approve` to the Project Manager role
    so `test-pm` can exercise Approve/Reject without an MFA dance.
    Sandbox only — production seeding never invokes this script.

- **Jest**: 57 suites, **387/387 passing** (was 357 → +30 net,
  +32 deferred-button regression assertions − 2 obsolete edit_tier
  assertions). Verified with a fresh `yarn test` post-edit.

### 2026-02-12 — Chat 26 §R7 Batch 1 ✓ Frontend (R7.0b send-back wiring + R7.1 + R7.2 + R7.3)

Frontend-only batch building on R7.0b's already-pushed backend send-back
endpoint. Working tree only — **not** pushed; awaiting operator
consolidated-STOP gate approval.

- **§1 — Send-back wiring (carry-forward from R7.0b)**:
  - `lib/api/purchaseOrders.js` — `sendBackPO(poId, body)` POSTs
    `/v1/purchase-orders/{id}/send-back`; `listPOApprovals(poId)` GETs
    `/v1/purchase-orders/{id}/approvals` (data source for R7.3 panel).
  - `hooks/purchaseOrders.js` — `sendBack` verb in `usePoTransition`
    map. New `usePOApprovals(poId, {enabled})` hook for the panel.
    NB: budget-line cache invalidation on commitment-changing verbs
    (send-back joins approve/issue/void) deferred to R7.6 / Batch 2.

- **R7.1 — Project-Detail Budgets tab-link**:
  - `pages/ProjectDetail.jsx` — `<Link>` to `/projects/{id}/budgets`
    (`data-testid=tab-budgets`), gated by
    `budgets.view || me.is_super_admin`. Routes already resolve to
    `BudgetsList` (not the catch-all). Sidebar `Budgets` entry in
    `AppShell.jsx` **left disabled** per locked decision (a global
    landing page is backlog).

- **R7.2 — `components/po/POActionButtons.jsx`** (new):
  - Refactors the inline action area out of `PurchaseOrderDetail.jsx`
    into a single source of truth.
  - Status × perm matrix incl. **approved** row (Issue / Send back /
    Void). Send-back uses shadcn `Dialog` + `Textarea` with required
    notes; reject also moved to a dialog (was `window.prompt`).
  - Self-approval guard mirrors backend `SelfApprovalForbidden`:
    `po.submitted_by === me.id` hides Approve, shows disabled twin
    with tooltip, hides Reject. **Send-back is NOT subject** — it IS
    the correction path.
  - `edit_tier` (lowercased string from backend) handled
    case-insensitively: `read_only` → no mutating buttons;
    `header_annotation_only` → suppress Edit/Delete only; `full` →
    all per matrix; absent → defensive `read_only` fallback.

- **R7.3 — `components/po/POApprovalPanel.jsx`** (new):
  - Mounts in the PO detail "approvals" tab. Renders iff
    `po.status === 'pending_approval'` AND an open approval row exists
    (resolution === null). The GET endpoint does NOT inline the open
    row, so the panel fetches via `usePOApprovals` (`/approvals` list)
    and picks the open one; the rest become history.
  - Over-budget snapshot table from
    `approval.budget_snapshot` (array of decimal-string overrun lines —
    `Number()` only for display via `fmtGBP`; no arithmetic).
  - Sensitive £ → `SensitiveValue` em-dash for read-only personas.
  - Approve (optional reason) / Reject (required reason). Self-
    approval guard via shared `lib/poSubmitter.js` helper. **Send-back
    is NOT here** — it lives only in `<POActionButtons/>` on the
    `approved` row.

- **Tests** — Jest +44 (**356/356 passing**, was 312):
  - `lib/api/__tests__/purchaseOrders.sendBack.test.js` — api/hook
    wiring URL contract.
  - `pages/__tests__/ProjectDetail.budgetsTab.test.jsx` — tab gating
    (with-perm / without-perm / super-admin / siblings).
  - `components/po/__tests__/POActionButtons.test.jsx` — per-status ×
    per-persona matrix (FULL PM / approver / read-only), approved row,
    self-approval rule, send-back dialog DOM transcript, edit_tier
    handling.
  - `components/po/__tests__/POApprovalPanel.test.jsx` — snapshot
    rendering, panel visibility logic, read-only em-dash, approve /
    reject verbs, creator-cannot-approve, send-back excluded.

- **No backend / migration / RBAC change.** Permissions 102, roles 10,
  alembic head `0034_audit_sendback` (unchanged from R7.0b push).

### 2026-05-22 — Chat 25 R6 v2 ✓ Closing-gap pass (frontend-only)

Second R6 pass to close gaps from the v1 pass that the operator flagged.

- **Expand-All (was missing, now wired end-to-end)**:
  - Toolbar buttons `bg2-expand-all` + `bg2-collapse-all`.
  - Single bulk GET `/v1/budgets/{id}/purchase-orders` hydrates every
    per-line cache via `queryClient.setQueryData(poKeys.budgetLineList(lid), …)`.
  - `useBudgetLinePOs` now has `staleTime: 30s` so seeded data is not
    immediately re-fetched.
  - Jest pin asserts ONE bulk GET → ZERO per-line PO GETs at mount.
- **Sticky cost-code column** on horizontal scroll: leading expand
  cell + cost_code header + cost_code body cell all `position: sticky`
  with backing bg. 6 sticky-attachment hits in
  `BudgetGridV2Desktop.jsx`.
- **Empty / Error+Retry states**: POsSection and ReceiptsSection both
  ship `…-loading`, `…-error`, `…-retry`, `…-empty` testids. Retry
  triggers `refetch()`.
- **A11y**: line expand button has `aria-expanded` + `aria-controls`;
  the expanded panel has `role="region"` + `aria-labelledby`.
  Keyboard Enter/Space work via native `<button>` semantics
  (jest-asserted).
- **Receipt photo thumbnail**: new `ReceiptPhotoThumb` with
  `loading="lazy"`, non-empty `alt` (caption → filename → "Receipt
  photo" fallback), `onError` → swaps to glyph fallback. Future-shaped
  endpoint `/api/v1/receipts/photos/{id}` consumed; backend photo
  router lands later.
- **Warm-expand timing**: cache-hit mount measured at ~6ms (budget
  500ms, headroom 80x).
- **Jest**: 53 suites, **324 tests passing** (was 313; +11 R6 v2 tests).
- **Bundle**: main bundle **385.29 kB gz** (gzip -9) / **395.25 kB gz**
  (CRA) — same headroom as v1.

### 2026-05-22 — Chat 25 R6 ✓ Inline Expandable Budget-Line Grid (frontend)

Phase A0 → 4 complete. R6 ships the Buildertrend-style inline expandable
budget-line drilldown against the R5.5 backend endpoints landed in the
prior session.

- **New components** (`src/components/budgets/grid/PerLineTransactionDrilldown/`):
  - `BudgetLineExpandedRow.jsx` — orchestrates breakdown + POs + Bills
  - `POsSection.jsx` — lazy-fetches `/v1/budget-lines/{id}/purchase-orders` (R5.5)
  - `ReceiptsSection.jsx` — nested per-PO `/v1/purchase-orders/{id}/receipts` (P0.3)
  - `BillsPlaceholder.jsx` — static placeholder (Documents & Compliance later track)
- **URL state**: `?expanded=line-id,line-id` on `BudgetDetail`, toggled via
  `setSearchParams(..., { replace: true })` so deep-links don't pollute
  history. Legacy `?line=` / `?drilldown=` are rewritten on mount.
- **A11y**: dedicated expand button per line with `aria-expanded` +
  `aria-controls`; panel mounts as `role="region"` with `aria-labelledby`.
- **RO gating**: `<SensitiveValue/>` renders `—` when the server returns
  `null` for `gross_total` / receipt amounts (already verified at the
  backend by R5.5 RO tests).
- **Deleted**: `BudgetGridDrilldown.jsx`, `POsSectionStub.jsx`,
  `VariationsSectionStub.jsx`, `BillsSection.jsx`, `BillStatusBadge.jsx`
  and their tests (`Drilldown.test.jsx`, `BillsSection.test.jsx`).
- **Jest**: 52 suites, **313 passing** (was 312; +11 R6 tests, +2 R5.5
  URL-pins, ‑10 stale stubs).
- **Bundle**: main **385.26 kB gz** (gzip ‑9 reported) / **395 kB gz**
  per CRA; ceiling 437 kB → **>40 kB headroom**.
- **Jest mock**: `src/__mocks__/react-router-dom.js` extended with a
  driveable `useSearchParams`/`__setSearchParams` so future URL-state
  tests don't need a real router stack.
- 0 dangling references for `BudgetGridDrilldown` / `POsSectionStub` /
  `VariationsSectionStub` / `BillStatusBadge` / legacy `BillsSection`.

### 2026-05-20 — Chat 24 ✓ CLOSED (R0–R5, Prompt 2.5)

Triage closing artefact filed at `docs/chat-summaries/chat-24-closing.md`. R0–R5 shipped, independently verified against real PostgreSQL 16, pushed to `main`. R6–R9 deferred to Chat 25.

- Alembic head `0033_po_receipts` (was 0028; +5 migrations 0029–0033).
- Permissions 102 (was 86; +16: 11 `pos.*` + 5 `suppliers.*`), roles 10 (unchanged).
- Backend pytest 875 passing (Emergent) / 55 PO+approval+receipt suites green (triage clean-DB).
- Jest 312 passing across 53 suites; 25 URL-contract pins.
- Main bundle 395.26 kB gz (cap 437, ~42 kB headroom); all R5 in lazy `suppliers-po` chunk.
- 6 in-flight defects fixed (D1–D6): numbering concurrency race, bad import, isolation_level→autocommit_block in 0029/0031/0032, notification enum, `read_only.suppliers.view` backfill, legacy guardrail rebaseline.
- 4 Build Pack deviations accepted (E1–E4): inline photos, no documents table, role-code mapping, no `pos.reopen`.
- Future_Tasks added: §16 PO approval amount thresholds, §17 reopen-from-closed, §18 cold-start vs 0018 guard (P1), §19 unified documents table, §20 multipart photo streaming.

**Carried as standing rules** ("Hard lessons"):
1. "Committed to main" ≠ pushed. Always Save-to-GitHub + triage re-pull before sign-off.
2. Backend STOP reports must include a real clean-DB migration run.
3. "Tests passing" can mean the suite never ran — confirm count + collection.
4. Demand printouts, not summaries.
5. Verify-don't-trust caught everything that mattered. Keep it.
6. Recommend a Claude Code phase-checkpoint pass on R1–R7 before Track 2 closes.

**Chat 25 job 1**: E2E lifecycle smoke (suppliers→prefix→PO→submit→approve→issue→partial→full→close, + void) against pushed code on live preview — promotes R5 from provisional to confirmed. Then R6 inline grid, R7 transitions/approvals UI, R8 tests sweep, R9 close-out.

### 2026-02-20 — Chat 24 R5 ✓ PO frontend (Prompt 2.5) — OPERATOR-VERIFICATION-PENDING

- Seven new routes wired under React.lazy + `suppliers-po` webpack chunk: `/suppliers`, `/suppliers/new`, `/suppliers/:id(/edit)`, `/projects/:id/purchase-orders(/new|/:po_id)`, `/projects/:id/settings/numbering`.
- API clients: `lib/api/{suppliers,purchaseOrders,numberPrefixes}.js` — every endpoint under `/v1/...` exactly once.
- Hooks: `hooks/purchaseOrders.js` — TanStack Query with nested keys per Build Pack §5.6.
- Components: `<POStatusPill/>` (brand-token pills — first real brand application), `<SensitiveValue/>` (em-dash fallback, defence-in-depth), `<SupplierSelect/>` (filter combobox + create-new), `<POLineEditor/>` (live qty×rate=net + totals strip).
- Permissions: `lib/poCapability.js` — single source of truth; `nextActionsForStatus()` drives lifecycle button rendering.
- Tailwind: extended `sy-teal/sy-orange/sy-grey` palettes with 100/200/600/700/800 shade ramps.
- **URL-contract pins: 22 (≥ 12 floor)** in `lib/api/__tests__/po-url-contracts.test.js`.
- **Whole Jest suite: 312 passed** (was 251 pre-R5, +61). 53 suites green.
- **`yarn build` clean. Main bundle 395.26 kB gz (cap 437 kB, ~42 kB headroom).** R5 surface in own chunk: 10.43 kB gz.
- Future_Tasks logged: §19 unified documents table (post-Documents track), §20 multipart streaming endpoint nice-to-have.

### 2026-02-20 — Chat 24 R4 ✓ PO Receipts backend (Prompt 2.5) — OPERATOR-VERIFICATION-PENDING

- Migration `0033_po_receipts`: 3 tables + recompute trigger + audit/notification enum extensions (via `autocommit_block` helper, no `isolation_level` regression). Backfills `read_only.suppliers.view` to close a drift hole exposed by the 0025 round-trip guardrail.
- Models: `PurchaseOrderReceipt`, `PurchaseOrderReceiptLine`, `PurchaseOrderReceiptPhoto`.
- Service `po_receipts.py`: status guard (issued|partially_receipted), future-date rejection, 30-day backdate requires `pos.edit_issued`, cumulative≤ordered guard, photo de-dup, auto status transition (issued ↔ partially_receipted ↔ receipted), Receipt audit, optional notifications.
- Endpoints: `GET/POST /purchase-orders/{id}/receipts`, `GET/PATCH/DELETE /receipts/{id}` — all under `/api/v1/`.
- Money invariant: `committed_value` unchanged across receipt create + full + delete (asserted by 2 integration tests).
- Tests: 11 unit + 24 integration = 35 R4 tests, all green. Whole suite: 875 passed, 0 failed, 0 errors (ex pre-existing `test_projects.py`).
- Live perm count: 102 (unchanged — R4 reuses `pos.receipt` from R2).
- Clean-DB bootstrap reaches `0033_po_receipts`; downgrade -1 / upgrade round-trip clean.

### 2026-02-20 — Chat 24 R3 ✓ Live-DB verification PASSED
- Provisioned local Postgres (`/app/backend/.env DATABASE_URL=postgresql+psycopg://syhomes:syhomes_dev@127.0.0.1:5432/syhomes`).
- Ran `alembic downgrade -4` then `alembic upgrade head` (0028 → 0032) — clean, zero errors. 0029, 0031, 0032 already used `op.get_context().autocommit_block()` for `ALTER TYPE ADD VALUE`; verified reversible.
- `SELECT count(*) FROM permissions` → **102** (live DB, not catalogue).
- All R1/R2/R3 integration + unit suites green: **84/84 pass** (test_purchase_orders_api, test_purchase_orders_unit, test_po_approvals_api, test_po_approvals_unit, test_number_prefixes, test_suppliers). Includes TestConcurrentNumbering (8 threads, sequential PO-0001..PO-0008, zero unique-constraint violations).
- Defects fixed during verification:
  * **D1 (race)** `po_numbering.allocate_next_number`: `SELECT FOR UPDATE` acquired row lock but SQLAlchemy identity-map served *cached* `next_sequence`, so concurrent POSTs computed the same PO number and tripped `ux_po_project_number`. Added `.execution_options(populate_existing=True)`.
  * **D2 (import)** `routers/number_prefixes._resolve_project`: wrong import `app.models.entities` → `app.models.entity` (singular). Without this, the v1 prefix endpoints raised `ModuleNotFoundError` under the tenant-scope path.
  * **D3 (test)** `tests/test_number_prefixes._get_primary_entity_id`: dropped reference to non-existent `entities.is_archived` column.
- Future task logged (P1): cold-start bootstrap blocked by 0018 guard (docs/SY_Homes_Future_Tasks.md §18).

### 2026-05-20 — Chat 24 R3 ✓ PO Approvals + commitment recompute (Prompt 2.5) — OPERATOR-VERIFICATION-PENDING
- **Migration `0032_po_approvals.py`:**
  * po_approval_resolution ENUM (approved, rejected)
  * `purchase_order_approvals` table with budget_snapshot jsonb,
    resolution_consistency CHECK, reject-requires-notes CHECK, and
    partial unique idx ux_poa_one_open_per_po (at most one open
    approval row per PO)
  * `fn_budget_line_recompute_commitments(uuid)` — canonical
    commitment-recompute SQL function
  * Trigger `trg_po_status_commitments` AFTER UPDATE OF status on
    purchase_orders → recomputes commitments on every linked line
  * Trigger `trg_pol_commitments_on_change` AFTER INSERT/UPDATE/DELETE
    on purchase_order_lines → handles line reassignment (OLD + NEW)
- **Model `PurchaseOrderApproval`** with PO_APPROVAL_RESOLUTIONS.
- **Services:**
  * `po_commitments.py` — over-budget gate (`evaluate_budget_overrun`),
    snapshot builder (`build_budget_snapshot`). Uses LIVE column names
    confirmed against `BudgetLine` model: current_budget,
    committed_value, actuals_to_date.
  * `po_approvals.py` — submit_po_with_budget_gate (3 branches:
    within-budget+!approval=auto-issue, within-budget+approval=
    auto-approved row, over-budget=pending_approval+row), approve_po,
    reject_po (notes required), unlock_po (approved→draft +
    notify prior approver), list_pending_approvals (with
    self-submitter hide). SELF-APPROVAL GUARD enforced — submitter
    cannot approve OR reject own PO (403 `po/self-approval-forbidden`).
- **Router:** 6 new endpoints under `/api/v1/`:
  * POST /purchase-orders/{id}/approve  → pos.approve
  * POST /purchase-orders/{id}/reject   → pos.approve
  * POST /purchase-orders/{id}/unlock   → pos.edit
  * GET  /purchase-orders/{id}/approvals → pos.view
  * GET  /projects/{id}/approvals/pending → pos.approve
  * GET  /approvals/pending → pos.approve
  * Also: existing POST /purchase-orders/{id}/submit replaced with
    budget-gated implementation. Total PO+approval routes mounted: 15.
- **Notifications:** Approval_Requested broadcast to all tenant
  approvers (except submitter) on over-budget submit;
  Approval_Decision to submitter on approve/reject; to prior approver
  on unlock.
- **Docs:** `docs/engineering-invariants.md` updated with the
  commitment contract (§R3) and self-approval guard rule.
- **Tests (25 total):**
  * `test_po_approvals_unit.py` — 8 unit tests verified PASSING
    in-container (budget gate math + snapshot aggregation + exception
    types).
  * `test_po_approvals_api.py` — 17 integration tests
    OPERATOR-VERIFICATION-PENDING (5 budget gate G3.1-G3.5,
    4 approve/reject/unlock G3.6-G3.9, 2 self-approval,
    5 commitment matrix, 1 pending list visibility).
- **Scope honoured:** Receipts → R4. Frontend → R5/R6. Approval-amount
  thresholds → future tracks (logged §15).
- **Commit:** TBD.

### 2026-05-20 — Chat 24 R2 ✓ Purchase Orders core (Prompt 2.5) — OPERATOR-VERIFICATION-PENDING
- **Migrations:**
  * `0030_purchase_orders.py` — po_status enum (8 states), purchase_orders +
    purchase_order_lines tables, fn_po_recompute_header_totals trigger,
    is_fully_receipted Computed column, partial unique idx on
    (project_id, prefix_id, sequence) for forensic reconstruction.
  * `0031_po_permissions.py` — 12 pos.* permissions, role grants.
- **Models (`app/models/purchase_orders.py`):** PurchaseOrder + PurchaseOrderLine
  with Status constants exported for state machine + edit-tier guard.
- **Services:**
  * `po_numbering.py` — atomic next-sequence allocation with SELECT FOR
    UPDATE on the prefix row.
  * `po_authz.py` — DUAL responsibility per build pack §4.5:
    Pattern α tenant/project scoping AND edit-tier guard
    (EditPermission.FULL / HEADER_ANNOTATION_ONLY / READ_ONLY with
    check_can_edit_fields).
  * `po_transitions.py` — state machine: submit, issue, void, close.
    Approval (R3) and receipt (R4) transitions declared in
    ALLOWED_TRANSITIONS but not yet driven.
  * `purchase_orders.py` — CRUD + transitions; every CUD writes audit_log
    with field-level diff; pricing fields gated by `pos.view_sensitive`.
- **Router (`app/routers/purchase_orders.py`):** 9 endpoints under
  `/api/v1/`:
  GET/POST list+create, GET/PATCH/DELETE detail,
  POST submit/issue/void/close.
- **RBAC:** PERMISSION_CATALOGUE += 12 pos.* perms; role mappings for
  super_admin (all 12), director (all 12), finance (9 incl. approve/void/close),
  project_manager (6 incl. submit/void), site_manager (view + receipt).
- **Tests (47 total):**
  * `test_purchase_orders_unit.py` — 33 unit tests verified PASSING
    in-container (state-machine 16 + edit-tier matrix 17).
  * `test_purchase_orders_api.py` — 14 integration tests
    OPERATOR-VERIFICATION-PENDING (require live PG): 6 numbering +
    4 CRUD + 4 transitions.
- **Scope honoured:** Approval flow → R3. Receipt flow → R4.
  Bills entity, PO templates, multi-currency, approval thresholds → future
  tracks. No frontend changes (R5/R6 scope).
- **Commit:** `1012e18 Chat 24 R2: Purchase Orders core (Prompt 2.5)`.

### 2026-05-19 — Chat 24 R1 ✓ Suppliers + Project Number Prefixes (Prompt 2.5)
- Migration 0029_suppliers_prefixes, models `suppliers.py` +
  `number_prefixes.py`, services + routers, 9 tests, all under /api/v1/.
- Commit `357a939`.

### 2026-05-19 — Chat 24 R0 ✓ Pre-flight cleanup
- `LineItemsPanel.jsx` → `LineItemsBreakdown` swap in `LineDrawer.jsx`.
- Supervisor `[program:backend]` template re-applied for self-healing.
- Commit `9070a80`.

### 2026-05-19 — Chat 23 Build Pack A CLOSED ✓ (R1–R10 complete · 38/39 acceptance gates · 1 documented partial)
- **R9/R10 closure:** All R-sections shipped, full test suites green at close (backend **843**, Jest **250**), bundle main **395.1 kB** (cap 437 kB, headroom 41.9 kB), permissions=86, roles=10, alembic head `0028_user_preferences_table`.
- **G38 partial:** v1 `BudgetLinesGrid.jsx` + `SortableLineRow.jsx` deleted; `LineItemsPanel.jsx` survives because it's still mounted by `LineDrawer.jsx` for the items-tab focus contract. Refactor deferred to Future_Tasks §13 (P2).
- **G39:** `/app/docs/chat-summaries/chat-23-closing.md` written — full gate-by-gate accounting + deferral list.
- **Operational debt picked up:** missing `/root/.emergent/on-restart.sh` reinstalled with Step-8 re-seed extension (eliminated the recycle-data-loss class of issue). MFA role-level enforcement documented in `test_credentials.md`. R7 seed pollution workflow documented.
- **Deferred (out of Build Pack A):** Playwright E2E adaptation (Build Pack A-followup), mobile shell rework (Future_Tasks §12, P1), `LineItemsPanel.jsx` deletion (§13, P2), `/api` vs `/api/v1` audit closure (§11, P1).
- **Currently:** Build Pack A is mergeable on operator signal.

### 2026-05-19 — Chat 23 Build Pack A §R8 Mobile read-only card list ✓ (STOP gate #9 partial: functional ✓, shell-UX inadequate → Future_Tasks §12)
- **R8.1 `BudgetGridMobileReadOnly`** (full replacement of R3 stub): stacked header tiles (new `stacked` prop on `BudgetGridHeaderTiles`) + search input (only mobile filter) + card list rendering code + description + current budget + variance badge. Empty-state for zero matches.
- **R8.2 `MobileLineDetailDrawer`**: bottom-anchored `Sheet`, full-viewport. All line fields READ-ONLY (Original/Current/Approved changes/Actuals/Committed/FFC/FTC/Variance/Variance %), sensitive fields gated by `budgets.view_sensitive`. **Notes EDITABLE on mobile** (NotesCell reused with `canEdit = budgets.edit perm`). Per-line transaction drilldown reused (POs stub + Variations stub + Bills live).
- **Explicit NON-features pinned by tests:** NO bulk actions on mobile · NO toolbar (column-visibility/saved-views/presets absent) · NO drilldown row-expand in the list (transactions only inside the drawer).
- **Tests:** Jest 235 → **250** (+15: routing, structure, search, drawer flow, Notes editability gates, sensitive-field gating).
- **Bundle:** main unchanged 395.1 kB · budgets chunk 22.54 → **23.89 kB gz** (+1.35 kB). 41.9 kB headroom.
- **STOP gate #9 outcome:** functionally complete, but operator flagged the surrounding shell (sidebar dominates, no dismiss, content cramped) — logged as Future_Tasks §12, dedicated build pack sized after R10.

### 2026-05-19 — Chat 23 Build Pack A §R7.5 Path-prefix drift audit ✓
- **Fixed three silent-404 callers** that the §R7 spot-check exposed: `useCostCodes` (was `/v1/projects/.../cost-codes`), `useEntities` in `PromoteForm.jsx`, `useProjects` in `ProjectPicker.jsx`. All three correctly route to `/api/...` (no `/v1/`) — confirmed against backend mount table in `server.py:138-160`.
- **`buildCostCodeMap` keyed by `cost_code_id`** (not `id`) so the FK in `budget_lines.cost_code_id` matches the lookup. Backward-compatible fallback to `id` for minimal test fixtures.
- **CSV cost-code resolution** (regression caught by operator spot-check): `buildCsvText` takes `costCodeMap` and special-cases `cost_code` column (TanStack `accessorFn` form ≠ `accessorKey`, so the previous fall-through emitted blanks).
- **Regression pins:** URL contract per fixed hook (positive + hard negative on `/v1/`), buildCostCodeMap key contract, CSV cost-code FK→code resolution, on-screen cell rendering pin (`BudgetGridV2-CostCodeRender.test.jsx`).
- **Future_Tasks §11** logged with full audit survey (P1 — silent 404 with empty-fallback is highest-risk bug class).

### 2026-05-19 — Chat 23 Build Pack A §R7 Bulk delete + CSV export ✓ (STOP gate #8)
- **R7.1 — Row selection** already line-only (groups + items not selectable) per the R3 `enableRowSelection` predicate. Confirmed no group/item rows render the select checkbox.
- **R7.2 — `BulkActionsBar.jsx`** new file. Renders between header tiles and toolbar when ≥1 line selected. Shows count + Export CSV + Delete selected + Clear. Auto-hides Delete when `canEdit=false` OR `editable=false` (Locked/Closed/Superseded). Over-cap warning + disabled Delete when >100 selected.
- **R7.3 — Bulk delete fan-out.** New backend endpoint `DELETE /api/v1/budget-lines/{line_id}` (singular; NO bulk endpoint per locked decision). Frontend loops sequential `deleteBudgetLine(id)` calls capped at 100; **live progress bar** swaps in while running showing "Deleted X of N…" (and "(K failed)" suffix on errors). One audit row per delete (metadata.kind=`line_delete`). Cache invalidation fires ONCE at the end. Partial-failure toast distinguishes total-fail vs partial-fail vs success.
- **R7.3 confirm dialog** — controlled `BulkDeleteConfirmDialog.jsx` wrapping shadcn `AlertDialog` directly (existing `ConfirmDialog` is uncontrolled — wrong shape for imperative open). sy-orange destructive class preserved.
- **R7.4 — Inline RFC-4180 CSV** at `lib/csv.js`: exactly the 5-line `toCsv` from the Build Pack + a `downloadCsv(text, name)` helper using Blob + ephemeral object URL. **NO papaparse**. The export-button reads `table.getVisibleLeafColumns()` and drops `select`/`expand`/`actions` columns. Display columns (variance_to_forecast, forecast_profit, forecast_margin_pct) compute their numeric value inline so the CSV captures the signal instead of JSX.
- **Sensitive-field gating in CSV** verified by Jest: `forecast_profit` + `forecast_margin_pct` columns are not even created for users without `budgets.view_sensitive` (R3.2 contract), so they cannot land in the CSV even if a future bug forced them visible. Pinned by `BulkActionsBar.test.jsx::"non-sensitive user CSV excludes forecast_profit and forecast_margin_pct"`.
- **Backend tests:** 837 → **843** (+6: 204/404/403/409/audit/total-recompute).
- **Frontend tests:** 204 → **223** (+19: 10 RFC-4180 csv unit + 9 BulkActionsBar render/gating/fan-out).
- **Bundle:** main 395.07 → **395.09 kB gz** (+22 B); budgets chunk 20.95 → **22.54 kB gz** (+1.58 kB). Headroom against 437 kB cap: **41.91 kB**.
- **Currently at:** STOP gate #8 — awaiting operator review before R8 (mobile card list + Notes-editable).

### 2026-05-19 — Chat 23 Build Pack A §R6 Saved Views + autosave ✓ (STOP gate #7)
- **R6.1 hooks** (`hooks/userPreferences.js`) — 5 hooks against `/api/v1/me/preferences/{surface}`:
  - `useUserPreferences` — GET snapshot, no refetch-on-focus, `staleTime=Infinity` so initial column-resize drafts aren't clobbered.
  - `useSetCurrentPreference` — PUT autosave, NO cache write (C2 audit fix preserved; signature is `(_data, _variables)`, NOT `arguments[0]`).
  - `useCreateSavedView` — POST + prepend to cached views.
  - `useUpdateSavedView` — PUT + replace in cached views.
  - `useDeleteSavedView` — DELETE + filter from cached views.
- **R6.2 autosave** — 500ms debounced `useEffect` in `BudgetGridV2Desktop` that fires `setCurrentMut` on any change to `{columnVisibility, columnOrder, sorting, filters}`. Initial hydration gated by `hydratedRef` so it does NOT trigger autosave (load-storm guard).
- **R6.3 `SaveViewDialog`** — name validated 1-128 chars; 409 conflict → "Name already in use" toast (dialog stays open); success → success toast + dialog closes.
- **R6.4 `ManageViewsDialog`** — list + rename + delete. Rename = delete-then-create with rollback recreate on half-failure (recovery toast if recreate ALSO fails). Delete fires directly because the dialog is itself a confirmation surface.
- **R6.5 hydration** — first snapshot fetch applies `current.payload.{columnVisibility,columnOrder,sorting,filters}` if non-empty; otherwise keeps `INITIAL_COLUMN_VISIBILITY`. Re-runs gated by `hydratedRef.current` so a refetch never clobbers in-flight user edits.
- **`ViewPresetsDropdown`** extended: 4 starter presets (Profit hidden when `!canViewSensitive`) → divider → saved views (one item per `prefs.views[i].name`) → divider → "Save current view…" + "Manage saved views…" footer.
- **API client** new file `lib/api/userPreferences.js` — 6 typed wrappers (getSnapshot / putCurrent / create / update / delete).
- **Scoped deviations log** — new `docs/chat-summaries/chat-23-closing.md` tracking 3 documented deviations: R3.9b source field (gdv_total ↔ "sale_price"), R5.1 textarea↔input, R6.2 debounce 500ms confirmed as per-Build-Pack.
- **Tests:** Jest 196 → **204** (+8). Hook contracts 6 + grid R6 wiring 2.
- **Bundle:** main 395.07 kB (+22 B); budgets chunk 20.95 kB (+2.18 kB). Headroom 41.93 kB.
- **Currently at:** STOP gate #7 — awaiting operator review before R7 (Bulk delete + CSV export).

### 2026-05-19 — Chat 23 Build Pack A §R5 NotesCell upgrade ✓ (STOP gate #6)
- **`NotesCell.jsx` rewrite**: 600ms debounce; rapid typing coalesces to a single PATCH; **Enter** commits immediately, **Shift+Enter** = newline, **Escape** reverts + cancels pending debounce, **Blur** commits immediately; same-value no-op guard; empty string → `notes: null`; **maxLength=500** enforced via textarea attribute; soft counter appears at ≥450 chars.
- **Optimistic + rollback**: leverages existing `usePatchBudgetLine.onMutate/onError`; NotesCell additionally restores its own `committedRef` so the next entry into edit mode shows the pre-failed value. **`sonner.toast.error`** fires on network failure with the server message.
- **Grid wiring**: `BudgetGridColumns.makeColumns` no longer takes `onUpdateNotes` — it forwards `lineId + budgetId` so the cell owns its own mutation. `BudgetGridV2Desktop` dropped the wrapper closure + the redundant `usePatchBudgetLine` import.
- **Tests:** Jest 184 → **196** (+12 NotesCell cases pinning the entire R5 contract — keystroke debounce, Enter/Shift+Enter/Escape/Blur, null-on-empty, no-op guard, counter, maxLength attr, network-failure rollback + toast).
- **Bundle**: main 395.05 kB unchanged; budgets chunk 18.58 → 18.77 kB (+194 B). Cap 437. Headroom **41.76 kB**.
- **Mobile note**: NotesCell IS mobile-editable per Build Pack §R5; the current mobile stub doesn't yet surface it. Reusing this same NotesCell unchanged in the R8 mobile card list.
- **Currently at:** STOP gate #6 — awaiting operator review before R6 (Saved Views CRUD UI + autosave wiring against the R1.4 backend).

### 2026-05-19 — Chat 23 Build Pack A §R4 BudgetGridDrilldown ✓ (STOP gate #5)
- **R4.1 LineItemsBreakdown** (editable 4-type item editor; description/amount/notes inline + `+ Add item` + delete-with-confirmation using `bg-sy-orange` for the destructive confirm).
- **R4.2 / R4.3** PO + Variations empty-state stubs pointing to Prompts 2.5 / 2.6.
- **R4.4 BillsSection LIVE** (6-col table fed by `useActualsForBudgetLine`). Confirmed param name `budget_line_id` (NOT `line_id`) against `routers/actuals.py:65` before wiring. New `BillStatusBadge` with 5-state semantic colour map (Draft/Posted/Paid/Disputed/Void → slate/sky/emerald/rose/zinc).
- **R4.5 BudgetGridDrilldown** wrapper. Mounted via colspan row directly under each expanded line in `BudgetGridV2Desktop` (items no longer attached as flat TanStack sub-rows).
- **3 confirms answered (operator R4 questions)**:
  1. `appraisal.gdv_total` IS the aggregate development revenue (Σ unit.qty × price_per_unit per `app/services/appraisal_calc.py:144-148`). Not per-unit. ✓
  2. `LineDrawer.jsx` retained (482 lines, unchanged). Actions menu still routes non-Notes edits to it. ✓
  3. Test rename: `PM_EMAIL` → `NON_SENSITIVE_EMAIL = test-readonly@example.test`. PM has `view_sensitive`; only `test-readonly` does not. No production rename, just fixture targeting. ✓
- **Future_Tasks §10** logged: MFA-on-test-users runbook is operational debt (P2). Need a `--test-fixture` middleware bypass for `*@example.test` in non-prod envs.
- **Tests:** Jest 172 → **184** (+12: BillsSection 3, Drilldown stubs + BillStatusBadge 7, budgetCategoryGroup regression-guard updated). Backend unchanged (no backend changes in R4).
- **Bundle:** main 395.05 kB gz (+0.08 from R3), budgets chunk 18.58 kB gz (+1.61). Cap 437. Headroom 41.95 kB.
- **Currently at:** STOP gate #5 — awaiting operator review before R5 (Notes inline-edit upgrade: debounce + audit).

### 2026-05-19 — Chat 23 Build Pack A §R3 BudgetGridV2 ✓ (STOP gate #4)
- **R3.9b backend** (`app/routers/budgets.py`): `_attach_provisional_allocation(db, budget, include_sensitive)` computes per-line `appraisal.gdv_total / len(lines)` 2dp; emitted as `_allocated_sale_price_provisional` on every line ONLY when `budgets.view_sensitive`. Underscore-prefix = "computed, not stored". Source field = `gdv_total` (no literal `sale_price` column exists). 4 new tests passing.
- **R3.1 component tree** — 12 new files under `frontend/src/components/budgets/grid/`:
  - `BudgetGridV2.jsx` — top-level (mobile/desktop chooser).
  - `BudgetGridV2Desktop.jsx` — TanStack Table + filter→group→sort pipeline + drag-reorder (sort-gated).
  - `BudgetGridMobileReadOnly.jsx` — R8 stub (card list).
  - `BudgetGridToolbar.jsx` — 5 filters (search, categories, variance band, only-actuals, only-variance) + views menu + column toggle.
  - `BudgetGridHeaderTiles.jsx` — 5 totals (3 hide for non-sensitive).
  - `BudgetGridColumns.jsx` — 12 cols, 6 default-visible; Profit/Margin conditional on `view_sensitive`.
  - `VarianceCell.jsx`, `MoneyCell.jsx`, `NotesCell.jsx`.
  - `ViewPresetsDropdown.jsx` — Quick/Standard/Full/Profit (Profit hidden if not sensitive).
  - `ColumnVisibilityMenu.jsx`.
  - `SORT_KEY_MAP.js` — id→backend translation + `computedLineValue` for 3 synthetic columns. Dev-mode `console.warn` on miss.
- **R3.5 grouping** — new `lib/budgetCategoryGroup.js` with 9-prefix `CATEGORY_BY_PREFIX`.
- **R3.6 default expansion** — categories open on first render; items closed.
- **R3.4 heat-map** — emerald/amber/rose semantic colours; brand `sy-teal`/`sy-orange` NOT used for variance (operator brand-convention check ✓).
- **R3.8 sort + drag-reorder** — TanStack sort applied via `SORT_KEY_MAP`; drag-reorder kept from v1 and disabled when `sorting.length > 0`.
- **R3.9 gating** — `_allocated_sale_price_provisional` stripped from non-sensitive responses; Profit/Margin columns aren't even created for those users.
- **Inline edit** — Notes ONLY (Q7). All other field edits route through the kept-from-v1 `LineDrawer`.
- **Wiring** — `pages/projects/BudgetDetail.jsx` swaps `BudgetLinesGrid` → `BudgetGridV2`.
- **Bundle:** main 394.97 kB gz (+0.17 over R2), budgets chunk 16.97 kB gz (+4.68). Cap 437 kB. Headroom **42 kB** preserved.
- **Tests:**
  - Backend 833 → **837** (+4 R3.9b cases).
  - Frontend Jest 151 → **172** (+21: VarianceCell 5 / budgetCategoryGroup 7 / SORT_KEY_MAP 8 + the original 1).
- **Currently at:** STOP gate #4 — awaiting operator review before R4 (per-line drilldown: BillsSection live, POs/Variations stubs).

### 2026-05-19 — Chat 23 Build Pack A §R2 frontend code-split ✓ (STOP gate #3)
- **Pre-flight verified:**
  - Full backend pytest run: **833 passed / 0 failed / 0 errors / 122.86s** (post fresh bootstrap; the prior session's ~93 errors were stale-state artifacts from a broken prior bootstrap, not real regressions).
  - G33 permissions=86 ✓ (unchanged); G34 roles=10 ✓ (unchanged).
  - `git status` clean — no auto-URL changes to ride along.
- **R0.3 / R2.1** — `@tanstack/react-table@^8.20.0` already present in `frontend/package.json`. No install needed.
- **R2.2** — `frontend/src/App.js`: `BudgetsList` + `BudgetDetail` converted from eager imports to `React.lazy` with the shared `webpackChunkName: "budgets"` magic comment; route elements wrapped in `<React.Suspense fallback={…Loading…}>` mirroring the existing AICapture pattern. (commit `c8acbb4`)
- **Bundle deltas after R2.2:**
  - `main.js`: **424.17 → 394.80 kB gz** (-29.37 kB — 3× the G11 ≥10 kB target)
  - New chunks: `budgets.a76cfc20.chunk.js` 12.29 kB + `981.chunk.js` 18.20 kB
  - Headroom against the 437 kB cap: **42.20 kB** before §R3 ships Grid v2.
- **Jest:** 151/151 passing (33 suites, 23.8s) — no test changes needed.
- **Fix-ups landed alongside (commit `f0c14a0`):**
  - `test_bootstrap.py::test_alembic_heads_helper_returns_single_head` — sentinel `0027_` → `0028_` per the chat-15 §3 convention now that R1.4 advanced the head.
  - `test_migration_0025_actuals.py::test_alembic_head_is_0025_actuals` — same one-character-class head bump.
  - `test_budgets_default_items.py::test_new_version_copies_items_verbatim_no_autocreate` — explicit `db_session.rollback()` before raw-SQL cleanup so the LIFO-order fixture finaliser doesn't deadlock on the FOR-UPDATE lock the test acquired via `new_version`.

### 2026-05-18 — Chat 23 Build Pack A §R1 backend ✓ (STOP gate #2)
- **R1.1 — Variance band update (commit `98ac673`).** `VARIANCE_AMBER_PCT` 5→0; `VARIANCE_RED_PCT` 15→10. `_classify_variance` operator flipped to use `>=` for Red. 6 new fence-post tests in `test_budgets_variance_bands.py` (-5/0/0.001/9.999/10/25 → Green/Green/Amber/Amber/Red/Red).
- **R1.2 — Auto-create 4 default `budget_line_items` on every new `budget_line` (commit `d990bb3` initial + `ba25b65` fix).** `DEFAULT_LINE_ITEMS = ("Materials","Labour","Equipment","Subcontractor")` at `display_order` 0-3, `amount=0`. `_create_default_items` is idempotent (skips when line already has items). Wired into `create_line` (services/budget_lines.py) and `create_from_appraisal` (services/budgets.py). `new_version` intentionally does NOT call the helper — copies source items verbatim. 5 new tests in `test_budgets_default_items.py` covering constant, service-level create, idempotency, and new_version copy semantics.
- **R1.3 — Migration `0027_default_line_items_backfill` (commit `2725bf1`).** Idempotent backfill: SELECT zero-item lines via LEFT JOIN; INSERT 4 defaults at amount=0. Emits a single `Seed_Run` audit row with `metadata.kind='data_backfill'` + row/item counters. Downgrade removes items matching the exact 4-label + amount=0 + display_order 0-3 shape. 4 tests in `test_migration_0027_backfill.py`. Build Pack §R1.3 spec slug was `0027_budget_line_items_backfill`; operator confirmed canonical name stays `0027_default_line_items_backfill` (one-char-class drift, no rename).
- **R1.4 — `user_preferences` table + 6 endpoints (commit `09d3911`).** Migration `0028_user_preferences_table`: id/user_id/surface_key/name/payload JSONB/created_at/updated_at; FK users.id CASCADE; two partial unique indexes (`name IS NULL` slot = 1 current per user/surface; `name IS NOT NULL` slot = 1 named view per user/surface/name); `set_updated_at` trigger. Service `app/services/user_preferences.py` exposes get_current/set_current/list_views/get_view/create_view/update_view/delete_view with ConflictError/NotFoundError. Router `app/routers/user_preferences.py` mounts under `/api/v1/me/preferences/{surface_key}` with 6 endpoints: GET snapshot, PUT autosave (NOT audited), GET/POST/PUT/DELETE named views (audited Create/Update/Delete). 16 API tests + 3 migration smoke tests = 19 new passing.
- **Test counts after R1 (sample):**
  - `test_budgets.py` 76/76 passing
  - `test_budgets_default_items.py` 5/5
  - `test_budgets_variance_bands.py` 6/6
  - `test_migration_0027_backfill.py` 4/4
  - `test_migration_0028_user_preferences.py` 3/3
  - `test_user_preferences_api.py` 16/16
- **Alembic head:** `0028_user_preferences_table`.
- **Currently at:** Build Pack STOP gate #2 — awaiting operator review before R2 (frontend code-split + TanStack Table install + Grid v2 build).

### 2026-05-18 — Chat 22 CI pipeline hardening ✓ CLOSED
- **Anchor (Future_Tasks §3, open since Chat 14):** GitHub Actions CI pipeline (`.github/workflows/ci.yml`) iteratively hardened across 5 red runs to reach a 799/799 green state without depending on `backend/.env` or sandbox-specific absolute paths.
- **Shipped fixes (cumulative):**
  - `backend/requirements-ci.txt` excludes the private `emergentintegrations` package.
  - `frontend/yarn.lock` regenerated + explicitly staged.
  - 7 pre-existing test-drift assertions patched across 5 test files.
  - CI env: `DATABASE_URL` → `postgresql+psycopg://` (psycopg3 driver), `CORS_ORIGINS`, `MFA_ENCRYPTION_KEY` inline (CI-only Fernet key).
  - CI postgres service: `POSTGRES_INITDB_ARGS=--lc-collate=C.UTF-8 --lc-ctype=C.UTF-8 --encoding=UTF8` (Pattern A — pins CI sort order to match sandbox + Python codepoint oracle).
  - `tests/test_bootstrap.py` + `tests/test_migration_0025_actuals.py`: replaced `/app/backend` hardcodes with `str(Path(__file__).resolve().parents[1])` (Pattern B).
- **Final validation:** Full backend suite (`python -m pytest --ignore=tests/test_c3_governance_smoke.py`) runs **799 passed / 0 failed** (108.72s) under `env -i` with the exact 14-var ci.yml block and no `backend/.env`. The handoff's "3 failing tests" report was a misdiagnosis (non-policy-compliant password in prior agent's local replica). See `CHANGELOG.md` Follow-up 5.
- **Backlog (P3, deferred to Future_Tasks polish):**
  - Refactor 19 cosmetic `load_dotenv("/app/backend/.env")` hardcodes across test suite.
  - Decide explicit `COLLATE` for entity `ORDER BY name` for production deployment.
  - Rename 5 test functions still carrying stale literal numbers from drift patches.

### 2026-02-17 — Prompt 2.5C AI Capture Review Surface ✓
- **Frontend + minimal backend chat.** Surface shipped: AI Capture inbox
  list page (`/ai-capture`) + capture-job detail page (`/ai-capture/:jobId`)
  with side-by-side attachment preview / extracted-fields / promote form.
  PromoteForm re-uses 19B's `BudgetLinePicker` (D37); navigates to the
  created Draft actual on success (D44). One new backend endpoint:
  `GET /api/v1/ai-capture-jobs/:id/attachment` (file bytes, auth-gated).
- **B36 outcome: NOT REPRODUCIBLE AT HEAD.** Zero LOC backend change.
  Hypothesised silent fix in chat-19B's `freshActual` factory rework.
  Regression test `tests/test_actuals_attachments.py::TestB36AttachmentRead
  AfterWrite` pins the read-after-write contract; chat-19B's skipped E2E
  delete case un-skipped (E14). See `chat-19c-closing.md` §"B36 RCA".
- **Bundle headroom remaining post-build: 13.01 kB** (423.99 kB vs +17
  hard-cap of 437.00 kB). Jest 88 → **118**; pytest 782 → **790**;
  smoke unchanged 11/11. 6 new Playwright spec files (operator-run).
- Reference: `docs/chat-summaries/chat-19c-closing.md`. 5 implementation
  deviations (E11–E15) captured. 6 new backlog items B37–B42 appended
  verbatim from Build Pack to Phase 2 backlog.

### 2026-02-15 — Prompt 2.5B Actuals Frontend + Payment View + E2E ✓
- **Frontend + E2E chat** following 19A backend. Bundle 387.10 kB →
  **419.72 kB** (+32.62 kB gz, target ≤+35 / hard cap +50).
- **Surfaces shipped:** ActualsList (per-project table + filters + create
  Sheet), ActualNew (mobile create route), ActualDetail (header / state
  actions / attachments / collapsible history), PaymentsView (Louise's
  global cross-project list with bulk Mark-Paid), AttachmentUploader
  (`react-dropzone@^14` + React synthetic onPaste for clipboard).
- **15 actuals endpoints wired** via `lib/api/actuals.js`; Zod schemas in
  `lib/schemas/actuals.js`; React Query hooks in `hooks/actuals.js`;
  capability helpers in `lib/actualCapability.js`.
- **State machine UI** matches the live router. `canPostDraft` correctly
  uses `actuals.edit` (verified — router docstring's "actuals.post" label
  is documentation-only). All non-trivial actions open a Radix Dialog
  with reason capture; field state resets on action change.
- **BulkPayDialog (Louise)** uses D30 N-call loop with snapshot pattern,
  shared `paid_date`, per-row auto-generated `BACS-YYYYMMDD-{id6}` refs
  (editable), per-row pending/success/error pills, full
  `actualsKeys.all`+`['budgets']` cache invalidation on completion.
- **Sensitive-field gating (D26):** Zod schemas declare sensitive fields as
  `.nullable().optional()`; backend strips at serialiser layer; UI renders
  "—" for `null|undefined` via `fmtGBP`. `ActualHistory` payload tile is
  client-gated on `actuals.view_sensitive`.
- **Pre-prompt backend patch (D32 + D33):** `ActualsListFilters.status`
  now accepts comma-separated values; ValidationError wrapped to 422 in
  both routes. **pytest 780 → 782 passed.**
- **Test deltas:** Jest 47 → **88** (+41 across 7 spec files); Playwright
  32 → **66** (+34 across 9 spec files); smoke 6 → **11**. Coverage:
  `actualCapability.js` 95.16% / `lib/schemas/actuals.js` 100%.
- **Routes are FLAT siblings in App.js** (not nested under ProjectDetail).
  `/payments` is top-level; project routes are `/projects/:id/actuals[/new|/:actualId]`.
- **8 new backlog items (B28–B35)** appended to Phase 2 backlog. Headline:
  B28 — AI capture review surface for Chat 19C.
- Reference: `docs/chat-summaries/chat-19b-closing.md`. **10 implementation
  deviations (E1–E10)** captured. Notably E8 fixed a shipped-code bug in
  `CreateActualSheet` (missing `project_id` in form defaults caused Zod to
  silently reject every submit); E7 patched the `freshActual.ts` factory to
  dynamically resolve the current Active/Locked budget.

### 2026-02-15 — Prompt 2.5A Actuals Backend ✓
- **Backend only — bundle delta 0.** Migration `0025_actuals` applied; 21 new
  endpoints across 3 routers (`actuals`, `inbound`, `ai_capture`); AI capture
  pipeline (Postmark inbound + APScheduler dispatcher + Anthropic stub/live).
- 5 new services: `actuals`, `actual_attachments`, `ai_capture`,
  `postmark_webhook`, `budgets_reconciliation`. 11 domain exceptions in
  `actual_errors`.
- 5 new tables: `actuals` (51 cols), `actual_attachments`,
  `inbound_email_messages`, `ai_capture_jobs`, `actuals_change_log`. 13 plain
  + 2 partial-unique indexes; 6 user triggers; 3 functions. Round-trip
  downgrade/upgrade verified.
- 9 new `audit_action` enum values (`Post`, `Mark_Paid`, `Void`, `Dispute`,
  `Undispute`, `Release_Retention`, `Add_Attachment`, `Remove_Attachment`,
  `Promote_From_Capture`).
- RBAC: `actuals.admin` (sensitive) added. Catalogue exposes 6 actuals perms
  (view/view_sensitive/create/edit/approve/admin). Finance role inherits admin;
  PM gets view/create/edit only.
- 107 new tests across 5 files. **Total backend: 780 passed / 0 failed / 0
  errors.** Baseline gate Jest 47 / pytest 673 / bundle 387.10 kB → after Jest
  47 / **pytest 780** / bundle 387.10 kB (Δ 0).
- Reference: `docs/chat-summaries/chat-19a-closing.md`. 5 implementation
  deviations (E1–E5) captured in chat summary and CHANGELOG. E5 patched
  in-scope (B27 — post-time budget-terminal re-check) per operator request.
  ⚠️ E4 sandbox env change: `POSTMARK_INBOUND_ENABLED=true` for tests;
  production MUST override to `false` until B23 cutover.

### 2026-05-14 — Prompt 2.4B-ii Playwright E2E ✓
- **Test infrastructure only** — zero changes under `backend/app/` or `frontend/src/`.
- Playwright `@playwright/test@1.60.0` + `otplib@12.0.1` (devDependencies).
- 32 physical Playwright tests in 12 spec files across 8 groups (31 active + 1 quarantined LineDrawer #6 per Build Pack v4 §15 known risk + operator policy 3a).
- Smoke subset (`yarn e2e:smoke`): **6/6 passing in 19.3s**.
- `frontend/playwright.config.ts` — single worker, headless, 5 named projects (chromium-pm/admin/readonly/site/anon) with per-role `storageState`.
- `frontend/e2e/global-setup.ts` re-seeds users + extended demo data, primes `storageState` files. `frontend/e2e/global-teardown.ts` exclusion-list sweep.
- 6 helpers in `frontend/e2e/helpers/`: `login.ts`, `seed.ts`, `asserts.ts`, `api.ts`, `factory.ts`, `freshBudget.ts`. No POM per locked decision #9.
- `scripts/seed_demo_budget.sh` extended with `E2E_PROJECT_ID` env override + 3 flags (`--with-v2-lineage`, `--empty-project`, `--extra-appraisal`). All idempotent.
- Baseline gate BEFORE + AFTER: Jest 47 ✓, pytest 673 ✓, bundle 387.09→387.10 kB (delta 0).
- D13 (new): `AppraisalCostLine` schema drift — Build Pack v4 §R2.2b listed 5 phantom columns; corrected to live 10-column schema. Annotation: `docs/chat-summaries/chat-18-build-pack-annotations.md`.
- D14: LineDrawer #6 quarantined (`test.skip`) — covered by Chat 17 Jest unit test.
- Reference: `docs/chat-summaries/chat-18-closing.md`.

### 2026-05-12 — Prompt 2.4B-i §R8 component tests ✓
- 10 test suites, 46 tests, 0 failures, ~3.4s runtime (`yarn test --watchAll=false`).
- Coverage: lib/ 96%, schemas 86%, BudgetsList 92%; component coverage
  46% (5 of 14 components 0% — relied on smoke-tested e2e paths).
- Files: `__tests__/budgetCapability.test.js` (8 tests),
  `__tests__/budgets-schemas.test.js` (5), `BudgetLinesGrid.pure.test.js`
  (5), `VarianceBadge.test.jsx` (6), `StatusBadge.test.jsx` (1),
  `SensitiveBanner.test.jsx` (2), `BudgetLineage.test.jsx` (4),
  `LifecycleActions.test.jsx` (5), `BudgetsList.test.jsx` (4),
  `LineDrawer.test.jsx` (5).
- Test infra: `setupTests.js` + `test/mockMatchMedia.js`
  + `test/renderWithProviders.jsx` + `test/mocks/fixtures.js`
  + `__mocks__/react-router-dom.js` + `jest.resolver.cjs`
  + craco.config.js jest section.
- Required tests all present: `buildReorderedIds` pure-fn (H8),
  lineage breadcrumb (E10), E9 conflict-banner, status×perm matrix,
  sensitive-stripped schema parse, mobile-floor gates, dirtyFields-only
  PATCH body.
- §R6.3 H8 follow-up: extracted `buildReorderedIds` to
  `lib/buildReorderedIds.js` so the pure-fn test doesn't drag dnd-kit /
  zod / shadcn into its require graph.
- §R7 follow-up: corrected FTC method enum values
  (`BudgetRemaining` → `Budget_Remaining` etc.) after schema test
  caught the divergence from backend.

### 2026-05-12 — Prompt 2.4B-i §R7 LineDrawer + LineItemsPanel + CostCodePicker ✓
- `components/budgets/LineDrawer.jsx` — full rhf + Zod form (line_description,
  notes, ftc_method, forecast_to_complete, percentage_complete, cost_code_id);
  dirtyFields-only PATCH body; defensive cost_code_id only sent when status
  permits; sensitive-field gates (notes + FTC fields hidden unless
  `budgets.view_sensitive`); E9 conflict-detect via `updated_at` watermark
  (loadedAt + justSavedRef) with non-blocking "Reload" amber banner;
  close-with-dirty AlertDialog confirm with sy-orange Discard; Cmd/Ctrl+S
  save + Esc close keyboard shortcuts (operator addition).
- `components/budgets/LineItemsPanel.jsx` — inline-CRUD on items table
  (description / qty / unit / rate, computed amount column); add-row
  builder beneath table; per-row Delete via existing ConfirmDialog
  (sy-orange destructive variant); mobile read-only floor. Field rename
  `unit_cost` → `rate` documented as **errata E11**.
- `components/budgets/CostCodePicker.jsx` — shadcn Select wrapping
  `useCostCodes(projectId)`; filters to `enabled` codes but always keeps
  currently-selected even if disabled; loading + missing-label fallback.
- Build: `main.js` 387.08 kB (+4 kB; rhf was already in the bundle).
- Smoke (test-pm on Draft v1): drawer opens, all 6 form fields render,
  dirty tracking flips on type, Cmd+S triggers PATCH + "Line saved"
  toast + dirty resets, Esc with dirty shows discard dialog (Keep
  editing / Discard sy-orange), discard closes drawer, items panel
  shows existing rows + add flow appends new row with computed £500.00.

### 2026-05-11 — Prompt 2.4B-i §R6 Budget Lines Grid ✓
- `components/budgets/SortableLineRow.jsx` — dnd-kit sortable row with
  setActivatorNodeRef-wired drag handle (C8/C9 a11y), inline edit on
  `line_description` and `percentage_complete` (E7 names), optimistic
  update + rollback via `usePatchBudgetLine` (extended in `hooks/budgets.js`),
  client-side cost-code label join (D13/E7), sensitive-field renders via
  `formatMoney(undefined) → "—"`.
- `components/budgets/BudgetLinesGrid.jsx` — DndContext + KeyboardSensor
  for keyboard a11y, `useReorderBudgetLines` with cache-rollback,
  memoised lines/itemIds, mobile read-only banner, reorder-error toast,
  exports pure `buildReorderedIds()` for §R8 unit test.
- `components/budgets/LineDrawer.jsx` — shadcn Sheet placeholder for §R7
  (line JSON dump + "coming next" checklist).
- `lib/budgetCapability.js` — added `isBudgetEditable`, `isLineCreatable`,
  `isCostCodeMutable` status-only helpers.
- Wired into `BudgetDetail.jsx` (replaced §R6 placeholder).
- Build: `main.js` 382.72 kB (+20 kB).
- Smoke (test-pm on v3 Draft): 3 rows render with drag handles, inline
  edit description + %-complete saved and re-rendered, drawer placeholder
  opens via row overflow menu.

### 2026-05-11 — Sandbox provisioning + lineage breadcrumb follow-up
- Recovery: pod-rebuild wiped Postgres install + `postgres` system user
  mid-session. Reinstalled PG16, restored role/DB, re-seeded demo project
  + v1+v2 budgets. Documented as Track 8 / pre-launch hardening item in
  `/app/docs/SY_Hub_Phase2_Backlog.md` (Sandbox / pod-runtime stability).
- New: `components/budgets/BudgetLineage.jsx` — slate-500 inline prev/next
  links computed client-side from cached `useProjectBudgets`. Errata E10
  added to Build Pack (backend has no lineage pointer).
- Verified: v1 (Superseded) → "Next version (v2) →", v2 (Draft, current)
  → "← Previous version (v1)". Cross-navigation confirmed.

### 2026-05-10 — Prompt 2.4B-i Budgets Frontend §R0–§R5 ✓
- §R0–R3: stack installed (TanStack Query v5 + Table v8 + dnd-kit + MSW),
  routes wired, Zod schemas + API clients + 14 React-Query hooks against
  the flat backend paths. Erratas E1–E9 (Jest/CRA, flat paths, baseURL,
  hooks D12/D13, perm rename, schema rename, sensitive optional, refetch-
  on-save conflict UX) baked in.
- §R4: BudgetsList (TanStack Table v8) with status + variance badges,
  CreateFromAppraisal dialog (lazy fetch, exclude existing source
  appraisals), refresh-attention button. `budgets.view` perm gate.
- §R5: BudgetHeader (5 tiles + variance row), LifecycleActions
  (Activate / Lock / Unlock / Close / New Version) gated by status +
  backend-verified perms (`budgets.edit`, `budgets.admin`) and
  `useIsDesktop()`, SensitiveBanner for users without
  `budgets.view_sensitive`, ConfirmDialog with reason capture +
  brand-fixed sy-teal/sy-orange.
- New: `lib/budgetCapability.js`, `components/budgets/{StatusBadge,
  VarianceBadge, BudgetsTable, CreateFromAppraisalDialog, ConfirmDialog,
  SensitiveBanner, BudgetHeader, LifecycleActions}.jsx`.
- Build smoke OK: `main.js` 362.82 kB. Lint clean. Verified end-to-end:
  Draft → Active transition via `POST /api/v1/budgets/:id/activate`.
- **NEXT (next session):** §R6 BudgetLinesGrid (dnd-kit + inline edit),
  §R7 LineDrawer + LineItemsPanel + CostCodePicker (refetch-on-save +
  `updated_at` banner per E9), §R8 component tests (Jest/CRA), §R9/R10.

### 2026-05-09 — Prompt 2.4A Budgets Core (Backend) ✓
- Migration 0024_budgets (3 tables, 3 enums, 7 indexes incl. 2 partial unique).
- ORM models, services (`budgets`, `budget_lines`, `budget_errors`).
- 14 REST endpoints under `/api/v1`.
- New permission `budgets.admin`; PM gains `budgets.create`. Total perms 84.
- 44 new tests; full suite 641/641 passing (was 597 baseline).
- See `/app/CHANGELOG.md` §2.4A and `/app/docs/SY_Hub_Phase2_Backlog.md`.

### Earlier (carried in from previous chats)
- 1.x: tenants, entities, users, RBAC, sessions, audit log, MFA, system_config.
- 2.1: SDLT bands, appraisal default settings (reference data).
- 2.2: Appraisals Core (header, units, cost lines, finance facilities,
  RLV solver, 8-step recompute pipeline, state machine, view_financials gating).
- 2.3 retrofit: Submitted/Approved/Rejected/Reopened toggles + scenarios.
- pre-2.4 cleanup: 0023 cascade fix on `appraisal_scenarios`.

## P0 / P1 / P2 backlog (next prompts)

### P0 — current prompt (Chat 17, Prompt 2.4B-i Frontend) — **CLOSED**
- R0–R10 ✓ shipped. See `docs/chat-summaries/chat-17-closing.md`.

### P0 — next prompt (Chat 18)
- **BudgetLinesGrid v2 (BT-style)** — dedicated Build Pack, full audit
  cycle. Replace flat R6 grid with cost-code grouping, 11+ columns,
  heat-mapped variance, sticky column, bulk-select, filtering. See
  `docs/SY_Hub_Phase2_Backlog.md` HIGH-PRIORITY section.
- **Track 8 P0** — wire `provision_postgres.sh` into `on-restart.sh`
  step 0 (retires the recurring operator interruption pattern observed
  6× in Chat 17). 1-2h fix.

### P0 — Chat 19
- Budgets E2E (Playwright) — pushed from Chat 18 to make room for v2.

### P0 — successor prompt (Chat 18, Prompt 2.4B-ii)
- Budgets E2E (Playwright).

### P1 — Phase 2 backlog (12 items, see SY_Hub_Phase2_Backlog.md)
1. AppraisalUnit aggregation in `create_from_appraisal` (post-Prompt 3.x)
2. Per-line `entity_id` sourcing (multi-entity projects)
3. Actuals service (Prompt 2.5)
4. Commitments service (Prompt 2.5)
5. Budget changes / approval flow (Prompt 2.6)
6. Cash-flow `budget_line_periods` (separate prompt)
7. `linked_programme_task_id` FK to `programme_tasks` (Prompt 3.2)
8. Xero hooks (Track 6)
9. `requires_attention` scheduler infra + clauses 2/3
10. `SystemConfig` variance-threshold columns
11. Idempotency keys on `/from-appraisal`, `/new-version`
12. SOX-style author-cannot-activate review (MD/Louise call)

### P0 — Batch 2 (Chat 26, next prompt)
- **R7.4 — Receipt form.** New routes `/projects/:id/purchase-orders/:po_id/receipts/new` and `/.../receipts/:receipt_id/edit`. Will re-mount `po-actions-receipt-btn` and `po-actions-receipt-partial-btn` in `<POActionButtons/>` (currently hidden; regression test in `POActionButtons.test.jsx` will flip).
- **R7.5 — Approvals dashboard.** Global landing page for all PO approvals awaiting current user. Pulls from `/api/v1/purchase-orders?status=pending_approval&assigned_to=me` (or equivalent — confirm endpoint shape during R7.5 preflight).
- **R7.6 — Confirm-dialog system + optimistic mutations.**
  - Generic `<ConfirmDialog/>` (reason textarea + confirm/cancel). Re-mounts:
    - **Void** button (`po-actions-void-btn`, `po-actions-void-issued-btn`) — backend `POVoidBody.reason` is `Field(..., min_length=1)` so dialog must collect a non-empty reason before firing.
    - Optionally: surface the existing Send-back / Reject dialogs through the same primitive.
  - Optimistic cache updates: turn the current "mutate → invalidate → refetch → render" three-hop into a single render flip with rollback-on-error. Same change un-breaks the "click Approve → page lag → click Approve again → double-mutation" trap.
  - Budget-line cache invalidation on commitment-changing verbs (send-back joins approve/issue/void in that set).
- **PO Edit / Delete forms (draft state, edit_tier=full).** New routes
  `/projects/:id/purchase-orders/:po_id/edit` and `/.../delete`. Will re-mount
  `po-actions-edit-btn` + `po-actions-delete-btn`. **Edit-issued** form
  (`/edit` reused with status=`issued`) re-mounts `po-actions-edit-issued-btn`.
  Whichever batch ships first, the `DEFERRED_TESTIDS` regression guard in
  `POActionButtons.test.jsx` should be trimmed at the same commit so the
  newly-wired button doesn't fail the matrix.

### P2 — debt / future-proofing
- **Batch 2 / R7.6 polish — `useProjectBudgets` UUID guard.** Add a
  one-line client-side guard before firing GET `/v1/projects/:id/budgets`
  so a bad-URL `:projectId` (e.g. `undefined`, `null`, copy-paste
  fragment) renders the empty-state instead of 422-toasting the user:
  `enabled: canView && /^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$/.test(projectId)`.
  Same pattern likely useful on the sister hooks (`useBudget`,
  `useProjectActuals`, `useProjectPOs`). Diagnosed during the Batch 1
  gate eyeball; root cause was an empty seed DB + a non-UUID URL
  hitting Pydantic's `uuid_parsing` path validator. Not a code bug;
  filed as P2 hardening only.
- `Project.tenant_id` column (will retire the `hasattr` no-op in services).
- Remaining `ON DELETE RESTRICT` FKs on `appraisal_scenarios`.

## Architecture notes
```
/app/backend/
├── alembic/versions/      # migrations (head: 0024_budgets)
├── app/
│   ├── auth/              # JWT + RBAC + permissions
│   ├── jobs/              # APScheduler-managed background jobs
│   ├── models/            # SQLAlchemy ORM
│   ├── routers/           # FastAPI routers (mounted via server.py)
│   ├── schemas/           # Pydantic request shapes (extra="forbid")
│   ├── services/          # business logic
│   ├── bootstrap.py       # `python -m app.bootstrap` (idempotent pod-start)
│   └── seed_*.py          # reference-data seeds
├── tests/                 # pytest suite (641 tests passing)
├── scripts/seed_test_users.py
└── server.py              # FastAPI app entry (NB: not main.py)
```

## How to run locally
```bash
sudo supervisorctl status               # mongodb, postgres, frontend already up
cd /app/backend && python -m app.bootstrap   # idempotent; bootstraps DB + seeds
sudo supervisorctl start backend
cd /app/backend && pytest tests/ --ignore=tests/test_c3_governance_smoke.py
```
