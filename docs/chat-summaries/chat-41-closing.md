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
