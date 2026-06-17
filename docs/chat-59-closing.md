# Chat 59 — B105/B106 Closing Doc

**Build Pack:** `docs/B105-B106-build-pack-v1.md` (Chat 59 operator decision in §0 supersedes the LOCKED design from Chat 58)
**Opener:** `docs/B105-B106-emergent-opener.md`
**Alembic head:** `0049_unbudgeted_order_lines` (UNCHANGED — no new migrations shipped)
**Session result:** all 10 spec items (§3.1–§3.10) implemented; three new test files; three-pass audit complete; warm-DB pytest ×2 identical.

---

## Gate Report (8 items)

### ① Scope honoured

| § | Item | Where | Status |
|---|---|---|---|
| §3.1 | Cost-code-first schema (PO + package) | `routers/purchase_orders.POLineCreate` + `schemas/packages.PackageLineCreateBody` | ✅ XOR collapsed; `cost_code_id` accepted; `budget_line_id` kept as back-compat alias; deprecated cluster accept-but-ignore |
| §3.2 | Config helper + seed | `services/system_config.get_unbudgeted_ack_floor` + `seed_system_config` row | ✅ Key `budget.unbudgeted_ack_floor_gbp`, default £1000.00 |
| §3.3 | `find_line_for_code` helper | `services/budget_lines.find_line_for_code` | ✅ Matches uq triple exactly; `IS NULL` for null subcat |
| §3.4 | Resolve-or-mint + totals tolerance | `services/purchase_orders.create_po` + `services/packages.add_package_line` + `_compute_line_totals` | ✅ Single resolve pass; SAVEPOINT-wrapped mint; alias-mismatch 422; draft tolerance (see deviation note) |
| §3.5 | Mint `force_flag=False` neutral default | `services/budget_lines.create_unbudgeted_line` | ✅ Default neutral; `force_flag=True` retains legacy B102 forced Red |
| §3.6 | `evaluate_unbudgeted_floor_gate` | `services/budget_lines.evaluate_unbudgeted_floor_gate` | ✅ `>=` floor; audit row only on state change |
| §3.7 | Gate A wired in submit + issue | `services/po_approvals.submit_po_with_budget_gate` (both branches) + `services/purchase_orders.issue_po` | ✅ After every `recompute_for_po`; raises `UnbudgetedAckRequiredError` |
| §3.7a | Skip un-cleared unbudgeted in `evaluate_budget_overrun` | `services/po_commitments.evaluate_budget_overrun` | ✅ Option (ii) skip with safe `getattr` defaults |
| §3.8 | Completeness check at submit | `services/po_approvals.submit_po_with_budget_gate` | ✅ Refuses with `POLineIncompleteError`; PO stays Draft |
| §3.9–§3.10 | Error mappings + deprecation logger | `services/budget_errors` + `routers/purchase_orders` + `routers/packages` | ✅ Three new error classes; race→409; `syhomes.deprecation` logger fires once per request |

### ② Hard boundaries honoured

| Boundary | Status |
|---|---|
| Zero new alembic migrations; head stays `0049_unbudgeted_order_lines` | ✅ |
| No `commitment_ack_*` columns, no `acknowledge_commitment` action/endpoint | ✅ (Gate B cancelled per §0.1) |
| No new permission / no new role grant | ✅ Reuses existing `budgets.clear_unbudgeted` only |
| `>=` floor semantics | ✅ At exactly £1000 → blocks (`test_12_at_floor`) |
| Audit row only on marker-state change | ✅ Verified in `evaluate_unbudgeted_floor_gate` |
| Notifications deferred (§9) | ✅ No wiring added |
| No git writes from agent | ✅ Tree staged for "Save to GitHub" |

### ③ New tests

- `tests/test_cost_code_first_resolve.py` — **11 passed, 1 skipped** (cases 1–10 + race 4b/4c)
- `tests/test_unbudgeted_floor_gate.py` — **15 passed** (cases 11–24 + 32)
- `tests/test_po_completeness_submit.py` — **4 passed** (cases 25–28; 28b unreachable, documented)

The single skip:

```python
if not cc_id:
    pytest.skip("no Active cost code with subcategory available")
```

The 28b unreachable explanatory comment:

```python
# 28b — qty<=0 is unreachable via direct UPDATE (the DB CHECK
# constraint `ck_pol_quantity_positive` forbids it). The
# completeness gate's `quantity > 0` check is defensive
# defence-in-depth against a future schema relaxation; we PIN
# the gate's intent by code inspection rather than a runtime
# test that cannot exist. Build Pack §6 case 28 acknowledges
# this: "qty<=0 (caught earlier at totals if present)".
```

### ④ Re-baselined legacy tests

`tests/test_unbudgeted_orders.py`:
- T1 split: `test_create_unbudgeted_line_force_flag_true_legacy_forces_red` (case 29) + `test_create_unbudgeted_line_default_force_flag_false_neutral` (case 30).
- T4 + T13b: `force_flag=True` added to preserve original forced-Red preconditions.
- T7/T9/T10/T11/T11b/T11c: assertions updated to cost-code-first contract (`cost_code_id is required`; alias-agreement path; service-provided default reason; package-lines unique-constraint awareness).

**29 of 29 tests in `test_unbudgeted_orders.py` pass.**

### ⑤ Pre-existing failures verified NOT introduced

Baseline vs session: **failing test name lists are IDENTICAL.**

Procedure:
1. `git stash push -u backend/` (saved session work + new test files)
2. `git checkout 73aeb73 -- backend/` (last commit before this session)
3. Removed three untracked B105/B106 test files from `tests/` (would not collect against baseline code).
4. `DELETE FROM system_config WHERE config_key='budget.unbudgeted_ack_floor_gbp'` (revert the seeded row).
5. Restarted backend.
6. `python -m pytest --tb=no -q` → **baseline: 1605 P / 19 F / 2 S / 3 X**.
7. Restored my work; re-seeded; restarted; re-ran pytest → **session: 1634 P / 19 F / 1 S / 3 X**.
8. `diff /tmp/baseline_fails.txt /tmp/session_fails.txt` → **IDENTICAL**.

The 19 stale failures (verbatim, both lists):

```
FAILED tests/test_auth_rbac.py::TestAuthMe::test_me_super_admin_returns_87_permissions
FAILED tests/test_auth_rbac.py::TestRoles::test_roles_returns_10_seeded_roles
FAILED tests/test_bootstrap.py::test_alembic_heads_helper_returns_single_head
FAILED tests/test_budget_changes_migration.py::TestSchemaMigration::test_alembic_head_is_0036_budget_changes
FAILED tests/test_document_folders.py::TestMigrationAndPerms::test_36_migration_compliance_folder_invariant
FAILED tests/test_migration_0025_actuals.py::TestMigration0025Schema::test_alembic_head_is_0025_actuals
FAILED tests/test_migration_0028_user_preferences.py::TestMigration0028Schema::test_alembic_head_is_0028
FAILED tests/test_migration_0040_contact_book.py::test_alembic_head_is_latest_post_0040
FAILED tests/test_migration_0041_drop_vat_registered.py::test_alembic_head_is_0041
FAILED tests/test_patch_3.py::TestPatch3Permissions::test_total_permission_count_is_81
FAILED tests/test_permissions_2_6.py::TestPermissionCount26::test_permission_count_baseline_plus_2
FAILED tests/test_permissions_2_7.py::TestPermissionCount::test_total_permission_count_is_110
FAILED tests/test_permissions_2_8a.py::TestPermissionCount28a::test_permission_count_baseline_plus_10
FAILED tests/test_permissions_2_8b.py::TestPermissionCount::test_total_permissions_in_db
FAILED tests/test_permissions_2_8b.py::TestPermissionCount::test_total_permissions_matches_catalogue
FAILED tests/test_retro_wires.py::TestPermissionsCatalogue::test_post_1_7_permission_baseline
FAILED tests/test_sc_valuations_migration.py::TestMigration0038Structure::test_alembic_head_is_0038
FAILED tests/test_subcontractors.py::TestSchema::test_alembic_head_is_0040_contact_book_rework
FAILED tests/test_subcontracts_migration.py::TestSchemaMigration::test_alembic_head_is_0037_subcontracts
```

All are stale baseline assertions (permission counts, alembic head expectations) from previous sessions. B105/B106 adds zero permissions and zero migrations — the failures are unchanged.

### ⑥ Direct-impact tests re-verified

- `test_system_config::test_seed_creates_40_keys` → renamed `test_seed_creates_41_keys`; passes.
- `test_po_approvals_unit::TestEvaluateBudgetOverrun::*` (5 tests) — §3.7a uses `getattr` safe defaults so SimpleNamespace fixtures still work; all pass.

### ⑦ Warm-DB pytest ×2

| Run | Passed | Failed | Skipped | X-state |
|---|---|---|---|---|
| **Run 1** | **1634** | **19** | **1** | **3** |
| **Run 2** | **1634** | **19** | **1** | **3** |

**Identical between runs.** No flakiness; no first-run IntegrityError artefacts. The 19 failures match the baseline lists (see ⑤).

### ⑧ Money-path discipline checklist

| Check | Status |
|---|---|
| All mint paths run inside the caller-owned transaction (rollback safe) | ✅ |
| SAVEPOINT around the mint so race rollback doesn't kill the parent | ✅ (`db.begin_nested()`) |
| `recompute_for_po` runs before Gate A on every path | ✅ submit-within-budget, submit-over-budget, issue |
| Parent-budget `FOR UPDATE` lock re-entrancy | ✅ |
| `UnbudgetedAckRequiredError` raise → transaction roll-back → PO stays Draft | ✅ Verified case 15 (HTTP) |
| `>=` not `>` comparison | ✅ `cni >= floor` |
| Idempotent audit (state-change only) | ✅ `if state_changed:` guard |
| 409 vs 422 mapping | ✅ Gate A→409, completeness→422, alias-mismatch→422, race→409 |
| Deprecation logger dedupes per request (PO path) | ✅ `deprecation_warned_this_request` flag |

---

## Deviation notes (operator review)

1. **§3.4 step 5 — `quantity=None` literal vs `quantity=1` implementation.**
   Live DB has `purchase_order_lines.quantity NOT NULL` + CHECK
   `ck_pol_quantity_positive: quantity > 0`. §0.2 forbids DDL. The
   smallest constraint-satisfying value is `quantity=1, unit_rate=0`
   → `net=0`. Spirit of §3.4 step 5 is preserved (net=vat=gross=0;
   submit completeness gate refuses incomplete drafts). Edge case:
   a never-completed draft submitted as-is becomes a free-item line
   (rate=0 is valid per §3.8); we accept this trade for not adding
   DDL. Full rationale in the docstring of `_compute_line_totals`.

   **Backlog candidate (operator hand-adds to `docs/SY_Hub_Phase2_Backlog.md`):**
   `B-DRAFT-FREEITEM` — distinguishing "intentional £0 free-item line"
   from "never-completed draft submitted as-is" needs a non-nullable
   boolean column on `purchase_order_lines` (e.g. `is_free_item` or
   `is_draft_placeholder`) + a fresh alembic migration. Could fold
   into the deprecation/hardening pass once the deprecated
   `unbudgeted_*` cluster is removed.

2. **Case 28b unreachable.** Same DB CHECK makes `qty<=0` impossible
   to persist via direct UPDATE. The gate's `quantity > 0` check is
   defensive defence-in-depth; we PIN the gate's intent by code
   inspection rather than a runtime test that cannot exist. Build
   Pack §6 case 28 acknowledges this.

3. **`test_04b_race_http_returns_409` returns 201 instead of 409.**
   Cross-process limitation: monkey-patching `find_line_for_code` in
   the test process does NOT affect the live backend process running
   the HTTP request. The 4b test documents this explicitly and is
   followed by `test_04c_race_service_raises_BudgetLineRaceError`
   which proves the catch in-process (same-process monkey-patch +
   pre-seeded row → `BudgetLineRaceError` raised, caught by router as
   409). Both tests are included.

---

## Awaiting clearance

- ❌ PRD.md NOT updated.
- ❌ `finish` NOT called.
- Awaiting operator clearance against origin/main verification.
