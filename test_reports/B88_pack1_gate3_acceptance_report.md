# B88 Pack 1 — Gate 3 acceptance report (re-submission)

> Three required follow-ups against the previously-submitted Gate 3
> code are complete. **No work has been saved to GitHub**, awaiting
> operator raw-fetch verification on `origin/main`.

---

## CHANGE 1 — Un-skip the two delete-guard tests

**Before:** the `spotcheck_budget_row` fixture in
`tests/test_cost_code_delete_guard.py` called `pytest.skip(...)` when
no `Active` budget was present on the pod. On this pod, no R7
spotcheck budget existed, so **G2** (`test_delete_blocked_by_budget_line`)
and **G3** (`test_delete_blocked_by_appraisal_cost_line`) silently
skipped — defeating the entire point of the guard tests.

**After:** the fixture now **self-seeds a probe Approved appraisal +
Active budget** for the spotcheck project when none exists, yields the
ids to the tests, then **cleans up on module teardown** so other test
modules can still wipe appraisals/budgets in their own setup without
FK collisions.

**Fixture body** (lines 148–235 of `test_cost_code_delete_guard.py`):

```python
@pytest.fixture(scope="module")
def spotcheck_budget_row(db_engine, spotcheck_project_id):
    """Return an Active budget + its source appraisal.
    ... [self-seeds probe rows when missing, cleans up on teardown] ...
    """
    created_ids = {"appraisal_id": None, "budget_id": None}

    with db_engine.connect() as c:
        row = c.execute(text("""
            SELECT id, source_appraisal_id
            FROM budgets WHERE status = 'Active'
            ORDER BY created_at LIMIT 1
        """)).first()
    if row is not None:
        yield {"budget_id": str(row[0]),
                "appraisal_id": str(row[1])}
        return

    with db_engine.begin() as c:
        admin_uid = c.execute(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        )).scalar()
        appraisal_id = str(uuid.uuid4())
        appraisal_group_id = str(uuid.uuid4())
        # bump version_number to avoid colliding with
        # (project_id, 'Base', version) rows left by sibling
        # appraisal tests in the same pytest session;
        # is_current=false so we don't trip the
        # "one current Base per project" trigger either.
        next_version = c.execute(text("""
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM appraisals
            WHERE project_id = :p AND scenario = 'Base'
        """), {"p": spotcheck_project_id}).scalar()
        c.execute(text("""
            INSERT INTO appraisals (
              id, project_id, version_number, name, status,
              reference_date, appraisal_group_id, is_current,
              scenario, created_by_user_id
            ) VALUES (
              :i, :p, :v, :n, 'Approved',
              CURRENT_DATE, :g, false, 'Base', :u
            )
        """), {"i": appraisal_id, "p": spotcheck_project_id,
                "v": next_version,
                "n": f"DEL-GUARD-PROBE-{appraisal_id[:8]}",
                "g": appraisal_group_id, "u": admin_uid})

        budget_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO budgets (
              id, project_id, source_appraisal_id, version_number,
              version_label, is_current, status, created_by_user_id
            ) VALUES (
              :i, :p, :a, :v,
              'Original', false, 'Active', :u
            )
        """), {"i": budget_id, "p": spotcheck_project_id,
                "a": appraisal_id, "v": next_version, "u": admin_uid})

    created_ids["appraisal_id"] = appraisal_id
    created_ids["budget_id"] = budget_id
    yield {"budget_id": budget_id, "appraisal_id": appraisal_id}

    # Module teardown — delete the probe rows so other test modules
    # can wipe appraisals/budgets without FK collisions.
    if created_ids["budget_id"] is not None:
        with db_engine.begin() as c:
            c.execute(text(
                "DELETE FROM budget_lines WHERE budget_id = :b"
            ), {"b": created_ids["budget_id"]})
            c.execute(text(
                "DELETE FROM budgets WHERE id = :b"
            ), {"b": created_ids["budget_id"]})
            c.execute(text(
                "DELETE FROM appraisal_cost_lines WHERE appraisal_id = :a"
            ), {"a": created_ids["appraisal_id"]})
            c.execute(text(
                "DELETE FROM appraisals WHERE id = :a"
            ), {"a": created_ids["appraisal_id"]})
```

The tests themselves still create + clean up their own blocker row
(a `budget_lines` insert for G2; an `appraisal_cost_lines` insert for
G3) and assert the `DELETE /api/cost-codes/{id}` call returns **409
with the named blocker text**. No trivial pass: the 409 only happens
when the inserted blocker row genuinely points at the cost code being
deleted via a RESTRICT FK.

**Result — `tests/test_cost_code_delete_guard.py` 15 / 15 GREEN
(previously 13 passed + 2 skipped):**

```
tests/test_cost_code_delete_guard.py::test_delete_clean_unenrolled_succeeds                            PASSED
tests/test_cost_code_delete_guard.py::test_delete_blocked_by_project_enrolment                         PASSED
tests/test_cost_code_delete_guard.py::test_delete_blocked_by_budget_line                               PASSED   ← was skipped
tests/test_cost_code_delete_guard.py::test_delete_blocked_by_appraisal_cost_line                       PASSED   ← was skipped
tests/test_cost_code_delete_guard.py::test_delete_blocked_by_subcategory                               PASSED
tests/test_cost_code_delete_guard.py::test_delete_blocked_by_purchase_order_line_transitively          PASSED
tests/test_cost_code_delete_guard.py::test_409_payload_lists_all_blockers                              PASSED
tests/test_cost_code_delete_guard.py::test_cost_code_entity_mapping_cascades_on_delete                 PASSED
tests/test_cost_code_delete_guard.py::test_replaced_by_self_ref_set_null_on_delete                     PASSED
tests/test_cost_code_delete_guard.py::test_section_delete_blocked_by_attached_cost_codes               PASSED
tests/test_cost_code_delete_guard.py::test_section_delete_blocked_by_child_subgroup                    PASSED
tests/test_cost_code_delete_guard.py::test_director_cannot_delete_cost_code                            PASSED
tests/test_cost_code_delete_guard.py::test_finance_cannot_delete_cost_code                             PASSED
tests/test_cost_code_delete_guard.py::test_project_manager_cannot_delete_cost_code                     PASSED
tests/test_cost_code_delete_guard.py::test_readonly_cannot_delete_cost_code                            PASSED

15 passed in 5.67s
```

---

## CHANGE 2 — Fix the 25 stale baseline tests

Every test asserting against a pre-B88 alembic head (`0043_document_folders`),
the old permission catalogue size (`133` for super_admin / `129` for
director), or the now-superseded "no DELETE / orphan-perm" invariants
has been updated. **No deferrals.** One xfail added on
`TestSeed::test_nine_sections` per the operator's direct instruction
(option (i)) with a TODO pointing at Gate 4.

| # | File :: Test | Old expected | New expected | Reason (one-line) |
|---|---|---|---|---|
| 1 | `test_sc_valuations_migration.py::TestMigration0023::test_alembic_head_unchanged` | head == `0043_document_folders` | head == `0044_cost_code_groups` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 2 | `test_bootstrap.py::test_alembic_at_head_after_bootstrap` | `head.startswith("0043_")` | `head.startswith("0044_")` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 3 | `test_migration_0025_actuals.py::TestActualsMigration::test_alembic_at_expected_head` | head == `0043_document_folders` | head == `0044_cost_code_groups` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 4 | `test_document_folders.py::TestMigrationHeadStable::test_head_is_document_folders` | head == `0043_document_folders` | head == `0044_cost_code_groups` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 5 | `test_migration_0041_drop_vat_registered.py::TestAlembicHead::test_head_unchanged` | head == `0043_document_folders` | head == `0044_cost_code_groups` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 6 | `test_budget_changes_migration.py::TestAlembicHead::test_alembic_at_expected_head` | head == `0043_document_folders` | head == `0044_cost_code_groups` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 7 | `test_migration_0040_contact_book.py::TestHead::test_head_is_unchanged` | head == `0043_document_folders` | head == `0044_cost_code_groups` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 8 | `test_subcontractors.py::TestSubcontractorsMigrationHead::test_alembic_head_is_subcontractors` | head == `0043_document_folders` | head == `0044_cost_code_groups` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 9 | `test_migration_0028_user_preferences.py::TestMigration0028::test_alembic_head_unchanged` | head == `0043_document_folders` | head == `0044_cost_code_groups` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 10 | `test_subcontracts_migration.py::TestMigration0042::test_alembic_head_is_subcontracts` | head == `0043_document_folders` | head == `0044_cost_code_groups` | B88 Pack 1 Gate 1 ships migration 0044, head moves. |
| 11 | `test_auth_rbac.py::TestAuthEndpoints::test_login_returns_permissions` | `len(data["permissions"]) == 133` | `== 136` | B88 Pack 1 Gate 2 adds `cost_codes.{create,edit,delete}` via wildcard → +3 → 136. |
| 12 | `test_auth_rbac.py::TestSeedRbacRoleGrants::test_super_admin_has_all_permissions` | `role_perms["super_admin"] == 133` | `== 136` | super_admin holds the full catalogue → 136. |
| 13 | `test_auth_rbac.py::TestSeedRbacRoleGrants::test_director_has_role_grants_but_excludes_admin_only` | `role_perms["director"] == 129` | `== 131` | director gains `cost_codes.create + .edit` only (delete in exclusion set → super_admin-only) → +2 → 131. |
| 14 | `test_patch_3.py::TestPatch3CostCodeAuditAcceptanceCounts::test_active_cost_codes_count_unchanged` | `total == 133` | `total == 136` | Same B88 +3 permission count (this counts perms not cost codes — see assertion). |
| 15 | `test_permissions_2_6.py::TestPermissionDelta::test_total_permission_count_is_132` | `count == 133` | `count == 136` | B88 Pack 1 Gate 2 adds 3 permissions → 136. |
| 16 | `test_permissions_2_7.py::TestPermissionDelta::test_total_count_is_133` | `n == 133` | `n == 136` | B88 Pack 1 Gate 2 adds 3 permissions → 136. |
| 17 | `test_permissions_2_8a.py::TestPermissionsCount::test_total_permission_count_is_132` | `count == 133` | `count == 136` | B88 Pack 1 Gate 2 adds 3 permissions → 136. |
| 18 | `test_permissions_2_8b.py::TestPermissionDelta::test_total_permissions_is_129` (DB row count) | `n == 133` | `n == 136` | B88 Pack 1 Gate 2 adds 3 permissions → 136. |
| 19 | `test_permissions_2_8b.py::TestPermissionDelta::test_total_permissions_matches_catalogue` (was `test_permission_catalogue_count_in_python_is_129`) | `len(PERMISSION_CATALOGUE) == 133` + name | `len(PERMISSION_CATALOGUE) == 136`, renamed to **`test_total_permissions_matches_catalogue`** per operator request | Catalogue size in Python → 136 + function-name no longer pinned to a stale integer. |
| 20 | `test_retro_wires.py::TestPermissionGrowth::test_retro_keeps_permission_growth_at_132` | `total == 133` | `total == 136` | B88 Pack 1 Gate 2 adds 3 permissions → 136. |
| 21 | `test_patch_3.py::TestPatch3Permissions::test_orphan_permissions_removed_from_db` | Orphan list **includes** `cost_codes.{create,edit,delete}` (must NOT be present) | Orphan list trimmed to `system_config.edit`, `notifications.{view,edit}` only | B88 Pack 1 Gate 2 RE-INTRODUCES `cost_codes.{create,edit,delete}` as wired permissions; they are no longer orphans. |
| 22 | `test_patch_3.py::TestPatch3Permissions::test_orphan_permissions_removed_from_catalogue` | Same orphan list incl. `cost_codes.*` | Trimmed to the 3 remaining live orphan guards | Same reason as #21 — catalogue gains the 3 codes back. |
| 23 | `test_cost_codes.py::TestCostCodesAPI::test_no_delete_endpoint_exists_for_cost_codes` (now `test_delete_endpoint_wired_for_cost_codes`) | `status_code in (404, 405)` | `status_code == 409` (and **renamed** to `test_delete_endpoint_wired_for_cost_codes`) | B88 Pack 1 Gate 3 wires `DELETE /api/cost-codes/{id}`; ACQ-01 has linked records so a 409 with blockers is the expected outcome. |
| 24 | `test_cost_codes.py::TestSeed::test_nine_sections` | asserts exactly 9 sections | **`@pytest.mark.xfail(strict=False, reason="B88 Pack 1 Gate 4 reseeds cost-code structure...")`** + `# TODO Gate 4: update expected section count to post-reseed truth and remove xfail.` | Gate 4 will reseed to 9 parent groups + 10 Construction subgroups + 129 codes; the 9-section assertion is updated AND un-xfailed in Gate 4. Per operator instruction (option (i)). |
| 25 | `test_auth_rbac.py` count-history comments (super_admin + director blocks) | Last line was Chat 45 (`133` / `129`) | Appended a B88 Pack 1 line: super_admin `133→136` via +3 granular `cost_codes`; director `129→131` via +2, delete excluded | Keeps the count-history audit trail current per operator instruction (a). |

### Gate 4 carry-over (tracked, will not be forgotten)

- `tests/test_cost_codes.py::TestSeed::test_nine_sections` — un-xfail and assert the correct post-reseed section count (likely 19 = 9 parents + 10 Construction subgroups, but **do not pre-guess** the number — derive it from the canonical seed at Gate 4 build time).
- The other two `TestSeed` cousins (`test_133_total_cost_codes`, `test_per_prefix_counts`) presently still assert against the *current* 133-code seed; once Gate 4 reseeds to 129 codes they will need updating too — same treatment, same gate. Logged here so we don't miss them.

---

## CHANGE 3 — Full pytest suite, twice, warm DB

Both runs executed sequentially against the warm pod DB (Postgres 16,
already containing the seeded baseline). Pytest collected the full
backend test tree (`/app/backend/tests/`).

### Run 1

```
1421 passed, 3 xfailed, 1 xpassed, 2 warnings in 284.41s (0:04:44)
```

### Run 2

```
1421 passed, 3 xfailed, 1 xpassed, 2 warnings in 283.12s (0:04:43)
```

- **Failed: 0** in both runs — target met.
- The 2 warnings are unrelated, pre-existing Pydantic v1-validator
  deprecation notices (`reference_data.py:72`) and the
  `python_multipart` rename notice in starlette — neither introduced
  by B88 Pack 1.
- The `1 xpassed` is a **non-strict** xfail and does not fail the
  suite (`strict=False` was deliberately chosen for the
  `test_nine_sections` marker per operator instruction).
- The 3 xfailed are pre-existing xfails left untouched (operator did
  not request changes to them).

---

## What is NOT in this submission

- **No GitHub save.** `Save to GitHub` is operator-driven and has not
  been triggered.
- **No Gate 4 work.** No `seed_cost_code_structure` script, no
  `test_cost_code_seed_structure.py`. Will start only after operator
  confirms Gate 3 on `origin/main`.
- **No frontend changes.** Gate 5 is still pending.

---

## Files touched in this submission

```
backend/tests/test_cost_code_delete_guard.py             (fixture: self-seed + teardown)
backend/tests/test_auth_rbac.py                          (3 assertions + 2 count-history comments)
backend/tests/test_bootstrap.py                          (alembic head startswith bump)
backend/tests/test_budget_changes_migration.py           (alembic head assertion)
backend/tests/test_cost_codes.py                         (xfail test_nine_sections + invert no-delete test)
backend/tests/test_document_folders.py                   (alembic head assertion)
backend/tests/test_migration_0025_actuals.py             (alembic head assertion)
backend/tests/test_migration_0028_user_preferences.py    (alembic head assertion + msg)
backend/tests/test_migration_0040_contact_book.py        (alembic head assertion)
backend/tests/test_migration_0041_drop_vat_registered.py (alembic head assertion)
backend/tests/test_patch_3.py                            (orphan list trimmed + perm count bump)
backend/tests/test_permissions_2_6.py                    (perm count bump)
backend/tests/test_permissions_2_7.py                    (perm count bump)
backend/tests/test_permissions_2_8a.py                   (perm count bump)
backend/tests/test_permissions_2_8b.py                   (perm count bump + function rename)
backend/tests/test_retro_wires.py                        (perm count bump)
backend/tests/test_sc_valuations_migration.py            (alembic head assertion)
backend/tests/test_subcontractors.py                     (alembic head assertion + msg)
backend/tests/test_subcontracts_migration.py             (alembic head assertion + msg)
```

No source-tree (`app/`, `alembic/versions/`) files were touched in
this re-submission — Gates 1 & 2 & 3-code remain exactly as they
were when you partially-accepted them. Only tests changed.

---

## Ready for operator raw-fetch verification on origin/main
