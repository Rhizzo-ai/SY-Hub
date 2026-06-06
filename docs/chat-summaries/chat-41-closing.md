# Chat 41 — Build Pack 2.7-BE-rev-A closing summary

**Pack:** Build Pack 2.7-BE-rev-A — Suppliers Contact-Book Rework (backend only)
**Branch base:** main @ `0039_committed_single_writer`, 129 permissions, 10 roles
**Head after this pack:** **`0040_contact_book_rework`**
**Permissions:** **131** (129 → 131; `+trades.view`, `+trades.create`)
**Roles:** 10 (unchanged)
**Backlog file (`docs/SY_Hub_Phase2_Backlog.md`):** NOT touched per the
opener (operator-owned).
**Auth flows touched:** none.
**Frontend:** untouched (2.7-FE still wired to the 2.7 schema — see §
"Known-stale FE" below).

---

## Gate run timeline

| Gate | Scope | Status |
|---|---|---|
| Gate 1 | §R1 migration (`0040_contact_book_rework`) + §R2 models (Trade, Supplier reshape, RESOURCES tuple) | ✅ landed; VERIFY in `memory/Gate1_VERIFY_2.7-BE-rev-A.md` |
| Gate 2 | §R3 services + §R4 routers + `seed_rbac.py` additions | ✅ landed; VERIFY in `memory/Gate2_VERIFY_2.7-BE-rev-A.md`; live API smoke green |
| Gate 3 | §R5 tests + §R6 seed + CHANGELOG + this closing | ✅ landed; second-run pytest count + per-file breakdown below |

## What landed in Gate 3 (this entry)

### §R5 — Test rework

- **HARD-BREAK raw-SQL INSERT fixes** in two files — without these,
  the moment `0040` lands every run of these two suites fails at the
  column-unknown error:
  - `tests/test_budget_integrity_committed.py` L78–87 — removed
    `default_vat_rate` from BOTH the column list AND the VALUES tuple.
  - `tests/test_audit_remediation_p0.py` L424–434 — same, in the P0.2
    cleanup-ID fixture.
- **`tests/test_subcontractors.py`** — reworked method-by-method:
  - alembic head assertion bumped to `0040_contact_book_rework`.
  - supplier_type enum assertion changed to the 4-value tuple.
  - the `_dropped` test that proved `cis_subtype` was rejected at the
    API has been REPLACED with a schema-level test that proves the
    column is gone (the API can no longer reject `cis_subtype` — the
    Pydantic body silently ignores it).
  - new tests for `Consultant` / `Other` contact types and for the
    `Subcontractor` filter value 422ing.
  - class renames `TestSubcontractor*` → `TestContractor*`.
- **`tests/test_suppliers.py`** — dropped `default_vat_rate` from the
  create body; added assertions on the rev-A serialised shape.
- **`tests/test_trades.py` (new)** — 11 functions covering CRUD,
  whitespace normalisation, case-insensitive idempotent re-create,
  archive/unarchive lifecycle, list filters, permission gating
  (read_only + site_manager view-only; PM can create), and the
  archive-doesn't-clear-supplier-trade_id invariant.
- **`tests/test_supplier_contact_book.py` (new)** — 9 functions
  covering serialised shape, `vat_registered` independence from
  `vat_number`, and the full `_resolve_trade` priority matrix
  (`trade_id` over name; `null` clears; absent key is `_UNSET`;
  swap; bad UUID → 422; name-grow creates the trade).
- **`tests/test_migration_0040_contact_book.py` (new)** — 11
  functions, DB-only VERIFY re-deriving the §R1 acceptance queries
  from Gate 1.
- **Hygiene** — removed the now-ignored `default_vat_rate` from
  payload fixtures in `test_po_approvals_api.py`,
  `test_purchase_orders_api.py`, `test_po_receipts_api.py`.

### §R6 — Seed script

`scripts/seed_contact_book.py` (new, idempotent). Seeds 8 starter trades
+ 4 sample contacts (one of each `supplier_type`). Trade upsert via
`services.trades.get_or_create_trade`; supplier upsert by
`(tenant_id, LOWER(name))`. Safe to re-run.

### Docs

- CHANGELOG entry "Chat 41 — Build Pack 2.7-BE-rev-A" prepended to
  `/app/CHANGELOG.md` (D1–D7 deviation block + §R3/§R4/§R5/§R6 detail).
- This closing summary.
- `memory/PRD.md` updated with Gate 1, Gate 2, Gate 3 entries.

## Pytest results (double-run on pod)

See `memory/Gate3_VERIFY_2.7-BE-rev-A.md` for the full output. Headline:

- Second-run total: see Gate3 verify file.
- Per-file breakdown for the two HARD-BREAK files:
  `test_budget_integrity_committed.py` and `test_audit_remediation_p0.py`
  — both green on second run with `default_vat_rate` removed from both
  the column list AND the VALUES tuple.
- alembic head still `0040_contact_book_rework`; permission count still 131.

## Known-stale FE (next-chat work)

The 2.7-FE pages (shipped Chat 40) still reference the dropped fields:

- `pages/SupplierForm.jsx` writes `cis_subtype` + `default_vat_rate` on
  submit. Backend will return 201; the keys are silently ignored by
  Pydantic (`extra="ignore"` default). UX is degraded (forms show
  values that don't round-trip).
- `pages/SupplierDetail.jsx` reads `cis_subtype` and `default_vat_rate`
  — both will be `undefined`.
- The "Subcontractors" nav link sends `?type=Subcontractor` which now
  422s. The list page needs `Contractor` as the wire value.

A separate 2.7-FE-revision prompt (sketched in the rev-A opener)
covers all of this in one pass.

## Out-of-scope (NOT touched here)

- **rev-B** (SharePoint file storage) — separate prompt.
- **2.7-FE-revision** — separate frontend prompt.
- **`docs/SY_Hub_Phase2_Backlog.md`** — operator-owned.

## Push readiness

- Schema reversible (round-trip `up → down → up` clean; documented
  lossy-cast caveat on the 4→2 enum collapse).
- All §R3.2/§R3.4 greps return zero functional hits.
- Live API smoke is green for the trade CRUD + supplier reshape +
  contractor-gate paths (Gate 2 VERIFY).
- The two hard-break files are patched.
- Permission count target hit exactly (131).
- Pytest double-run completed on the pod.

Ready for push.

---

# Chat 41 — Build Pack 2.7-FE-revision closing summary (appended)

**Pack:** Build Pack 2.7-FE-revision — Suppliers Contact-Book Rework (frontend) + 3 operator-eyeball follow-ons.
**Branch base:** main @ `0040_contact_book_rework`, **131** permissions, 10 roles (the BE-rev-A close above).
**Head after this pack:** **`0041_drop_vat_registered`** (+1 schema migration in this run; the original BE-rev-A close stays at 0040).
**Permissions:** **132** (131 → 132; `+suppliers.delete`).
**Roles:** 10 (unchanged).
**Backlog file (`docs/SY_Hub_Phase2_Backlog.md`):** still NOT touched (operator-owned).
**Auth flows touched:** none.

> The BE-rev-A close above is preserved verbatim. This section is the FE-revision close.

---

## Gate run timeline (FE-revision)

| Step | Scope | Status |
|---|---|---|
| Gate 1 (§R1–§R8) | trades api+hook, `<TradePicker/>`, `<ColumnPicker/>`, Form/Detail/List rework, nav+capability+cisFormat hygiene, tests + VERIFY greps + setupTests shim | ✅ landed; counts below |
| Eyeball follow-on 1 | CIS placement fix — `<select>` moved INSIDE Contractor gate; subtitle on Detail gated; payload omits `cis_status` for non-Contractor | ✅ landed; 4 paired render-presence tests added |
| Eyeball follow-on 2 | Hard-delete + `suppliers.delete` permission; 5-table linked-record gate; toast for 409; FE button on Detail | ✅ landed; 4 backend + 5 frontend tests; perms 131 → 132 |
| Step 2A | `vat_registered` dropped entirely — migration `0041_drop_vat_registered` + backend/frontend purge | ✅ landed; round-trip green; head 0040 → 0041 |
| Step 2B Part 1 | Multi-field search widening (q now matches name + trading_name + contact_name + notes + joined `trades.name`) | ✅ landed; 7 backend tests |
| Step 2B Part 2 | Click-to-sort on `SupplierList.jsx` (asc/desc/clear cycle, arrow + aria-sort) | ✅ landed; 3 frontend tests |
| Step 2B Part 3 | Seed expansion (4 → 11 contacts, idempotent via `_REPAIRABLE_FIELDS` upsert) | ✅ landed; live double-run idempotent |

## What landed (FE-revision sweep)

### Frontend
- New files
  - `lib/api/trades.js`
  - `hooks/trades.js`
  - `components/suppliers/TradePicker.jsx`
  - `components/suppliers/ColumnPicker.jsx`
- Reworked
  - `pages/SupplierForm.jsx` (4-way type, CIS+UTR inside Contractor block, `<TradePicker/>`, address block, sensitive block unchanged)
  - `pages/SupplierDetail.jsx` (subtitle split, address block hide-when-all-null, Contractor-gated CIS/Contracts tabs, Delete button)
  - `pages/SupplierList.jsx` (4-way type filter w/ stale-bookmark fallback, `<ColumnPicker/>`, dynamic colSpan, sortable column heads)
  - `lib/api/suppliers.js` (+ `deleteSupplier`)
  - `hooks/purchaseOrders.js` (+ `useDeleteSupplier`)
  - `lib/poCapability.js` (+ `canViewTrades`, `canCreateTrades`, `canDeleteSupplier`)
  - `lib/cisFormat.js` (− `labelCisSubtype`, − `CIS_SUBTYPE_LABEL`)
  - `components/AppShell.jsx` (− Subcontractors nav, − `HardHat` import)
  - `setupTests.js` (+ `Element.prototype.scrollIntoView` jsdom shim for cmdk)

### Backend (rule lifted, all logged in CHANGELOG)
- `services/suppliers.py`
  - new `delete_supplier(…)` + `SupplierHasLinkedRecords` exception (5 linked tables probed; `_LINKED_RECORD_TABLES` triple-tuple).
  - `list_suppliers.q` widened across name / trading_name / contact_name / notes / `trades.name`. `outerjoin(Trade, …)` added.
  - `vat_registered` removed from `_AUDIT_COLS`, create-path, update-path, serialise.
- `routers/suppliers.py`
  - new `DELETE /api/v1/suppliers/{id}` (204 / 409 / 403 / 404).
  - `vat_registered` removed from both Pydantic bodies.
- `models/suppliers.py` — `vat_registered` mapped_column removed.
- `seed_rbac.py` — `+suppliers.delete` (mirrors `suppliers.archive` distribution).
- `scripts/seed_contact_book.py` — expanded to 11 varied contacts + 8 trades; idempotent via `_REPAIRABLE_FIELDS` upsert.
- Migration `0041_drop_vat_registered` — drops `suppliers.vat_registered`; round-trip green.

### Tests
- New backend files
  - `tests/test_migration_0041_drop_vat_registered.py` (3 tests)
  - `tests/test_supplier_search_widened.py` (7 tests)
- Backend reworked
  - `tests/test_suppliers.py` (Delete suite added, vat_registered drop reflected in shape assertions)
  - `tests/test_supplier_contact_book.py` (vat_registered tests removed; absence asserted)
  - `tests/test_subcontractors.py` (vat_registered removed from expected columns, head sentinel bumped)
  - `tests/test_migration_0040_contact_book.py` (head sentinel + trimmed `trade_id`-only "present" assertion)
  - Head-sentinel bumps in `test_budget_changes_migration.py`, `test_migration_0025_actuals.py`, `test_migration_0028_user_preferences.py`, `test_subcontracts_migration.py`, `test_sc_valuations_migration.py`, `test_bootstrap.py`.
  - Permission-count bumps in `test_permissions_2_7.py`, `test_permissions_2_8a.py`, `test_permissions_2_8b.py`, `test_patch_3.py`, `test_retro_wires.py`, `test_permissions_2_6.py`, `test_auth_rbac.py` (super_admin 131 → 132 + director 127 → 128).
- New frontend files
  - `lib/api/__tests__/trades.test.js` (3 tests)
  - `components/suppliers/__tests__/TradePicker.test.jsx` (7 tests)
  - `components/suppliers/__tests__/ColumnPicker.test.jsx` (4 tests)
- Frontend reworked
  - `pages/__tests__/SupplierForm.test.jsx` (CIS-Contractor-gated render-presence describe block, vat-registered tests replaced with "checkbox is gone + key absent")
  - `pages/__tests__/SupplierDetail.test.jsx` (delete-flow describe block: button gating, cancel, success+toast+navigate, 409+toast+stay; vat-registered row removed; CIS subtitle gating)
  - `pages/__tests__/SupplierList.test.jsx` (click-to-sort describe block; default-VAT column removed)
  - `lib/__tests__/cisFormat.test.js` (`labelCisSubtype` tests removed)

## Counts (final)

### Backend pytest — double-run on pod, fresh DB each run
- **Run 1:** 1292 passed, 3 xpassed, 0 failed, 0 err — 234.83 s
- **Run 2:** 1292 passed, 3 xpassed, 0 failed, 0 err — 232.67 s

### Frontend craco test — single deterministic run
- **78 suites / 570 tests passed.**

### Seed counts (live, fresh DB)
- Run 1: `trades=8 contacts_total=11 contacts_created=11 contacts_repaired=0`
- Run 2: `trades=8 contacts_total=11 contacts_created=0 contacts_repaired=11`
- DB grouping: Contractor 3, Supplier 3 (1 archived), Consultant 2, Other 3 (1 archived).

## Push readiness

- §R9 VERIFY greps all zero-hit (re-verified post-Step-2B).
- Alembic head: `0041_drop_vat_registered`; round-trip up → down → up clean.
- Permission count target hit exactly (132); `bootstrap.verify.perms` green.
- Backend + frontend live smoke green; preview `/api/health` returns 200.
- Backlog file (`docs/SY_Hub_Phase2_Backlog.md`) still NOT touched.
- One observed test-isolation gap (`test_entities_api` mutates `test_projects` fixtures) — flagged as a candidate backlog item; not in scope for this pack.

Ready for push.
