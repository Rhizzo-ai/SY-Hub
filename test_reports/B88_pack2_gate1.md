# B88 Pack 2 — Gate 1 backend report

## Run 2 (canonical, warm DB)

```
1483 passed, 3 xpassed, 2 warnings in 268.24s
Exit code: 0
```

## Baseline delta

- Pack 1 close: **1449 passed + 3 xpassed**
- Pack 2 Gate 1: **1483 passed + 3 xpassed**
- Delta: **+34 net** (18 in `test_budget_grid.py` + 16 in `test_budget_scope_enforcement.py`)

## Run 1 (warm-DB churn)

Identical 1483/3 — no first-run integrity-error churn this iteration
(the suite ran cold on entry and the warm-DB recovery now completes
inside the first invocation).

## Alembic state

```
alembic current: 0045_construction_scope (head)
```

## RBAC catalogue invariants

```
permissions = 136
roles = 10
project_manager → budgets.view_sensitive = REVOKED (False)
director / finance / super_admin → budgets.view_sensitive = INTACT
```

## Files landed (Gate 1)

- `backend/alembic/versions/0045_construction_scope.py` (NEW)
- `backend/app/models/cost_codes.py` — `+ included_in_construction_scope`
- `backend/app/services/cost_code_scope.py` (NEW)
- `backend/app/routers/budgets.py` — grid endpoint + scope filter +
  scope guards + serialiser scope branch + sensitive-key promotion
- `backend/app/routers/cost_codes.py` — surface scope flag on
  SectionRead / SectionCreate / SectionUpdate
- `backend/app/seed_rbac.py` — drop `budgets.view_sensitive` from PM
- `backend/scripts/seed_cost_code_structure.py` — scope flag on insert
  + restore-after-round-trip for canonical construction sections
- `backend/tests/test_budget_grid.py` (NEW — 18 tests)
- `backend/tests/test_budget_scope_enforcement.py` (NEW — 16 tests)
- `backend/tests/test_budgets.py` — `total_budget` joined sensitive-omit
  set for Tier 2 callers
- `backend/tests/test_budget_line_serialisation.py` — `_StubLine`
  stub gains `actuals_this_period` attribute (line-level money key
  promoted out of `view_sensitive` gate per §R5 / D4)
- `backend/tests/test_bootstrap.py` — alembic head sentinel `0044→0045`
- 9 other existing test files — alembic head sentinel `0044→0045`
