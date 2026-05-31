# Chat 34 closing — Build Pack 2.8a (Subcontracts & Variations)

**Branch strategy:** push-to-main (phase-boundary audits only).
**Build pack:** `BuildPack_2.8a_Subcontracts_Variations.md`.
**Type:** backend-only (no frontend, no Playwright).
**Scope:** Subcontracts + variations only. 2.8b (valuations / payment
notices / retention release / CIS deductions) deliberately deferred.

---

## §R0 Pre-flight deltas (reported to operator BEFORE coding)

The Build Pack lists 8 verification items. **Single material delta:**

- **§R0.7 `permission_action` enum.** Build Pack notes that `issue`
  may be a new value. Live `pg_enum` lookup shows `issue` was already
  added by PO 2.5 (it's the PO `issue` action). The ONLY new
  `permission_action` value introduced by this pack is `cost`. The
  migration's `_add_enum_value_if_missing(...)` calls are idempotent
  so the path is safe either way; the difference is documented
  inline in `0037_subcontracts.py`.

All other §R0 items confirmed clean against `main`:
- Alembic HEAD = `0036_budget_changes` (8-char new revision id chosen:
  `0037_subcontracts`, 17 chars).
- `purchase_orders` carries `project_id`, `supplier_id`, `budget_id`,
  `status` (po_status with `closed`/`voided` terminal), `total_amount`.
- `budget_changes.source_variation_id` exists as a nullable UUID with
  NO FK constraint (2.6 stub — this pack adds the FK).
- `services.budget_changes.create_bcr(...)` signature accepts
  `change_type='Adjustment'` + `source_variation_id=<uuid>` (verified
  at lines 271–283 in `services/budget_changes.py`).
- `suppliers.supplier_type` carries the `'Subcontractor'` enum value
  (2.7 single-table inheritance).
- `services/audit.py` exposes `record_audit` + `field_diff`.
  Numbering pattern: BCR-style row-locked count + unique constraint
  (per `services/budget_changes._next_reference`), not the
  ProjectNumberPrefix table.
- Router pattern (`require_permission` + `/api/v1` mount) confirmed
  against `routers/budget_changes.py` and `routers/purchase_orders.py`.
- Permission baseline = 112 confirmed in DB.

---

## §R1–§R5 outcomes

### Migration `0037_subcontracts` (§R1)
- `permission_action += 'cost'` idempotent (only new value).
- `permission_resource += 'subcontracts'`, `+= 'subcontract_variations'`.
- Two new tables (`subcontracts`, `subcontract_variations`) with the
  state-column `CHECK` constraints, the composite uniques on
  `(project_id, reference)` / `(subcontract_id, reference)`, and
  three indexes per pack §R1.
- Deferred FK
  `budget_changes.source_variation_id → subcontract_variations.id ON
  DELETE SET NULL` (LD3). The column already existed (2.6 stub); this
  migration only adds the constraint.
- 10 permission catalogue rows inserted idempotently
  (`ON CONFLICT (code) DO NOTHING`).
- Role grants seeded explicitly for `super_admin` + `director` +
  `finance` + `project_manager` + `site_manager` + `read_only`. On a
  warm DB the seed re-runs at boot via `seed_rbac.py` and the grants
  remain consistent.
- Downgrade drops FK first, then the variations table, then the
  contracts table; `cost` enum value remains in `permission_action`
  on downgrade (Postgres has no `DROP VALUE`), inert without
  catalogue rows or grants. Pattern matches the
  0029/0035/0036 asymmetry.

### Permissions (§R2)
- Net delta = +10. Final count = **122** (was 112).
- `subcontracts.{view,view_sensitive,create,edit,approve}` (5).
- `subcontract_variations.{view,create,cost,approve,issue}` (5).
- Sensitive flags: `view_sensitive`, `approve` on subcontracts;
  `approve`, `issue` on variations.
- Live role map (mirrored explicitly in the migration AND in
  `seed_rbac.py`):

  | role | view | view_sensitive | create | edit | approve | (variation) cost | (variation) approve | (variation) issue |
  |---|---|---|---|---|---|---|---|---|
  | super_admin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
  | director    | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
  | finance     | ✓ | ✓ |   |   | ✓ |   | ✓ | ✓ |
  | project_manager | ✓ | ✓ | ✓ | ✓ |   | ✓ |   |   |
  | site_manager | ✓ |   |   |   |   |   |   |   |
  | read_only   | ✓ |   |   |   |   |   |   |   |

  Read-only + site-manager get the `.view` of both resources only.
  Project manager raises and costs variations but does NOT approve or
  issue them — separation of duties carries the variation surface
  through to finance / director.

### Services (§R3)
- `services/subcontracts.py`:
  - `create_subcontract`: LD2 guard (rejects plain suppliers as
    ValueError → 422), LD1 PO link guard (same project + same
    subcontractor; sum reconciliation is **warn-not-block** via
    `po_reconciliation_note`), SC-NNNN race-safe under
    `SELECT … FOR UPDATE` on the parent project row, status `Draft`,
    `current_contract_sum = original_contract_sum`.
  - `update_subcontract`: Draft-state edits cover scope + sums +
    dates + signed_*; Active-state edits restrict to lifecycle fields
    (`title`, `start_on`, `end_on`, `signed_at`, `signed_by`).
    PO (un)linking re-runs the LD1 guard.
  - `activate_subcontract` (requires `signed_at`), `complete_subcontract`
    (Active → Completed), `terminate_subcontract` (any → Terminated).
  - Service-layer audit via `record_audit` + `field_diff` on all
    mutations.
- `services/subcontract_variations.py`:
  - `raise_variation`: parent subcontract must be Active; VAR-NNNN
    sequential under the subcontract row lock.
  - `cost_variation`: sets `agreed_value`, Raised → Costed.
  - `approve_variation`: Costed → Approved. Two branches:
    - `WithinContractSum`: bumps `current_contract_sum` by
      `agreed_value` (LD4); no BCR created.
    - `BudgetChange`: resolves the project's current Active budget
      (`is_current=true AND status='Active'`; missing → ValueError
      → 422); calls the EXISTING `services.budget_changes.create_bcr(
      ..., change_type='Adjustment', source_variation_id=variation.id,
      lines=[{budget_line_id, delta=agreed_value}])`. The resulting
      BCR is Draft and follows its OWN approve/apply lifecycle.
      Contract sum **unchanged** on this branch (LD4).
      The router accepts `target_budget_line_id` in the approve body
      so the caller designates the line to adjust.
  - `issue_variation`: Approved → Issued (terminal — formal
    instruction issued).
  - `reject_variation` (reason required, missing → 422) /
    `withdraw_variation`: terminal from Raised|Costed.
  - SoD carry-through documented in the module docstring: the BCR
    creator equals the variation approver, so 2.6's self-approval
    guard prevents that SAME user from approving the generated BCR
    above threshold — a different user must. Correct and intended.

### Routers (§R4)
- `routers/subcontracts.py` mounted under `/api/v1/subcontracts`.
- `routers/subcontract_variations.py` mounted under
  `/api/v1/subcontract-variations`.
- Cross-tenant 404, validation 422, bad transition 409.
- `subcontracts.view_sensitive` gates the contract sum fields at the
  router-layer serialiser.
- Both routers registered in `server.py`.

### Tests (§R5) — 64 functions across 6 files, EXACT names
- `tests/test_subcontracts_migration.py` (8) — schema + FK + enum
  checks (gates 1–2 + sanity).
- `tests/test_permissions_2_8a.py` (11) — perm count 122, code
  presence, full role-map coverage (gates 28–30).
- `tests/test_subcontracts_service.py` (14) — gates 3–13: Draft/SC-0001
  invariants, LD2 plain-supplier rejection, LD1 PO link (same/different
  project + sum-mismatch with note), SC-0002 sequencing, lifecycle
  transitions, sensitive sum gating.
- `tests/test_subcontracts_api.py` (11) — validation 422s,
  permission gating (read-only / PM / finance), audit-row emission,
  list filtering.
- `tests/test_subcontract_variations_service.py` (13) — gates 14–25
  + 31–34: raise/cost/approve/issue/reject/withdraw transitions,
  invalid-state 409s, WithinContractSum fold, BudgetChange-without-
  Active-budget 422, invalid cost_treatment 422, audit emission.
- `tests/test_subcontract_variations_api.py` (7) — gates 22, 23, 26,
  27, 30: BudgetChange branch generates a Draft BCR with
  `source_variation_id` populated, contract sum unchanged,
  budget_line.approved_changes unchanged until the BCR is applied;
  two-user end-to-end (admin raises/costs/approves → director
  submits/approves/applies); source_variation_id round-trip;
  PM/readonly permission denials.
- Shared helpers live in `tests/_subcontracts_common.py`
  (underscore-prefixed so pytest does NOT collect it as a test file —
  same convention as `_bcr_common.py`).
- Test files were **NOT consolidated** (the 2.6 split-file miss was
  not allowed to recur).

---

## Baseline regression sentinels bumped

Following the chat-15 §3 / chat-22 §2 literal-drift convention,
hardcoded baselines in the prior suites were updated to track the
+10 perm delta and the new alembic HEAD:

| file | bump |
|---|---|
| `test_auth_rbac.py` | super_admin 112→122, director 108→118, read_only 13→15 |
| `test_patch_3.py` | total 112→122 |
| `test_permissions_2_6.py` | count 112→122 |
| `test_permissions_2_7.py` | n 112→122 |
| `test_retro_wires.py` | total 112→122 |
| `test_budget_changes_migration.py` | head `0036_budget_changes`→`0037_subcontracts` |
| `test_subcontractors.py` | head `0036_…`→`0037_subcontracts` |
| `test_migration_0025_actuals.py` | head `0036_…`→`0037_subcontracts` |
| `test_migration_0028_user_preferences.py` | head `0036_…`→`0037_subcontracts` |
| `test_bootstrap.py` | sentinel `0036_` → `0037_` (2 sites) |

Function names retained.

---

## §R0 Self-Report

```
## 2.8a Self-Report
- §R0 deltas: only `cost` is a NEW permission_action enum value
  (`issue` already exists from PO 2.5). All other 7 items match
  Build Pack predictions.
- Alembic: HEAD was 0036_budget_changes; migration 0037_subcontracts;
  round-trip pass; source_variation_id FK added: yes
- permission_action enum: new values cost (added);
  issue (reused, pre-existing from PO 2.5)
- Permission count: 112 → 122 (baseline + 10 as predicted)
- Tables added: subcontracts, subcontract_variations
- Variation→BCR hook: create_bcr called with source_variation_id
  verified — round-trip asserted in
  tests/test_subcontract_variations_api.py::TestEndToEndApply.
- Routers registered: subcontracts, subcontract_variations
- Tests: 64 new (8+11+14+11+13+7). pytest 2nd-run: 1180 passed /
  3 xpassed / 0 failed / 0 errors / 1183 collected.
  Regression floor 1183: held.
- Deviations:
  * Naming-convention literal-drift: 10 prior test files'
    hardcoded numeric/head-id baselines bumped (see CHANGELOG).
  * `WithinContractSum` approval still requires the variation to
    have been costed first (Costed→Approved); approving from Raised
    returns 409 (matches Build Pack gate 17).
- Files changed: 20 new/modified.
  - New: app/models/subcontracts.py,
    app/services/subcontracts.py,
    app/services/subcontract_variations.py,
    app/routers/subcontracts.py,
    app/routers/subcontract_variations.py,
    alembic/versions/0037_subcontracts.py,
    tests/_subcontracts_common.py,
    tests/test_subcontracts_migration.py,
    tests/test_permissions_2_8a.py,
    tests/test_subcontracts_service.py,
    tests/test_subcontracts_api.py,
    tests/test_subcontract_variations_service.py,
    tests/test_subcontract_variations_api.py,
    docs/chat-summaries/chat-34-closing.md.
  - Modified: app/models/rbac.py (RESOURCES + ACTIONS),
    app/seed_rbac.py (catalogue + role grants),
    server.py (router registration),
    CHANGELOG.md (Chat 34 entry).
  - Baseline bumps: test_auth_rbac.py, test_patch_3.py,
    test_permissions_2_6.py, test_permissions_2_7.py,
    test_retro_wires.py, test_budget_changes_migration.py,
    test_subcontractors.py, test_migration_0025_actuals.py,
    test_migration_0028_user_preferences.py, test_bootstrap.py.
- Commits: committed locally; NOT pushed-confirmed — operator
  pushes via Save to GitHub.
- IMPORTANT: test files named EXACTLY per §R5 (no single-file
  consolidation — the 2.6 split-file miss did NOT recur).
```
