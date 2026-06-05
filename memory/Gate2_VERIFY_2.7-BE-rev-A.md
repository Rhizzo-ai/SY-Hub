# Gate 2 — VERIFY artefacts (Build Pack 2.7-BE-rev-A §R3 + §R4 + seed_rbac)

Generated against the live backend after services / routers / seed_rbac edits,
backend hot-reloaded, bootstrap re-run.

## Alembic + permission count
```
alembic head: 0040_contact_book_rework (unchanged from Gate 1)
permissions:  131  (was 129; +trades.view +trades.create)
roles:        10   (unchanged)
```
Bootstrap log (excerpt):
```
verify.alembic    result=ok current=0040_contact_book_rework
verify.perms      result=ok expected=131 actual=131
verify.roles      result=ok expected=10  actual=10
```

## §R3.2 VERIFY — dropped identifiers absent from `services/suppliers.py`
```
$ grep -n "default_vat_rate\|cis_subtype\|_coerce_vat_rate\|_validate_cis_subtype\|CIS_SUBTYPES" \
    backend/app/services/suppliers.py
6:  - `cis_subtype` + `default_vat_rate` validators / writes removed.
56:    # Chat 41 §R3.2 (Prompt 2.7-BE-rev-A) — `cis_subtype` + `default_vat_rate`
115:# Chat 41 §R3.2 — `cis_subtype` validator removed; `supplier_type` enum
```
All 3 hits are **docstring/comment notes documenting the removal**. Zero functional references. ✓

## §R3.4 VERIFY — behavioural `"Subcontractor"` literals (comparison usage) gone from `services/`
```
$ grep -rn 'supplier_type.*[!=]=.*"Subcontractor"\|"Subcontractor".*[!=]=.*supplier_type' \
    backend/app/services/
(zero hits)
```
Wider `"Subcontractor"` grep in `app/services/`:
```
app/services/retention_releases.py:200:    supplier_name = supplier.name if supplier else "Subcontractor"
app/services/subcontract_valuations.py:618:        supplier_for_actual.name if supplier_for_actual else "Subcontractor"
app/services/budget_lines.py:52:    "Subcontractor",
```
All non-behavioural (display fallback strings + a budget-line-item label). §R3.4 explicitly scopes to comparison usage. ✓

## §R3.3 + §R3.4 — both gates now key off `"Contractor"`
```
app/services/cis.py:179:           if supplier.supplier_type != "Contractor":
app/services/subcontracts.py:290:  if supplier.supplier_type != "Contractor":
```

## End-to-end behavioural smoke (live API, `test-pm@example.test`)
```
login:                                  200
list trades (initially empty):          200 total=0
create trade Groundworks:               201
idempotent CI re-create ("groundworks"): 201 same_id=True
create supplier (Contractor + "Electrical"): 201
  supplier_type='Contractor', trade='Electrical', vat_registered=True,
  current_cis_status='Unverified'
  'cis_subtype' in body: False, 'default_vat_rate' in body: False
patch (trade_id→Groundworks):           200 trade='Groundworks'
patch (clear trade with null):          200 trade_id=None
patch (no trade key — _UNSET path):     200 trade_id still None
create plain Supplier:                  201
  CIS verify on Supplier:               409 detail='CIS verification only
                                            valid for contractors (CIS
                                            subcontractors)'
list ?supplier_type=Contractor:         200 total=1
list ?supplier_type=Subcontractor:      422  ('Subcontractor' no longer a
                                              valid value — relabel confirmed)
```
This exercises §R3.1 (trades CRUD), §R3.2 (`_resolve_trade` + `_UNSET` sentinel
+ serialise reshape + `vat_registered`), §R3.3 (CIS gate relabel + new message
mapped through the 409 router branch), §R4.1 (trades router mounted + perms
enforced), §R4.2 (supplier body reshape).

## §R4.1 — trades router permission grants
```
trades.create  → super_admin, director, finance, project_manager
trades.view    → super_admin, director, finance, project_manager,
                 site_manager, read_only
```
Mirrors `suppliers.create` / `suppliers.view` distribution exactly (D7).

## Files changed (Gate 2)
- new   `app/services/trades.py` (list, get, get_or_create with SAVEPOINT,
        set_archived, serialise)
- new   `app/routers/trades.py`   (GET / POST / POST /{id}/archive / POST /{id}/unarchive)
- edit  `app/services/suppliers.py` — _resolve_trade + _UNSET, removed
        _validate_cis_subtype + _coerce_vat_rate, audit_cols updated,
        serialise reshape (vat_registered, trade, trade_id; cis_subtype
        + default_vat_rate keys gone), current_cis_status default keyed
        off "Contractor"
- edit  `app/services/cis.py`     — gate literal relabel + new error message
- edit  `app/services/subcontracts.py` — LD2 gate literal relabel +
        "Subcontractor not found" → "Contractor not found"
- edit  `app/routers/suppliers.py` — body reshape: dropped cis_subtype +
        default_vat_rate; added vat_registered, trade, trade_id; filter
        description updated to 4-value contact-type label
- edit  `app/routers/cis.py`      — 409 detector string updated to match
        new "only valid for contractors" message
- edit  `server.py`               — mount trades_router after suppliers_router
- edit  `app/seed_rbac.py`        — trades catalogue (view, create) + role
        grants for super_admin/director/finance/project_manager (create) +
        site_manager/read_only (view)

## Gate 2 status
- [x] alembic head unchanged at `0040_contact_book_rework`
- [x] permission count 129 → **131** (verify.perms expected=131 actual=131)
- [x] §R3.2 grep zero functional hits in `services/suppliers.py`
- [x] §R3.4 grep zero behavioural `"Subcontractor"` comparison literals in `services/`
- [x] Both CIS / subcontracts gates now compare to `"Contractor"`
- [x] CIS verify on a Supplier returns 409 with the **new** error message
- [x] `_UNSET` sentinel correctly distinguishes "key absent" from "explicit null"
- [x] Grow-as-you-type trades: case-insensitive idempotent re-create returns same id
- [x] supplier serialise omits `cis_subtype` and `default_vat_rate`; includes
      `vat_registered`, `trade`, `trade_id` (joined `trade` is null-safe)
- [x] trades router mounted in v1; perms enforced

## Expected next-gate (Gate 3) work — NOT done here
- §R5 test rework:
  - `test_subcontractors.py` method-by-method (several assertions invert).
  - `test_suppliers.py` — drop legacy `default_vat_rate` from create bodies; assert serialised shape.
  - New `test_trades.py`, `test_supplier_contact_book.py`, `test_migration_0040_contact_book.py`.
  - **HARD-BREAK fix** in `test_budget_integrity_committed.py` + `test_audit_remediation_p0.py` — both raw-SQL INSERTs reference the dropped `default_vat_rate` column. These WILL break the moment those suites run and must be patched (column list + VALUES tuple).
- §R6 idempotent `scripts/seed_contact_book.py`.
- CHANGELOG deviation block + `docs/chat-summaries/chat-41-closing.md`.
- backlog `docs/SY_Hub_Phase2_Backlog.md` — **untouched** (operator-owned).
