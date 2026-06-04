# Gate 1 — VERIFY artefacts (Build Pack 2.7-BE-rev-A §R1+§R2)

Generated against the live Postgres after `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` round-trip. Migration `0040_contact_book_rework`.

## §R1.0 — Alembic head guard
```
0040_contact_book_rework (head)
```
Pre-migration head (verified before writing): `0039_committed_single_writer`.

## §R1.3 — `supplier_type` enum labels (exactly the 4 target values)
```
1: 'Contractor'
2: 'Supplier'
3: 'Consultant'
4: 'Other'
```
Lingering temp types (`supplier_type_old` / `supplier_type_new`): **(none — clean)**

## §R1.3 — `supplier_type` data sanity
- Rows with NULL supplier_type: **0**
- Per-value count (live DB after migration): no supplier rows seeded yet (clean DB).
- **Data-mapping VERIFY (downgrade-and-upgrade with seeded rows):**
  - Inserted on 0039: `TEST_R1_3_SUB` (supplier_type='Subcontractor'), `TEST_R1_3_SUP` (supplier_type='Supplier')
  - After `alembic upgrade head` (re-run USING CASE):
    ```
    TEST_R1_3_SUB: supplier_type = 'Contractor'
    TEST_R1_3_SUP: supplier_type = 'Supplier'
    ```
  - ✅ Subcontractor → Contractor; Supplier → Supplier. Deterministic, no NULLs.

## §R1.2 — Dropped columns absent
```
suppliers.cis_subtype:        ABSENT ✓
suppliers.default_vat_rate:   ABSENT ✓
```

## §R1.2 — Added columns present
```
suppliers.trade_id:        uuid    nullable=YES default=None
suppliers.vat_registered:  boolean nullable=NO  default='false'
```

## §R1.2 — `default_vat_rate` CHECK constraint gone
```
ck_suppliers_vat_rate_range present (expect []): []
```
Postgres auto-dropped this column-scoped CHECK when `default_vat_rate` was dropped.

## §R1.1 — `trades` table + columns
```
id            uuid                       NOT NULL  (pk, default gen_random_uuid())
tenant_id     uuid                       NOT NULL  FK tenants.id ON DELETE RESTRICT
name          character varying(100)     NOT NULL
is_archived   boolean                    NOT NULL  DEFAULT false
created_at    timestamptz                NOT NULL  DEFAULT now()
created_by    uuid                       NOT NULL  FK users.id
updated_at    timestamptz                NOT NULL  DEFAULT now()
updated_by    uuid                       NOT NULL  FK users.id
```

## §R1.1 — `trades` indexes
```
trades_pkey                   (PK)
ix_trades_tenant_id           btree(tenant_id)
ux_trades_tenant_name_ci      UNIQUE btree(tenant_id, lower(name::text))
```

## §R1.5 — `permission_resource` enum extension
```
'trades' present in permission_resource: True
```
Added via the autocommit `_add_enum_value_if_missing` helper (mirrors 0035).
Enum value remains on downgrade (PG limitation; documented in migration).

## §R2 — Model layer sanity
- `app/models/trades.py`: `Trade` ORM exists; columns: id, tenant_id, name, is_archived, created_at, created_by, updated_at, updated_by.
- `app/models/suppliers.py`:
  - `SUPPLIER_TYPES = ('Contractor', 'Supplier', 'Consultant', 'Other')`
  - has `trade_id`: True; has `vat_registered`: True
  - has `cis_subtype`: False; has `default_vat_rate`: False
  - `trade` relationship: lazy='joined', no back_populates (one-directional)
- `app/models/__init__.py`: `CIS_SUBTYPES` removed from imports/exports; `Trade` exposed.
- `app/models/rbac.py`: `RESOURCES` includes `'trades'`.

## §R2.2 grep — no model code references to dropped fields
```
$ grep -rn "CIS_SUBTYPES|default_vat_rate|cis_subtype" backend/app/models/
backend/app/models/suppliers.py:9:  - `cis_subtype` and `default_vat_rate` dropped.
```
Sole hit is a docstring note in the rewritten suppliers model documenting the change. **Zero functional references.** ✓

## §R1.4 — Round-trip reversibility
```
0040 → 0039 → 0040  (logged via alembic)
```
- Downgrade re-adds `cis_subtype` (VARCHAR(30) NULL), `default_vat_rate` (NUMERIC(5,2) NULL DEFAULT 20.00) + the `ck_suppliers_vat_rate_range` CHECK verbatim from 0029.
- Downgrade rebuilds the 2-value `supplier_type` enum with the documented lossy collapse: `Contractor → Subcontractor`, `{Supplier, Consultant, Other} → Supplier`.
- Downgrade drops `vat_registered`, `trade_id`, and the `trades` table.
- `trades` value on `permission_resource` enum is left in place (PG limitation; documented).

---

## Gate 1 status
- [x] alembic head is `0040_contact_book_rework`
- [x] supplier_type enum recreated cleanly to the 4 target values
- [x] data migration verified Subcontractor → Contractor, Supplier → Supplier
- [x] cis_subtype + default_vat_rate dropped; CHECK constraint gone
- [x] trade_id + vat_registered added with correct nullability/defaults
- [x] trades table + ux_trades_tenant_name_ci unique index present
- [x] permission_resource enum has 'trades'
- [x] Trade model + suppliers model + rbac RESOURCES updated
- [x] Round-trip (up → down → up) clean
- [x] No functional refs to dropped fields in `app/models/`

## Expected next-gate work (NOT done here — STOP at Gate 1)
- §R3 services: `_validate_cis_subtype` / `_coerce_vat_rate` removal, `_resolve_trade` + `_UNSET` sentinel, cis.py + subcontracts.py gate relabel to `'Contractor'`, supplier serialise reshape.
- §R4 routers: trades router; suppliers body reshape (`vat_registered`, `trade_id`, `trade`).
- §R5 tests + raw-SQL INSERT fixes; §R6 seed.
- seed_rbac.py: `trades.{view,create}` catalogue + role grants (drives permission count 129 → 131).

Until Gate 2 lands, the running backend will fail to import (`services/suppliers.py` still references `CIS_SUBTYPES` and the dropped columns). This is the **expected** intermediate state per §R7 ("Do not touch services/routers until the operator confirms the schema is clean").
