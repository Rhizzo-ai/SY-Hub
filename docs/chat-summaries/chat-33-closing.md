# Chat 33 closing — Build Pack 2.6 (Budget Change Control)

**Branch strategy:** push-to-main (phase-boundary audits only).
**Build pack:** `BuildPack_2.6_BudgetChangeControl.md`.
**Type:** backend-only (frontend split deferred to 2.6-FE).

---

## §R0 Pre-flight deltas (reported to operator BEFORE coding)

The Build Pack lists 9 verification items. 7 of 9 matched expectation
exactly. Two material deltas required operator clarification before
proceeding:

1. **Audit mechanism (§R0.6).** Budgets service has **zero**
   `record_audit` calls; ALL 10 audit writes live in
   `app/routers/budgets.py` lines 322–778. By contrast, suppliers /
   CIS / PO / PO approvals / supplier_documents all audit IN the
   service layer. New BCR code follows the **newer Track-2
   service-layer pattern** (operator decision Q2=a). Divergence noted
   in service docstring.

2. **`budget_changes` resource pre-seeded (§R0.8).** The Build Pack
   §R0 line 8 says: "Confirm `RESOURCES` enum in `models/rbac.py`
   needs `budget_changes` added." Reality: the enum slot AND four
   permission rows
   (`budget_changes.{view,create,edit,approve}`) were already seeded
   in an earlier chat. Build Pack §R2's `include=
   ["view","create","submit","approve","apply"]` therefore did NOT
   apply cleanly — it omits the pre-seeded `edit`. Operator decision
   Q1=b: **additive — keep `edit`, add `submit`+`apply`**. Final
   delta +2 (not +5). Permission count 110 → **112** (not 115).
   Test gate 31 reads literal 112 with an inline deviation comment.

All other §R0 items (HEAD = `0035_subcontractors`; `budget_lines`
already has `approved_changes` and NOT `is_contingency`; budget status
enum + TERMINAL/LINE_FROZEN sets;  `_recompute_line` +
`recompute_summary` reusability; `get_budget_self_approval_threshold`
+ `BudgetSelfApprovalError` importability; `_load_budget_for_write`
write-path loader; router conventions; existing `budgets.approve`
perm) were confirmed against `main` as Build-Pack-expected.

---

## §R1–§R5 outcomes

### Migration `0036_budget_changes` (§R1)
- `permission_action += 'apply'` idempotent (`submit` already present).
- `budget_lines.is_contingency` BOOL NOT NULL DEFAULT false. Backfill
  clean — verified 0 rows where `is_contingency IS NOT FALSE`.
- New tables `budget_changes` + `budget_change_lines`.
  - Header: tenant_id, budget_id, reference, change_type, status,
    title, reason, net_impact, source_variation_id (no FK), workflow
    stamps (submitted/approved/applied/rejected × at + by + reason),
    created_at/by, updated_at, indexes
    `(budget_id, status)` + `(tenant_id)`, unique `(budget_id, reference)`,
    CHECK constraints on type + status.
  - Detail: tenant_id, budget_change_id, budget_line_id (FK
    RESTRICT — protect Applied BCR records), delta, created_at,
    index `(budget_change_id)`.
- Down/up round-trip verified clean against live PG.

### Permissions (§R2)
- 110 → **112** (operator-confirmed additive interpretation).
- New rows: `budget_changes.submit` (non-sensitive),
  `budget_changes.apply` (sensitive).
- Role grants (verified against live `role_permissions` table):
  - `super_admin`, `director`: full set (all 6 budget_changes.*) via
    the seed_rbac wildcard.
  - `finance`: view + approve + apply (no submit / create).
  - `project_manager`: view + create + edit + submit + approve + apply.
  - All others: none.
  - `apply` mapping verified IDENTICAL to `approve` mapping
    (`test_apply_role_mapping`).

### Services (§R3)
- `services/budget_changes.py` — single new module.
- `create_bcr` enforces parent must be `Active`/`Locked`; per-type
  invariants (Transfer net-zero, ContingencyDrawdown net-zero +
  non-contingency-source rejection, Adjustment non-zero); advisory
  create-time negative-budget check; race-safe BCR-NNNN sequence
  under parent row lock.
- Workflow transitions row-lock parent + BCR via FOR UPDATE.
- `approve_bcr` — LD2 self-approval guard on GROSS movement
  (`sum(abs(delta))` — NOT net_impact). Tested literally with a
  £50k↔£50k Transfer (net 0, gross 100k) — blocks at the £10k
  threshold per the Build Pack spec.
- `apply_bcr` — re-asserts parent still Active/Locked, FRESH reads
  of every line under FOR UPDATE, defensive negative-budget guard,
  ALL-OR-NOTHING write, then calls the EXISTING `_recompute_line`
  + `recompute_summary` to propagate the change into header FFC /
  variance / total_budget. NO duplicated math.
- Reads: `get_bcr`, `list_bcrs(status?)`, `change_log` (all BCRs
  for a budget, newest first).
- Audit pattern: `record_audit` + `field_diff` in-service (newer
  Track-2 convention); divergence from legacy budgets noted in
  module docstring.

### Routers (§R4)
- `routers/budget_changes.py`, mounted at `/api/v1` in `server.py`.
- 10 endpoints: POST/GET list/GET one/PATCH, +submit, +approve,
  +reject (reason required → 422 if missing), +withdraw, +apply,
  + GET `/budgets/{id}/change-log` convenience read.
- Error mapping: 404 cross-tenant, 422 validation, 409 state, 403
  self-approval.

### Tests (§R5)
- **39 new test functions** split across **4 files** matching the
  Build Pack §R5 naming convention:
  - `tests/test_budget_changes_migration.py` — **3 tests** (schema
    + alembic head sentinel + is_contingency backfill).
  - `tests/test_budget_changes_service.py` — **15 tests** (service-
    layer invariants 10 + apply-effects 5).
  - `tests/test_budget_changes_api.py` — **17 tests** (HTTP workflow
    7 + self-approval 5 + API surface 5).
  - `tests/test_permissions_2_6.py` — **4 tests** (permissions /
    regression — mirrors test_permissions_2_7.py shape).
  Shared helpers in `tests/_bcr_common.py` (NOT collected — leading
  underscore prefix).
- All 35 Build Pack §R5 acceptance gates covered across the four
  files.
- Baseline-drift literals bumped (chat-15 §3 pattern) in 8 legacy
  test files:
  - `test_auth_rbac.py` — super_admin 110→112, director 106→108
  - `test_bootstrap.py` — head sentinel 0035_ → 0036_
  - `test_migration_0025_actuals.py` — head literal → 0036_budget_changes
  - `test_migration_0028_user_preferences.py` — head literal → 0036_budget_changes
  - `test_patch_3.py` — 110 → 112
  - `test_retro_wires.py` — 110 → 112
  - `test_permissions_2_7.py` — 110 → 112
  - `test_subcontractors.py` — head literal → 0036_budget_changes
- **Pytest 2nd-run WARM-DB: 1110 passed, 3 xpassed, 0 failed,
  0 errors, 189.07s.** Regression floor 1071 honoured (+39 net new).

---

## Deviations (explicit)

1. **D1 — Permission delta +2, not +5.** Build Pack §R2 predicted
   baseline+5 = 115; live seed already had `view/create/edit/approve`.
   Operator decision Q1=b: additive — final +2 = 112.
2. **D2 — Audit pattern.** BCRs audit at service layer (suppliers
   pattern), not router layer (legacy budgets pattern). Operator
   decision Q2=a; documented in service docstring.
3. **D3 — Withdrawn transitions write `Update` audit action**
   (not a new dedicated verb). `AUDIT_ACTIONS` already covers the
   semantic via `metadata.kind="bcr_withdrawn"`. Avoided minting a
   new enum value for a single workflow path.
4. **D4 — `reference` uniqueness.** Build Pack §R3.1 names the
   service-generated `BCR-NNNN`; the migration enforces it via a
   table-level `UNIQUE (budget_id, reference)` constraint, not a
   partial-index. Behaviour identical; simpler constraint shape.
5. **D5 — Audit verb mapping.** `Apply` re-uses the existing
   `Approve` audit action (with `metadata.kind="bcr_applied"`) for
   the same reason as D3: minting a new enum value for a
   sub-workflow phase is over-engineering. The audit row's metadata
   captures the semantic.

---

## Out of scope (honoured)

- Frontend / React / Playwright — later split 2.6-FE.
- 2.8 variation → BCR generation. `source_variation_id` is a
  nullable UUID stub with NO FK; 2.8 will add the FK and the
  generation path.
- Per-role / per-user approval limits beyond the single global
  threshold — backlog B43.
- Contingency-remaining reporting / dashboards — the
  `is_contingency` flag enables it; the report itself is later.
- Multi-level approval chains (>1 approver) — not in any current
  track.
- Editing / reversing an Applied BCR — by design, corrections are
  a new opposing BCR. Not a gap.

---

## 2.6 Self-Report

```
- §R0 pre-flight deltas: 2 material (audit-mechanism location + pre-seeded
  budget_changes perms); 7 confirmed clean.
- Audit mechanism found: budgets service has NO record_audit calls; ALL
  10 audit writes live in routers/budgets.py. New BCR code follows the
  newer Track-2 service-layer pattern (suppliers/CIS/PO).
- Alembic: HEAD was 0035_subcontractors; migration 0036_budget_changes;
  round-trip down -1 / up head clean on live PG.
- permission_action enum: new values = ['apply']. (submit already present
  from Prompt 2.2.)
- Permission count: 110 → 112 (operator-confirmed additive interpretation;
  Build Pack predicted 115 but +5 predated the pre-seeded
  budget_changes.{view,create,edit,approve}).
- Tables added: budget_changes, budget_change_lines
  (+ budget_lines.is_contingency).
- Routers registered: budget_changes (10 endpoints incl. change-log).
- Self-approval guard: reused get_budget_self_approval_threshold,
  gross-movement basis (sum(abs(delta))); NULL-creator fail-open;
  super-admin NOT exempt.
- Tests: 39 new functions across 4 files (matching §R5 naming):
    tests/test_budget_changes_migration.py  (3)
    tests/test_budget_changes_service.py    (15)
    tests/test_budget_changes_api.py        (17)
    tests/test_permissions_2_6.py           (4)
    tests/_bcr_common.py                    (shared helpers; not collected)
  pytest 2nd-run WARM-DB:
  1110 passed, 3 xpassed, 0 failed, 0 errors, 189.07s.
  Regression floor 1071 honoured (+39 net new).
- Deviations: D1 perm-count +2 (not +5); D2 service-layer audit;
  D3 Withdrawn → Update audit verb + metadata; D4 reference UNIQUE
  constraint vs partial-index; D5 Apply → Approve audit verb.
- Files changed:
    NEW: app/models/budget_changes.py
         app/services/budget_changes.py
         app/routers/budget_changes.py
         alembic/versions/0036_budget_changes.py
         tests/_bcr_common.py
         tests/test_budget_changes_migration.py
         tests/test_budget_changes_service.py
         tests/test_budget_changes_api.py
         tests/test_permissions_2_6.py
         docs/chat-summaries/chat-33-closing.md
    MODIFIED: app/models/budgets.py (is_contingency on BudgetLine)
              app/models/rbac.py (ACTIONS += 'apply')
              app/seed_rbac.py (budget_changes perms incl. submit+apply;
                                PM + finance role grants extended)
              server.py (budget_changes_router import + mount)
              tests/test_auth_rbac.py (110→112; 106→108)
              tests/test_bootstrap.py (head sentinel 0035→0036)
              tests/test_migration_0025_actuals.py (head literal)
              tests/test_migration_0028_user_preferences.py (head literal)
              tests/test_patch_3.py (110→112)
              tests/test_retro_wires.py (110→112)
              tests/test_permissions_2_7.py (110→112)
              tests/test_subcontractors.py (head literal)
              CHANGELOG.md (Chat 33 entry)
- Commits: R1–R5 code + tests in one commit; closing docs (CHANGELOG +
  this file) in a separate commit. NOT pushed-confirmed — operator pushes
  via Save to GitHub.
```
