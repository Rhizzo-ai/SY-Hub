"""Chat 41 §R5 (Prompt 2.7-BE-rev-A) — migration 0040 schema VERIFY tests.

DB-only assertions (no API). Runs against the live Postgres at
`alembic upgrade head`. These tests re-derive the assertions from the
§R1.2 / §R1.3 / §R1.5 VERIFY queries shipped in Gate 1.

Scope:
  - alembic head is the latest. Today: 0041_drop_vat_registered.
  - supplier_type enum has exactly the 4 target values (no temp types
    lingering).
  - suppliers: cis_subtype + default_vat_rate columns DROPPED; trade_id
    ADDED with the expected nullability/defaults. (vat_registered was
    ADDED here in 0040 then DROPPED in 0041 — see
    test_migration_0041_drop_vat_registered.)
  - default_vat_rate CHECK constraint (`ck_suppliers_vat_rate_range`)
    auto-dropped with the column.
  - trades table exists with the unique CI index on (tenant_id, lower(name)).
  - permission_resource enum has 'trades'.
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


# ---------------------------------------------------------------------------
# §R1.0
# ---------------------------------------------------------------------------

def test_alembic_head_is_latest_post_0040(engine):
    # The latest head was bumped to 0041 by Chat 41 §R-eyeball-Step2A
    # (dropping vat_registered). Function name retains "is_0040" per the
    # project's literal-drift convention.
    with engine.connect() as c:
        head = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert head == "0045_construction_scope", head


# ---------------------------------------------------------------------------
# §R1.3 — supplier_type enum
# ---------------------------------------------------------------------------

class TestSupplierTypeEnum:
    def test_enum_has_exactly_four_values_in_order(self, engine):
        with engine.connect() as c:
            labels = [
                r[0] for r in c.execute(text(
                    "SELECT enumlabel FROM pg_enum "
                    "WHERE enumtypid='supplier_type'::regtype "
                    "ORDER BY enumsortorder"
                )).all()
            ]
        assert labels == ["Contractor", "Supplier", "Consultant", "Other"], labels

    def test_no_lingering_temp_types(self, engine):
        """`supplier_type_old` and `supplier_type_new` must be cleaned up
        by the migration (no temp types left behind after recreation).
        """
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT typname FROM pg_type
                 WHERE typname IN ('supplier_type_old', 'supplier_type_new')
            """)).all()
        assert rows == [], f"unexpected lingering temp types: {rows}"

    def test_default_value_is_supplier(self, engine):
        """The `suppliers.supplier_type` column default must be 'Supplier'
        (re-set on the new type during recreation).
        """
        with engine.connect() as c:
            default = c.execute(text("""
                SELECT column_default
                  FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='suppliers'
                   AND column_name='supplier_type'
            """)).scalar()
        assert default is not None and "Supplier" in default, default


# ---------------------------------------------------------------------------
# §R1.2 — suppliers columns
# ---------------------------------------------------------------------------

class TestSuppliersColumns:
    def test_dropped_columns_absent(self, engine):
        with engine.connect() as c:
            cols = {r[0] for r in c.execute(text("""
                SELECT column_name FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='suppliers'
                   AND column_name IN ('cis_subtype', 'default_vat_rate')
            """)).all()}
        assert cols == set(), f"expected dropped columns absent, found {cols}"

    def test_new_columns_present_with_expected_metadata(self, engine):
        # Chat 41 §R-eyeball-Step2A: vat_registered was ADDED here in
        # 0040 but DROPPED again in 0041. At head, only trade_id
        # survives — verify its metadata. The drop is verified
        # separately in test_migration_0041_drop_vat_registered.
        with engine.connect() as c:
            rows = list(c.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='suppliers'
                   AND column_name = 'trade_id'
            """)).mappings())
        by_name = {r["column_name"]: r for r in rows}
        assert set(by_name) == {"trade_id"}, by_name

        trade = by_name["trade_id"]
        assert trade["data_type"] == "uuid"
        assert trade["is_nullable"] == "YES"

    def test_default_vat_rate_check_constraint_dropped(self, engine):
        """`ck_suppliers_vat_rate_range` (from 0029) must be gone — PG
        auto-drops a single-column CHECK when the column is dropped.
        """
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT conname FROM pg_constraint
                 WHERE conrelid='suppliers'::regclass
                   AND contype='c'
                   AND conname='ck_suppliers_vat_rate_range'
            """)).all()
        assert rows == [], (
            f"expected ck_suppliers_vat_rate_range to be dropped, found {rows}"
        )


# ---------------------------------------------------------------------------
# §R1.1 — trades table
# ---------------------------------------------------------------------------

class TestTradesTable:
    def test_trades_table_exists_with_expected_columns(self, engine):
        with engine.connect() as c:
            cols = {
                r[0]: (r[1], r[2])
                for r in c.execute(text("""
                    SELECT column_name, data_type, is_nullable
                      FROM information_schema.columns
                     WHERE table_schema='public' AND table_name='trades'
                """)).all()
            }
        required = {
            "id", "tenant_id", "name", "is_archived",
            "created_at", "created_by", "updated_at", "updated_by",
        }
        assert required.issubset(cols.keys()), (
            f"missing columns on trades: {required - set(cols)}"
        )

    def test_trades_unique_ci_index_present(self, engine):
        """Chat 41 §R1.1 — `ux_trades_tenant_name_ci` enforces
        (tenant_id, LOWER(name)) uniqueness.
        """
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT indexname, indexdef FROM pg_indexes
                 WHERE schemaname='public' AND tablename='trades'
                   AND indexname='ux_trades_tenant_name_ci'
            """)).mappings().all()
        assert rows, "ux_trades_tenant_name_ci index not present"
        defn = rows[0]["indexdef"].lower()
        assert "unique" in defn
        assert "lower" in defn
        assert "tenant_id" in defn

    def test_trades_tenant_index_present(self, engine):
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT indexname FROM pg_indexes
                 WHERE schemaname='public' AND tablename='trades'
                   AND indexname='ix_trades_tenant_id'
            """)).all()
        assert rows, "ix_trades_tenant_id index not present"


# ---------------------------------------------------------------------------
# §R1.5 — permission_resource enum
# ---------------------------------------------------------------------------

def test_permission_resource_enum_has_trades(engine):
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT 1 FROM pg_enum e
              JOIN pg_type t ON t.oid = e.enumtypid
             WHERE t.typname='permission_resource' AND e.enumlabel='trades'
        """)).all()
    assert rows, "'trades' value missing from permission_resource enum"


# ---------------------------------------------------------------------------
# §R1.2 — suppliers.trade_id FK behaviour
# ---------------------------------------------------------------------------

def test_supplier_trade_id_foreign_key_set_null_on_delete(engine):
    """`suppliers.trade_id` FK must be `ON DELETE SET NULL`. (We don't
    actually hard-delete in the app — this proves the migration set the
    constraint correctly so a manual cleanup would preserve suppliers.)
    """
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT confdeltype
              FROM pg_constraint con
              JOIN pg_class rel ON rel.oid = con.conrelid
              JOIN pg_attribute att ON att.attrelid = con.conrelid
               AND att.attnum = ANY(con.conkey)
             WHERE rel.relname='suppliers'
               AND att.attname='trade_id'
               AND con.contype='f'
        """)).all()
    # PG codes: 'n' = SET NULL, 'a' = NO ACTION, 'r' = RESTRICT,
    # 'c' = CASCADE, 'd' = SET DEFAULT.
    assert rows and rows[0][0] == "n", (
        f"expected suppliers.trade_id FK on delete=SET NULL ('n'), got {rows}"
    )
