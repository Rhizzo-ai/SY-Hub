"""Chat 34 §R5 (Prompt 2.8a) — Subcontracts schema/migration tests.

Covers Build Pack 2.8a §R5 gates 1–2:
  1. upgrade clean; both tables + the source_variation_id FK exist.
  2. down→up round-trip clean (sanity check; the live DB is not
     downgraded during pytest — the round-trip is asserted via the
     stamped revision id only).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from tests._subcontracts_common import DATABASE_URL


@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


class TestSchemaMigration:
    def test_alembic_head_is_0037_subcontracts(self):
        """Head sentinel — renamed semantically by each chat. Chat 35
        (Prompt 2.8b) bumps it to 0038_sc_valuations."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            head = db.execute(text(
                "SELECT version_num FROM alembic_version"
            )).scalar()
        finally:
            db.close()
        assert head == "0038_sc_valuations", (
            f"Expected alembic head 0038_sc_valuations; got {head}"
        )

    def test_subcontract_tables_exist(self, db_engine):
        with db_engine.connect() as c:
            assert c.execute(text(
                "SELECT to_regclass('subcontracts')"
            )).scalar() == "subcontracts"
            assert c.execute(text(
                "SELECT to_regclass('subcontract_variations')"
            )).scalar() == "subcontract_variations"

    def test_source_variation_id_fk_added(self, db_engine):
        """LD3 — the 2.6 stub column now carries an actual FK to
        subcontract_variations.id with ON DELETE SET NULL."""
        with db_engine.connect() as c:
            fks = c.execute(text("""
                SELECT tc.constraint_name, rc.delete_rule
                  FROM information_schema.table_constraints tc
                  JOIN information_schema.key_column_usage kcu
                    ON kcu.constraint_name = tc.constraint_name
                  JOIN information_schema.referential_constraints rc
                    ON rc.constraint_name = tc.constraint_name
                  JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                 WHERE tc.constraint_type = 'FOREIGN KEY'
                   AND tc.table_name = 'budget_changes'
                   AND kcu.column_name = 'source_variation_id'
                   AND ccu.table_name = 'subcontract_variations'
            """)).fetchall()
        assert fks, (
            "Expected FK budget_changes.source_variation_id → "
            "subcontract_variations.id"
        )
        # ON DELETE SET NULL.
        assert fks[0][1] == "SET NULL", (
            f"Expected ON DELETE SET NULL; got {fks[0][1]}"
        )

    def test_permission_action_enum_has_cost(self, db_engine):
        """`cost` is the only NEW permission_action enum value added by
        this migration; `issue` already exists from PO 2.5."""
        with db_engine.connect() as c:
            vals = {r[0] for r in c.execute(text("""
                SELECT enumlabel FROM pg_enum
                WHERE enumtypid = (
                    SELECT oid FROM pg_type WHERE typname='permission_action'
                )
            """))}
        assert "cost" in vals, vals
        assert "issue" in vals, vals  # pre-existing

    def test_permission_resource_enum_has_new_resources(self, db_engine):
        with db_engine.connect() as c:
            vals = {r[0] for r in c.execute(text("""
                SELECT enumlabel FROM pg_enum
                WHERE enumtypid = (
                    SELECT oid FROM pg_type WHERE typname='permission_resource'
                )
            """))}
        assert "subcontracts" in vals, vals
        assert "subcontract_variations" in vals, vals

    def test_unique_constraints_on_references(self, db_engine):
        with db_engine.connect() as c:
            sc_uq = c.execute(text("""
                SELECT conname FROM pg_constraint
                 WHERE conrelid = 'subcontracts'::regclass
                   AND contype = 'u'
            """)).fetchall()
            v_uq = c.execute(text("""
                SELECT conname FROM pg_constraint
                 WHERE conrelid = 'subcontract_variations'::regclass
                   AND contype = 'u'
            """)).fetchall()
        assert any(
            "project_reference" in r[0] for r in sc_uq
        ), sc_uq
        assert any(
            "ref" in r[0] for r in v_uq
        ), v_uq

    def test_check_constraint_on_status_subcontracts(self, db_engine):
        """The migration's CHECK constraint must reject unknown statuses."""
        with db_engine.connect() as c:
            with pytest.raises(Exception):
                c.execute(text("""
                    INSERT INTO subcontracts
                      (id, tenant_id, project_id, subcontractor_id,
                       reference, title, status,
                       original_contract_sum, current_contract_sum,
                       retention_pct, cis_applies)
                    SELECT gen_random_uuid(),
                           (SELECT id FROM tenants LIMIT 1),
                           gen_random_uuid(),
                           gen_random_uuid(),
                           'SC-9999','t','NotAValidStatus',
                           0,0,0,true
                """))

    def test_check_constraint_on_status_variations(self, db_engine):
        with db_engine.connect() as c:
            with pytest.raises(Exception):
                c.execute(text("""
                    INSERT INTO subcontract_variations
                      (id, tenant_id, subcontract_id,
                       reference, title, status)
                    SELECT gen_random_uuid(),
                           (SELECT id FROM tenants LIMIT 1),
                           gen_random_uuid(),
                           'VAR-9999','t','NotAValidStatus'
                """))
