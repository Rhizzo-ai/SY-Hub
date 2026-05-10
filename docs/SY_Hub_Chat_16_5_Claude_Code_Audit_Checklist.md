# Chat 16.5 — Post-Emergent Build-State Audit Checklist

**For:** Claude Code (independent auditor, post-Emergent execution).
**Scope:** Verify Emergent's 16.5 patch lands cleanly AND surface any prompt-vs-codebase mismatches the prompt couldn't catch upfront.
**Branch under audit:** `chore/chat-16.5-coverage-and-brand`.

This checklist exists because the Chat 17 prep audit (run by triage Claude) caught structural issues in the prompt itself, but could NOT verify several claims about the live codebase without files it didn't have access to. Those go here.

---

## A. Pre-checks (before reading the diff)

```bash
cd /app
git checkout chore/chat-16.5-coverage-and-brand
git log --oneline main..HEAD
# expect: 1-3 logical commits (R2 / R3 / R4 if split, or 1 combined)

git diff main --stat
# expect: 4-5 files changed
#   backend/tests/test_budgets.py        (large +)
#   frontend/design_guidelines.json      (small +)
#   frontend/tailwind.config.js          (small +)
#   frontend/src/index.css               (small +, optional)
#   CHANGELOG.md                         (small +)
```

If any other file shows up in the diff — flag it. The prompt forbids production code changes.

---

## B. Six items the prompt couldn't verify upfront

These were flagged in the prompt audit as residual risk; STOP conditions in the prompt should have surfaced them. Verify each.

### B1 — `budgets.lock` permission does NOT exist; lock requires `budgets.edit`

**Prompt assumption (Build Pack #85):** "PM users CAN lock a budget (PM has `budgets.lock` permission per role seed)."

**Suspected reality:** No `budgets.lock` permission. Lock endpoint requires `budgets.edit`. PM has only `budgets.create` per `CHANGELOG.md` line 48. Therefore PM → POST lock → 403, not 200.

**Audit:**
```bash
grep -n "budgets.lock\|budgets.edit" /app/backend/app/seed_rbac.py
grep -n "require_permission" /app/backend/app/routers/budgets.py | grep lock
psql $DATABASE_URL -c "SELECT code FROM permissions WHERE code LIKE 'budgets.%' ORDER BY code;"
psql $DATABASE_URL -c "SELECT r.name, p.code FROM roles r JOIN role_permissions rp ON rp.role_id=r.id JOIN permissions p ON p.id=rp.permission_id WHERE r.name='project_manager' AND p.code LIKE 'budgets.%';"
```

**Expect:**
- No `budgets.lock` row in permissions.
- Lock endpoint requires `budgets.edit`.
- PM has `budgets.create` only (or whatever the seed actually grants — list them).

**Verify in the test:**
```bash
grep -A 30 "test_post_lock_endpoint_with_pm_session" /app/backend/tests/test_budgets.py
```

The shipped test should assert the actual response code (likely 403, given PM lacks `budgets.edit`). If it asserts 200, the test was written against the wrong premise — flag for re-roll.

---

### B2 — Per-line lock state column is `is_locked`, not `frozen_at`

**Prompt assumption (Build Pack #33/#34):** Spec hedges with "the post-lock column the service writes (e.g. `frozen_at`)."

**Suspected reality:** `frozen_at` does not exist. Per-line column is `is_locked` boolean. Visible in `app/routers/budgets.py:123` (`_serialise_line` dict).

**Audit:**
```bash
grep -n "is_locked\|frozen_at" /app/backend/app/models/budgets.py
grep -n "is_locked\|frozen_at" /app/backend/alembic/versions/0024_budgets.py
grep -A 20 "test_lock_in_memory_line_state_consistent_with_db\|test_unlock_in_memory_line_state_consistent_with_db" /app/backend/tests/test_budgets.py
```

**Expect:**
- Model + migration use `is_locked`. No `frozen_at` column.
- Tests #33 and #34 reference `is_locked`.

If tests reference `frozen_at`, they would have failed at import or at first assertion — Emergent should have hit the STOP condition before writing them. If they shipped against `frozen_at`, that's a serious red flag (means Emergent invented the column).

---

### B3 — Audit log column name is `metadata_json`, not `metadata`

**Prompt assumption (Build Pack #39):** Spec uses `metadata['superseded_id']` (Python dict access in description), should resolve to SQL column access.

**Suspected reality:** Column is `metadata_json` (verified via existing `test_create_lock_unlock_close_all_audited` query pattern in `test_budgets.py`).

**Audit:**
```bash
grep -A 15 "test_create_version_writes_audit_log_with_superseded_id" /app/backend/tests/test_budgets.py
```

**Expect:** SQL query selects `metadata_json` and uses `metadata_json->>'kind' = 'new_version'` filter, plus `action='Create'` (NOT `Status_Change` — new_version uses `Create` per `routers/budgets.py:393`).

If the test queries a non-existent `metadata` column, it'll fail with an SQL error.

---

### B4 — `refresh-attention` endpoint path: `/internal/`, not `/admin/`

**Prompt assumption (Build Pack #78):** Test calls `POST /admin/budgets/refresh-attention`.

**Suspected reality:** Endpoint mounts under `/internal/budgets/refresh-attention` per router docstring line 27.

**Audit:**
```bash
grep -n "refresh-attention\|refresh_attention" /app/backend/app/routers/budgets.py
grep -A 20 "test_requires_attention_clears_when_no_longer_matching" /app/backend/tests/test_budgets.py
# Also cross-check existing pattern:
grep -A 10 "test_admin_scan_runs" /app/backend/tests/test_budgets.py
```

**Expect:** New test #78 uses the same path as the existing `test_admin_scan_runs` test. If they diverge, one is wrong.

---

### B5 — `budget_svc.lock` row-level locking (Build Pack #14)

**Prompt assumption:** Lock service uses `SELECT ... FOR UPDATE` to serialise concurrent lock attempts.

**Reality (unverifiable from triage chat without `services/budgets.py`):** Router state-change path explicitly passes `lock_for_update=False` to `_load_budget_for_write`. The FOR UPDATE may exist inside `budget_svc.lock` itself; may not.

**Audit:**
```bash
grep -n "with_for_update\|for_update_of\|FOR UPDATE" /app/backend/app/services/budgets.py
```

**Expect outcomes:**
- **If FOR UPDATE present:** test #14 should be the two-connection NOWAIT pattern from the prompt's R2.
- **If FOR UPDATE absent:** Emergent should have hit the prompt's STOP condition and reported. Test #14 should be deferred (added to backlog), not silently shipped as a no-op.

Flag either: (a) test #14 silently passing with `assert True`-style stub, or (b) Emergent fabricated a service modification to add FOR UPDATE (production code change — explicit prompt violation).

---

### B6 — `site_manager` role exists in seed (Build Pack #81)

**Prompt assumption:** Test #81 needs a site_manager-roled user. Prompt instructs Emergent to construct one via raw SQL if not pre-seeded, OR STOP if the role itself is missing.

**Audit:**
```bash
psql $DATABASE_URL -c "SELECT name FROM roles ORDER BY name;"
grep -rn "site_manager" /app/backend/app/seed_rbac.py /app/backend/app/seed_users.py 2>/dev/null
grep -A 30 "test_post_from_appraisal_403_with_site_manager_session" /app/backend/tests/test_budgets.py
```

**Expect:**
- `site_manager` role exists in `roles` table.
- New test creates a site_manager test user via raw SQL OR uses an existing helper.
- POST → 403 assertion present.

If the role doesn't exist, Emergent should have STOPped. If the test was written despite the role missing, flag.

---

## C. Hard-rule compliance (R1)

```bash
# C1. Production code untouched
git diff main -- 'backend/app/services/' 'backend/app/routers/' 'backend/app/models/' 'backend/app/schemas/' 'frontend/src/pages/' 'frontend/src/components/'
# expect: empty output

# C2. No new migrations
git diff main -- 'backend/alembic/versions/'
# expect: empty output. alembic head still 0024_budgets.

# C3. Permission count unchanged
psql $DATABASE_URL -c "SELECT COUNT(*) FROM permissions;"
# expect: 84

# C4. No new dependencies
git diff main -- 'backend/requirements.txt' 'frontend/package.json'
# expect: empty output

# C5. No deletion of existing tests
git log -p main..HEAD -- backend/tests/test_budgets.py | grep -E "^-def test_|^-    def test_"
# expect: empty output. Additive only.

# C6. Test count delta
cd /app/backend
python -m pytest tests/ --ignore=tests/test_c3_governance_smoke.py --collect-only -q 2>/dev/null | tail -3
# expect: 664 tests collected (up from 641)
```

---

## D. Test execution

```bash
cd /app/backend
python -m pytest tests/test_budgets.py -v --ignore=tests/test_c3_governance_smoke.py 2>&1 | tee /tmp/budgets_test_run.log
# expect: 67 passed (44 existing + 23 new)

python -m pytest tests/ --ignore=tests/test_c3_governance_smoke.py -q
# expect: 664 passed

python -m app.bootstrap; echo "rc=$?"
# expect: rc=0
```

For each of the 23 new tests, confirm it appears in the verbose output as `PASSED`. Any `SKIPPED`, `XFAIL`, or `ERROR` is a flag.

The 23 expected names (verbatim from Build Pack §R5):
```
test_original_budget_total_matches_appraisal_total_cost
test_create_handles_zero_cost_lines_appraisal
test_concurrent_lock_serialised_via_select_for_update
test_create_new_version_carries_programme_task_link
test_create_new_version_does_not_carry_items
test_lock_in_memory_line_state_consistent_with_db
test_unlock_in_memory_line_state_consistent_with_db
test_create_version_writes_audit_log_with_superseded_id
test_ftc_manual_uses_provided_value
test_ftc_percentage_complete
test_ftc_percentage_complete_falls_back_to_budget_remaining_when_zero
test_variance_pct_zero_when_current_budget_zero
test_variance_pct_overflow_handled_gracefully
test_create_item_via_relationship_collection_populated
test_item_amount_validation_warns_but_does_not_block
test_delete_line_cascades_items
test_header_summary_refreshed_at_advances_on_recompute
test_existing_budgets_approve_perm_still_present
test_pm_role_does_not_have_budgets_admin
test_requires_attention_clears_when_no_longer_matching
test_post_from_appraisal_403_with_site_manager_session
test_post_lock_endpoint_with_pm_session
test_get_list_budgets_for_project_filters_by_is_current
```

If any name diverges from this list, flag (Emergent renamed a test).

---

## E. Brand patch verification

```bash
# E1. design_guidelines.json structure
jq '.brand_palette.usage_rules' /app/frontend/design_guidelines.json
# expect: array of 5 rule strings, no parse error

jq '.colors.brand.description' /app/frontend/design_guidelines.json
# expect: string mentioning both slate-900 baseline AND teal override

# E2. tailwind.config.js tokens
grep -A 5 "sy-teal\|sy-orange\|sy-grey" /app/frontend/tailwind.config.js
# expect: tokens registered (literal hex OR CSS-var pattern)

# E3. index.css vars (only if CSS-var pattern was used)
grep -E "^\s*--sy-" /app/frontend/src/index.css
# expect: 7 lines OR empty (if literal hex pattern in tailwind.config.js)

# E4. Frontend builds
cd /app/frontend
yarn build 2>&1 | tail -20
# expect: clean build, no warnings about unknown classes

# E5. No teal/orange applied to existing components
git diff main -- 'frontend/src/' | grep -E "sy-teal|sy-orange|--sy-"
# expect: matches in tailwind.config.js + index.css ONLY (NOT in any component)
```

---

## F. CHANGELOG verification

```bash
head -25 /app/CHANGELOG.md
# expect:
#   Line 1: # Change Log
#   Line 7: ## Format
#   Line 12: ## Entries
#   Line 14ish: ## Chat 16.5 — Coverage debt + brand patch — closed YYYY-MM-DD
#   Line further down: ## 2.4A — Budgets Core (Backend) (2026-05-09)

grep -c "^## 2.4A — Budgets Core" /app/CHANGELOG.md
# expect: 1 (no duplicate)

grep -c "^## Chat 16.5" /app/CHANGELOG.md
# expect: 1
```

---

## G. Spec-vs-service mismatches Emergent should have reported

If any of the prompt's STOP conditions fired (#10, #14, #33-34, #46, #65, #70, #78, #81), Emergent's report should call them out by Build Pack number with the discrepancy.

Cross-reference Emergent's reported output against:
1. Was a STOP triggered? Yes/No per test.
2. If Yes, was the test deferred (added to backlog) or silently stubbed? Defer is correct; stub is a violation.
3. Was a backlog entry written for any deferred test? Should land in `/app/docs/SY_Hub_Phase2_Backlog.md`.

---

## H. Sign-off gate

All of the below must be ✓ before merging to `main`:

- [ ] B1–B6 verified, mismatches explainable
- [ ] C1–C6 hard rules respected (no production code touched)
- [ ] D 664 tests passing, all 23 named tests PASSED
- [ ] E brand tokens registered, no components touched
- [ ] F CHANGELOG single Chat 16.5 entry inserted at correct anchor
- [ ] G STOP condition outcomes match Emergent's report
- [ ] alembic head still `0024_budgets`
- [ ] permission count still 84
- [ ] bootstrap rc=0

If any check fails, do NOT merge. Return to triage chat with the specific failure for re-spec or re-roll.

---

## Reporting back

Post a summary block:

```
Chat 16.5 audit — <PASS | FAIL | PASS-WITH-NOTES>

Tests: 641 → <N> passing (delta: <D>)
Files changed: <list>
STOP conditions: <list any that fired, with Emergent's resolution>
Hard rules: <all respected | violation: <which>>
Brand: <tokens registered, no component changes | issue: <what>>
CHANGELOG: <single 16.5 entry at correct position | issue: <what>>

Recommendation: <merge | hold for fixes | re-roll>
```

End of checklist.
