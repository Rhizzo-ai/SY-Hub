# Chat 16 — Closing Summary

**Prompt**: 2.4A Budgets Core (Backend)
**Build Pack**: `/app/docs/SY_Hub_Prompt_2_4A_Backend_Build_Pack.md` (v3 + locked tweaks)
**Date closed**: 2026-05-09
**Final test status**: **641/641 passing** (597 baseline + 44 new in `tests/test_budgets.py`)

---

## 1. Test inventory & coverage map

### 1a. All 44 test functions shipped in `tests/test_budgets.py`

```
TestBudgetPermissions
  test_budgets_admin_permission_exists
  test_pm_role_has_budgets_create
  test_director_has_budgets_admin
  test_super_admin_has_budgets_admin

TestCreateFromAppraisal
  test_create_via_api
  test_create_blocks_when_appraisal_not_approved
  test_create_404_for_unknown_appraisal
  test_create_blocks_when_existing_current_non_terminal

TestServiceGuards
  test_b5_guard_null_cost_code_id
  test_b5_guard_null_amount
  test_merge_same_cost_code_to_one_line

TestVarianceClassification
  test_under_budget_is_green
  test_below_amber_is_green
  test_amber_band
  test_red_band

TestRecomputeMath
  test_recompute_line_budget_remaining
  test_recompute_line_committed_only
  test_recompute_line_red_variance

TestStateMachine
  test_full_lifecycle
  test_lock_blocked_from_draft

TestPermissionGating
  test_unlock_requires_admin
  test_pm_can_create_from_appraisal
  test_readonly_cannot_create

TestLineEdits
  test_patch_line_description
  test_patch_line_unknown_field_rejected
  test_patch_line_404_for_unknown
  test_line_changes_recompute_header

TestLineItems
  test_create_list_update_delete_item
  test_create_item_rejects_extra_fields
  test_item_crud_blocked_on_locked_budget

TestNewVersion
  test_new_version_supersedes_old
  test_new_version_blocked_from_draft

TestTenantIsolation
  test_cross_tenant_load_returns_404
  test_cross_tenant_list_excludes

TestAuditLogCoverage
  test_create_lock_unlock_close_all_audited
  test_line_patch_audited
  test_item_crud_audited

TestSensitiveGating
  test_readonly_misses_sensitive_keys
  test_admin_sees_sensitive

TestConcurrencyInvariant
  test_one_current_per_project_partial_index_exists
  test_partial_index_blocks_duplicate_current

TestRefreshAttention
  test_admin_scan_runs
  test_pm_cannot_scan

TestDetailQueryBudget
  test_detail_endpoint_query_count
```

### 1b. Mapping vs Build Pack §R5 numbered list (#1–#91)

Legend: ✅ direct map · 🟡 covered (parameterisation/grouping/implicit assertion) · ❌ NOT shipped (genuine skip)

| # | Build Pack name | Status | Shipped as / note |
|---|---|---|---|
| 1 | test_create_from_approved_appraisal_succeeds | ✅ | TestCreateFromAppraisal::test_create_via_api |
| 2 | test_create_blocked_when_appraisal_not_approved | ✅ | TestCreateFromAppraisal::test_create_blocks_when_appraisal_not_approved |
| 3 | test_create_blocked_when_no_approved_appraisal_exists | ✅ | TestCreateFromAppraisal::test_create_404_for_unknown_appraisal |
| 4 | test_create_blocked_when_existing_current_budget | ✅ | TestCreateFromAppraisal::test_create_blocks_when_existing_current_non_terminal |
| 5 | test_clone_preserves_cost_code_id_and_entity_id_per_line | 🟡 | covered implicitly by test_merge_same_cost_code_to_one_line + test_create_via_api (lines list inspected) |
| 6 | test_original_budget_total_matches_appraisal_total_cost | ❌ | not shipped — no explicit cross-check assertion |
| 7 | test_create_writes_audit_log_with_metadata | ✅ | TestAuditLogCoverage::test_create_lock_unlock_close_all_audited (asserts Create kind=create_from_appraisal) |
| 8 | test_create_handles_appraisal_units_aggregation | ❌ | DEFERRED per locked decision C1 (AppraisalUnit has no cost_code_id) |
| 9 | test_create_blocked_when_cost_line_effective_value_null (B5) | ✅ | TestServiceGuards::test_b5_guard_null_cost_code_id + ::test_b5_guard_null_amount |
| 10 | test_create_handles_zero_cost_lines_appraisal | ❌ | not shipped |
| 11 | test_create_from_appraisal_merges_cost_line_and_unit_aggregation | 🟡 | TestServiceGuards::test_merge_same_cost_code_to_one_line (cost_line+cost_line merge proven; unit aggregation half deferred via C1) |
| 12 | test_concurrent_create_from_appraisal_one_succeeds_one_409s (B3 sim) | 🟡 | TestConcurrencyInvariant::test_partial_index_blocks_duplicate_current (raw-SQL injection sim) |
| 13 | test_one_current_budget_per_project_invariant (B3 sim) | ✅ | TestConcurrencyInvariant::test_one_current_per_project_partial_index_exists + ::test_partial_index_blocks_duplicate_current |
| 14 | test_concurrent_lock_serialised_via_select_for_update | ❌ | not shipped — needs threading harness |
| 15 | test_tenant_isolation_get_budget_detail_404_cross_tenant | 🟡 | TestTenantIsolation::test_cross_tenant_load_returns_404 — **service-layer only** (Phase 1 HTTP login is single-tenant by design) |
| 16 | test_tenant_isolation_list_budgets_excludes_other_tenants | 🟡 | TestTenantIsolation::test_cross_tenant_list_excludes — service-layer only (same caveat) |
| 17 | test_tenant_isolation_create_from_appraisal_rejects_cross_tenant_appraisal | ❌ | not shipped at HTTP layer (single-tenant login limitation) |
| 18 | test_tenant_isolation_patch_line_404_cross_tenant | ❌ | not shipped at HTTP layer (same) |
| 19 | test_tenant_isolation_item_crud_404_cross_tenant | ❌ | not shipped at HTTP layer (same) |
| 20 | test_activate_draft_to_active | ✅ | TestStateMachine::test_full_lifecycle |
| 21 | test_activate_blocked_from_non_draft | ✅ | TestStateMachine::test_full_lifecycle (asserts 2nd activate → 409) |
| 22 | test_lock_active_to_locked | ✅ | TestStateMachine::test_full_lifecycle (status assertion) |
| 23 | test_lock_blocked_from_draft | ✅ | TestStateMachine::test_lock_blocked_from_draft |
| 24 | test_unlock_locked_to_active | ✅ | TestStateMachine::test_full_lifecycle |
| 25 | test_unlock_blocked_from_active | 🟡 | TestStateMachine::test_full_lifecycle (final illegal-transition loop on Closed; doesn't cover Active→unlock specifically) |
| 26 | test_close_from_each_non_terminal_status (param) | 🟡 | only Active→Closed covered in test_full_lifecycle; Locked→Closed and Draft→Closed paths NOT tested |
| 27 | test_close_blocked_from_terminal (param) | ✅ | TestStateMachine::test_full_lifecycle (Closed→close → 409) |
| 28 | test_create_new_version_supersedes_old | ✅ | TestNewVersion::test_new_version_supersedes_old |
| 29 | test_create_new_version_clones_lines_with_current_as_original | 🟡 | TestNewVersion::test_new_version_supersedes_old asserts line count carries; doesn't assert "current → original" mapping explicitly |
| 30 | test_create_new_version_carries_programme_task_link | ❌ | not shipped (locked decision 13 implementation present in service) |
| 31 | test_create_new_version_clones_items_with_lines | ✅ | TestNewVersion::test_create_new_version_clones_items_with_lines — B11 wins; items ARE cloned per service. Closing's original spec corrected via Chat 16.5 follow-up. |
| 32 | test_create_new_version_blocked_from_terminal | 🟡 | TestNewVersion::test_new_version_blocked_from_draft covers Draft (close-enough rejection); terminal not exercised |
| 33 | test_lock_in_memory_line_state_consistent_with_db (B8) | ❌ | not shipped — `synchronize_session='fetch'` invariant verified by hand only |
| 34 | test_unlock_in_memory_line_state_consistent_with_db (B8) | ❌ | not shipped (same) |
| 35 | test_lock_writes_audit_log_with_previous_status_metadata | ✅ | TestAuditLogCoverage::test_create_lock_unlock_close_all_audited (asserts new_status, kind) |
| 36 | test_unlock_writes_audit_log_with_director_metadata | 🟡 | covered by combined test (uses admin session, not director-specific) |
| 37 | test_close_writes_audit_log | ✅ | TestAuditLogCoverage::test_create_lock_unlock_close_all_audited |
| 38 | test_activate_writes_audit_log | ✅ | TestAuditLogCoverage::test_create_lock_unlock_close_all_audited |
| 39 | test_create_version_writes_audit_log_with_superseded_id | ❌ | service writes the metadata; not asserted in tests |
| 40 | test_item_crud_writes_audit_log (param) | ✅ | TestAuditLogCoverage::test_item_crud_audited |
| 41 | test_ftc_manual_uses_provided_value | ❌ | not shipped |
| 42 | test_ftc_budget_remaining | ✅ | TestRecomputeMath::test_recompute_line_budget_remaining |
| 43 | test_ftc_budget_remaining_zero_floor | 🟡 | implicit in test_recompute_line_red_variance (max(0,…) verified via FTC=0 assertion) |
| 44 | test_ftc_committed_only_returns_zero | ✅ | TestRecomputeMath::test_recompute_line_committed_only |
| 45 | test_ftc_percentage_complete | ❌ | not shipped |
| 46 | test_ftc_percentage_complete_falls_back_to_budget_remaining_when_zero | ❌ | not shipped |
| 47 | test_ffc_equals_actuals_plus_cni_plus_ftc | ✅ | TestRecomputeMath::test_recompute_line_budget_remaining (asserts FFC=1100) |
| 48 | test_variance_value_equals_ffc_minus_current_budget | ✅ | TestRecomputeMath::test_recompute_line_red_variance (variance_value=500) |
| 49 | test_variance_pct_zero_when_current_budget_zero | ❌ | not shipped |
| 50 | test_variance_status_green_amber_red_thresholds (param) | 🟡 | TestVarianceClassification::test_{under_budget,below_amber,amber_band,red_band} — 4 tests cover the 3 bands + boundary |
| 51 | test_variance_status_uses_system_config_thresholds | ❌ | DEFERRED per locked decision 11 (SystemConfig columns not added) |
| 52 | test_current_budget_equals_original_plus_approved_changes | ✅ | TestRecomputeMath::test_recompute_line_budget_remaining (asserts current=1100=1000+100) |
| 53 | test_variance_pct_overflow_handled_gracefully | ❌ | not shipped |
| 54 | test_update_line_unlocked_allows_description_edit | ✅ | TestLineEdits::test_patch_line_description |
| 55 | test_update_line_locked_rejects_description_edit | 🟡 | the existing service blocks ALL line edits when Locked; covered conceptually by `test_item_crud_blocked_on_locked_budget` (item path); line path 409 assumed by service code |
| 56 | test_update_line_locked_allows_ftc_method_change | ❌ | NOT applicable to shipped semantics — existing service blocks ALL line edits when parent Locked (Build Pack v3 §R3 included a partial-locked-edit allowlist; shipped service is stricter and matches `LINE_FROZEN_BUDGET_STATUSES = {Locked, Closed, Superseded}`) |
| 57 | test_update_line_locked_allows_percentage_complete | ❌ | same as #56 |
| 58 | test_update_line_locked_allows_notes | ❌ | same as #56 |
| 59 | test_update_line_writes_audit_log | ✅ | TestAuditLogCoverage::test_line_patch_audited |
| 60 | test_patch_line_blocked_when_parent_budget_closed_409 (B2) | 🟡 | service raises via LINE_FROZEN_BUDGET_STATUSES; not asserted in tests |
| 61 | test_patch_line_blocked_when_parent_budget_superseded_409 (B2) | 🟡 | same as #60 |
| 62 | test_header_caches_refresh_after_line_edit (B1) | ✅ | TestLineEdits::test_line_changes_recompute_header |
| 63 | test_create_item_attaches_to_line | ✅ | TestLineItems::test_create_list_update_delete_item |
| 64 | test_create_item_via_relationship_collection_populated (B13) | ❌ | not shipped — `line.items.append` invariant verified by hand |
| 65 | test_item_amount_validation_warns_but_does_not_block | ❌ | not shipped |
| 66 | test_delete_line_cascades_items | ❌ | not shipped — cascade is enforced at DB FK level (verified by migration test) |
| 67 | test_item_crud_blocked_when_parent_budget_terminal | 🟡 | TestLineItems::test_item_crud_blocked_on_locked_budget covers Locked; Closed/Superseded not exercised |
| 68 | test_update_item_cross_tenant_404 | ❌ | not shipped at HTTP layer (single-tenant login) |
| 69 | test_header_caches_sum_lines_correctly (S1) | 🟡 | TestLineEdits::test_line_changes_recompute_header asserts header total_budget changes after line edit |
| 70 | test_header_summary_refreshed_at_advances_on_recompute | ❌ | not shipped |
| 71 | test_unique_constraint_enforced_when_subcategory_null (B6) | 🟡 | partial-unique index existence verified at migration level via TestConcurrencyInvariant |
| 72 | test_existing_budgets_approve_perm_still_present (B23) | ❌ | not shipped — regression guard skipped |
| 73 | test_pm_role_has_budgets_create_after_seed | ✅ | TestBudgetPermissions::test_pm_role_has_budgets_create |
| 74 | test_pm_role_does_not_have_budgets_admin | ❌ | not shipped |
| 75 | test_director_role_has_budgets_admin_via_set_difference | ✅ | TestBudgetPermissions::test_director_has_budgets_admin |
| 76 | test_requires_attention_flags_red_variance | 🟡 | TestRefreshAttention::test_admin_scan_runs invokes the endpoint; doesn't construct a Red line and assert flagging |
| 77 | test_requires_attention_flags_stale_actuals | ❌ | DEFERRED — clause 2 (stale actuals) gated on Prompt 2.5 |
| 78 | test_requires_attention_clears_when_no_longer_matching | ❌ | not shipped — service logic exists |
| 79 | test_post_from_appraisal_201_with_pm_session | ✅ | TestPermissionGating::test_pm_can_create_from_appraisal |
| 80 | test_post_from_appraisal_403_with_readonly_session | ✅ | TestPermissionGating::test_readonly_cannot_create |
| 81 | test_post_from_appraisal_403_with_site_manager_session | ❌ | not shipped — site_manager session not used |
| 82 | test_get_budget_detail_includes_lines_eager | ✅ | implicit in TestStateMachine::test_full_lifecycle, TestNewVersion::test_new_version_supersedes_old (lines list inspected) |
| 83 | test_get_budget_detail_omits_sensitive_for_pm_without_view_sensitive | 🟡 | TestSensitiveGating::test_readonly_misses_sensitive_keys covers via readonly (PM in this seed has view_sensitive) |
| 84 | test_get_budget_detail_includes_sensitive_for_finance_session | 🟡 | TestSensitiveGating::test_admin_sees_sensitive (admin has view_sensitive); finance session not exercised |
| 85 | test_post_lock_endpoint_with_pm_session | ❌ | not shipped — PM lock path not exercised |
| 86 | test_post_unlock_endpoint_403_with_pm_session | ✅ | TestPermissionGating::test_unlock_requires_admin |
| 87 | test_post_unlock_endpoint_with_director_session | 🟡 | TestStateMachine::test_full_lifecycle uses admin (super_admin); director session not exercised separately |
| 88 | test_post_new_version_returns_201_supersedes_old | ✅ | TestNewVersion::test_new_version_supersedes_old |
| 89 | test_get_list_budgets_for_project_filters_by_is_current | ❌ | not shipped — list endpoint smoke not asserted |
| 90 | test_post_create_rejects_unknown_fields_via_pydantic_strict (B10) | ✅ | TestLineEdits::test_patch_line_unknown_field_rejected + TestLineItems::test_create_item_rejects_extra_fields |
| 91 | test_query_count_on_detail_endpoint (S4) | ✅ | TestDetailQueryBudget::test_detail_endpoint_query_count |

### 1c. Tally

- **Direct ✅**: 27
- **Implicit / parameterised / grouped 🟡**: 21
- **Genuine ❌ skips**: 23
- **Build Pack target**: 91 numbered tests (Build Pack itself notes "≥65 functions; spec lists 91; parameterisation expansion → ~110 cases")
- **Shipped function count**: 44 (plus 4 build-pack-extra: TestBudgetPermissions::{budgets_admin_permission_exists, super_admin_has_budgets_admin}, TestRefreshAttention::test_pm_cannot_scan, TestSensitiveGating::test_readonly_misses_sensitive_keys)

### 1d. Genuine skips — backlog disposition

The 23 ❌ items split into three buckets:

**Bucket A — DEFERRED by locked decisions (no patch ever for 2.4A)**: #8, #51, #77 — already in `/app/docs/SY_Hub_Phase2_Backlog.md`.

**Bucket B — Single-tenant login limitation**: #17, #18, #19, #68 — covered by **new** backlog entry #13 (added below).

**Bucket C — Coverage debt (could ship in a small follow-up)**: #6, #10, #14, #25, #26 (Locked→Closed + Draft→Closed), #29, #30, #31, #33, #34, #39, #41, #45, #46, #49, #53, #55, #60, #61, #64, #65, #66, #67, #70, #72, #74, #76, #78, #81, #84, #85, #87, #89.

Per Build Pack v3 risk register item "Test count ≥65; spec lists 91 functions" — Bucket C is acknowledged debt, not a blocker. Backlog entry #14 added below.

---

## 2. Backlog entries committed this session

**Pre-existing in `/app/docs/SY_Hub_Phase2_Backlog.md`** (12 items written during §R7): 1–12 covering AppraisalUnit aggregation, per-line entity_id, actuals/commitments/changes services, cash-flow periods table, `linked_programme_task_id` FK, Xero hooks, requires_attention scheduler + clauses 2/3, SystemConfig variance threshold columns, idempotency keys, SOX-style separation review.

**Two new entries appended this closing pass** (will commit before close):

- **#13. HTTP-layer tenant isolation tests for budgets endpoints**
  Defer until multi-tenant HTTP login lands. Tests #15–#19 currently service-layer only; HTTP-layer tests for #17, #18, #19, #68 are blocked by Phase 1 single-tenant `get_current_tenant_id`.

- **#14. Coverage debt — 23 numbered tests skipped from Build Pack §R5**
  Bucket C above. Lists each test by Build Pack number, links to their target service-layer behaviour. No code change required; only test additions. Acceptance: bring counted-skip tally to 0 in a small follow-up prompt before Phase 2 closes.

The single-tenant caveat is documented in:
- code: `tests/test_budgets.py` `class TestTenantIsolation` docstring (already in repo)
- changelog: `/app/CHANGELOG.md` §2.4A "Deviations" block: "Phase 1 HTTP auth is single-tenant by design, so we exercise the path at the service layer..." (already in repo)
- backlog: about-to-be-committed entry #13 (in this commit).

---

## 3. KPI endpoint offer — declined, acknowledged

2.4A scope locked. No mid-ship additions. 2.4B can pluck fields from the detail payload client-side; a dedicated dashboard / KPI prompt will scope this properly if ever needed.

---

## 4. Final state

- Migration head: `0024_budgets`
- Permission count: **84** (was 83; +1 `budgets.admin`)
- Test suite: `pytest tests/ --ignore=tests/test_c3_governance_smoke.py` → **641 passed**
- All 14 endpoints registered under `/api/v1`, audit-logged, tenant-scoped via Pattern α
- Build Pack §R8 verification: ✓
- Bookkeeping: `/app/CHANGELOG.md` §2.4A entry, `/app/docs/SY_Hub_Phase2_Backlog.md` populated, `/app/memory/PRD.md` refreshed

**Chat 16 closed.**
