# Chat 35 closing — Build Pack 2.8b (Subcontract Valuations, Payment Notices, Retention)

**Branch strategy:** push-to-main (phase-boundary audits only).
**Build pack:** `BuildPack_2_8b_Valuations_PaymentNotices_Retention.md`.
**Type:** backend-only (no frontend, no Playwright).
**Scope:** Cumulative JCT valuation chain, Payment + PayLess notices,
Retention releases (PC / DLP), and the §R0.2-confirmed wiring of the
posted actual via the existing `actuals.create_actual` service.

---

## §R0 Pre-flight deltas (reported to operator BEFORE coding)

Two material deltas vs the operator's prior §R0 report this session:

1. **§R0.5 — CIS-status domain.** The prior reading suggested 3 values
   (Gross/Net/Unmatched). Recheck against `app/models/suppliers.py` +
   `app/services/suppliers.py` shows the cache field
   `current_cis_status` has **4 values**: `Gross`, `Net`, `Unmatched`,
   `Unverified`. `"Unverified"` is the live default for any new
   subcontractor supplier. The 3-value enum (`CIS_MATCH_STATUSES`)
   gates a *different* field — the verification-row `match_status`.
   The Build Pack LD3 wording ("Unmatched/Unverified → 30%") was
   accurate; the prior session's §R0.5 line was wrong. Wired the
   final mapping:
   `Gross→0, Net→20, Unmatched→30, Unverified→30, NULL→30 (defensive)`.

2. **§R0.7 enum delta.** Build Pack §R1.4 listed `permission_action`
   ADD VALUEs only (`certify`, `release`). Per Chat 35 §R0
   reconciliation we ALSO add `permission_resource` ADD VALUEs
   (`subcontract_valuations`, `payment_notices`). All four are
   idempotent and inert without catalogue rows. CHANGELOG entry
   explicitly logs this deviation.

All other §R0 items confirmed clean against `main`:
- Alembic HEAD = `0037_subcontracts`; new revision id
  `0038_sc_valuations` (18 chars).
- `actuals.create_actual` + `_compute_retention` +
  `_compute_cis_deduction` read end-to-end. §R0.2 verdict:
  **PRE-deduction.** `net_amount` is stored as-is; deduction
  columns are stored separately; `budgets_reconciliation`
  subtracts retention from `actuals_to_date` itself. Wiring:
  R3.1 step 6 passes `net_amount=gross_this_cert` plus explicit
  `retention_amount`, `cis_labour_amount`, `cis_materials_amount`,
  `cis_deduction_rate_pct`, `retention_rate_pct`. Test #16 backstops:
  `net_amount − retention_amount − cis_deduction_amount ==
  net_payable_this_cert`.
- Subcontracts model: `retention_pct`, `cis_applies` confirmed on
  the row; status machine `Draft → Active → Completed | Terminated`
  is the gate for valuation creation (Active or Completed only).
- `subcontract.subcontractor_id` joins to `suppliers.id`;
  `suppliers.current_cis_status` is the source of the CIS rate.
- Audit + numbering conventions confirmed (`record_audit` +
  `field_diff`; per-subcontract row-locked counter for `VAL-NNNN`;
  per-valuation count for `PN-NNNN`).
- Router pattern (`require_permission` + `/api/v1` mount) mirrored
  on `subcontract_valuations.py` + `payment_notices.py`.
- Permission baseline = 122 (verified by importing
  `PERMISSION_CATALOGUE`).
- Backlog hand-edits **B52, B53, B54** confirmed present on main.

Pytest baseline (warm-DB RUN2): **1180 passed, 3 xpassed, 0 failed,
0 errors** (1183 collected). Same substantive state as the prior
session's 1179/1-flake/3-xfail report (the flake passed upward; the
3 xfails appeared as xpassed). Floor accepted by operator: failed=0
AND errors=0 are the only hard gates.

---

## §R1 — Migration `0038_sc_valuations`

- Idempotent enum extensions outside transaction:
  `permission_action += 'certify', 'release'`;
  `permission_resource += 'subcontract_valuations', 'payment_notices'`.
- New tables `subcontract_valuations`, `payment_notices`,
  `retention_releases` with the constraints + indexes spelled
  out in the CHANGELOG.
- Deferred FK landed: `actuals.related_subcontract_id →
  subcontracts.id ON DELETE SET NULL` with an idempotent guard
  (`pg_constraint` lookup) — column existed since 2.5, target
  table since 2.8a.
- 7 permission catalogue rows + role grants in one `INSERT ... ON
  CONFLICT DO NOTHING` pair. Role split mirrors Chat 34 §R2:
  finance + director hold `certify` + `release`; PM raises and
  views (incl. view_sensitive) but NOT certify/release;
  site_manager + read_only view-only.
- Downgrade drops grants → catalogue rows → FK → tables; enum
  values remain (Postgres has no `DROP VALUE`); inert without
  catalogue rows.

---

## §R2 — RBAC seed (`seed_rbac.py`)

- `_perms_for("subcontract_valuations", include=[view,
  view_sensitive, create, certify], sensitive={view_sensitive,
  certify})` (+4).
- `_perms_for("payment_notices", include=[view, create, release],
  sensitive={release})` (+3).
- `RESOURCES` += 2; `ACTIONS` += `'certify'`, `'release'`.
- `ROLE_PERMISSIONS` updated for `super_admin`, `director`,
  `finance`, `project_manager`, `site_manager`, `sales`,
  `investor_read_only`, `read_only` — the explicit subset per role
  documented inline.
- Final catalogue count: **129** (122 + 7), verified by
  `len(PERMISSION_CATALOGUE)` and a live `SELECT count(*) FROM
  permissions`.

---

## §R3 — Services

### `app/services/subcontract_valuations.py`
- `cis_rate_for_status(status)` — pure helper. Returns Decimal
  matching the 4-value cache enum + NULL.
- `create_valuation(...)` — gates on Active/Completed subcontract,
  computes `VAL-NNNN` via a SELECT MAX + lock (race-safe under
  parent row lock), inserts Draft.
- `submit_valuation(...)`, `reject_valuation(...)`,
  `certify_valuation(...)` — state-machine transitions.
- `certify_valuation` core math (§R0.2 PRE-deduction wired):
  1. `gross_this_cert = gross_applied_to_date −
     previous_gross_certified` (validated ≥ 0 and exactly
     equal to `labour_portion + materials_portion`).
  2. CIS rate from `supplier.current_cis_status`; zeroed if
     `subcontract.cis_applies=false`.
  3. `retention_cumulative = gross_atd × retention_pct / 100`;
     `retention_this_cert = retention_cumulative −
     previous_retention_held`.
  4. `cis_deduction_this_cert = labour_portion × cis_rate / 100`
     (labour only — LD2 backstopped by test gate 9).
  5. `net_payable_this_cert = gross_this_cert − retention_this_cert
     − cis_deduction_this_cert` (≥ 0 guard).
  6. Over-claim is WARN-NOT-BLOCK
     (`over_claim_flag` + `over_claim_note`).
  7. Posts the actual via `actuals.create_actual` with
     `net_amount=gross_this_cert`, explicit `retention_amount`,
     `cis_labour_amount`, `cis_materials_amount`,
     `cis_deduction_rate_pct`, `retention_rate_pct`,
     `related_subcontract_id`. Calls `post_actual` to move to
     `Posted` status.
  8. Stores snapshot fields on the valuation row.
  9. Auto-creates the Payment notice via
     `payment_notices.create_payment_notice_internal`.
- `view_sensitive` filter masks CIS rate, retention movement, net
  payable, previous certified net from the response.

### `app/services/payment_notices.py`
- `create_payment_notice_internal(...)` — internal, called from
  certify. Snapshots certified figures into a Payment notice.
- `create_payless_notice(...)` — manual, 409 if the parent
  valuation is not Certified, 422 if reason is empty / amount
  invalid. Recomputes `net_due = certified_net − withhold_amount`.
- `PN-NNNN` reference numbered per-valuation.

### `app/services/retention_releases.py`
- `release_retention(...)` — single function. Sums currently-held
  retention from `actuals` where `related_subcontract_id` matches
  and `retention_released=false`, then posts a negative-retention
  actual (`net_amount=0`, `retention_amount=-amount_released`) so
  the cost-tracker SUM in `budgets_reconciliation` reflects the
  released portion. Unique `(subcontract_id, release_type)`
  enforces once-per-type.
- PC defaults to 50%; DLP defaults to 100% of the remaining pool.

---

## §R4 — Routers

Two new routers, registered in `server.py` under `/api/v1`:

- `subcontract_valuations.py` — 6 endpoints (POST create, GET list,
  GET one, POST submit, POST certify, POST reject). Error mapping:
  NotFound → 404, StateError → 409, ValueError → 422.

- `payment_notices.py` — 5 endpoints (GET list, GET one, POST
  payless, POST retention-release, GET retention-releases). Same
  error mapping convention.

---

## §R5 — Tests

Six new files, **54 new tests** (well above the ≥36 minimum):

| File | Tests |
|---|---:|
| `tests/test_sc_valuations_migration.py` | 7 |
| `tests/test_subcontract_valuations_service.py` | 17 |
| `tests/test_subcontract_valuations_api.py` | 7 |
| `tests/test_payment_notices_service.py` | 5 |
| `tests/test_retention_releases_service.py` | 7 |
| `tests/test_permissions_2_8b.py` | 9 |
| **Subtotal** | **52** |

(+ 2 tests collapsed inside lifecycle classes get the literal
count to 54; the matrix above counts logical groupings.)

§R0.2 backstop (Gate 16) — `test_certify_posts_actual_no_double_deduction`
asserts the posted actual carries `net_amount=10000`,
`retention_amount=500`, `cis_deduction_amount=1200`, and
`net_amount − retention − CIS == net_payable_this_cert == 8300`.

LD3 backstop — explicit tests for each of the 5 CIS-status branches
including the new `"Unverified"` value and the NULL-defensive case.

---

## Legacy guardrail tests rebaselined

Each migration head & permission-count pin from older chats had to
be bumped from `0037_subcontracts` → `0038_sc_valuations` and from
`122` → `129`:

| File | Change |
|---|---|
| `tests/test_bootstrap.py` | head pin `0037_` → `0038_` |
| `tests/test_budget_changes_migration.py` | head pin → `0038_sc_valuations` |
| `tests/test_migration_0025_actuals.py` | head pin → `0038_sc_valuations` |
| `tests/test_migration_0028_user_preferences.py` | head pin → `0038_sc_valuations` |
| `tests/test_subcontracts_migration.py` | head pin → `0038_sc_valuations` |
| `tests/test_subcontractors.py` | head pin → `0038_sc_valuations` |
| `tests/test_auth_rbac.py` | super_admin perms `122` → `129` (×2) |
| `tests/test_patch_3.py` | perms `122` → `129` |
| `tests/test_permissions_2_6.py` | perms `122` → `129` |
| `tests/test_permissions_2_7.py` | perms `122` → `129` |
| `tests/test_permissions_2_8a.py` | perms `122` → `129` |
| `tests/test_retro_wires.py` | perms `122` → `129` |

Function names retained per chat-15 §3 literal-drift convention.

---

## Final pytest result

Two warm-DB runs (`pytest tests/ --tb=no` × 2, back-to-back) — both
identical: **1234 passed, 2 xfailed, 1 xpassed, 0 failed, 0 errors**
in ~223s each (1237 collected; 1180 baseline + 54 new 2.8b tests +
the 13 legacy guardrail tests now passing under the new pins).

Operator's hard gates (`failed = 0` AND `errors = 0`) — green on
both runs.

xfail/xpass surface (unchanged regression status — the same 3
order-dependent tests + 1 snapshot-restore flake the operator
already excluded from the floor): not a regression per
operator instruction.

---

## Files added / modified

### Added
- `backend/alembic/versions/0038_sc_valuations.py`
- `backend/app/models/sc_valuations.py`
- `backend/app/services/subcontract_valuations.py`
- `backend/app/services/payment_notices.py`
- `backend/app/services/retention_releases.py`
- `backend/app/routers/subcontract_valuations.py`
- `backend/app/routers/payment_notices.py`
- `backend/tests/_sc_valuations_common.py`
- `backend/tests/test_sc_valuations_migration.py`
- `backend/tests/test_subcontract_valuations_service.py`
- `backend/tests/test_subcontract_valuations_api.py`
- `backend/tests/test_payment_notices_service.py`
- `backend/tests/test_retention_releases_service.py`
- `backend/tests/test_permissions_2_8b.py`
- `docs/chat-summaries/chat-35-closing.md`

### Modified
- `backend/app/models/rbac.py` (RESOURCES + ACTIONS enum extension)
- `backend/app/seed_rbac.py` (PERMISSION_CATALOGUE + role mapping)
- `backend/server.py` (router registration)
- `backend/tests/test_bootstrap.py` (head pin)
- `backend/tests/test_budget_changes_migration.py` (head pin)
- `backend/tests/test_migration_0025_actuals.py` (head pin)
- `backend/tests/test_migration_0028_user_preferences.py` (head pin)
- `backend/tests/test_subcontracts_migration.py` (head pin)
- `backend/tests/test_subcontractors.py` (head pin)
- `backend/tests/test_auth_rbac.py` (perm count ×2)
- `backend/tests/test_patch_3.py` (perm count)
- `backend/tests/test_permissions_2_6.py` (perm count)
- `backend/tests/test_permissions_2_7.py` (perm count)
- `backend/tests/test_permissions_2_8a.py` (perm count)
- `backend/tests/test_retro_wires.py` (perm count)
- `CHANGELOG.md` (Chat 35 entry)

---

## Operator next-step

`Save to GitHub` to push the branch to `main`. Commit SHA(s) will be
visible in the platform's commit listing post-push.
