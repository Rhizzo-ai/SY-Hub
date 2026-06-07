"""Chat 33 §R5 (Prompt 2.6) — Budget Change schema/migration tests.

Covers Build Pack 2.6 gates 1–3 (schema + migration round-trip
preconditions). See `tests/_bcr_common.py` for shared helpers and
`tests/test_budget_changes_service.py`, `tests/test_budget_changes_api.py`,
`tests/test_permissions_2_6.py` for the other thirds of the suite.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from tests._bcr_common import DATABASE_URL


@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


class TestSchemaMigration:
    def test_alembic_head_is_0036_budget_changes(self):
        """Head sentinel — name retained for git-diff hygiene; the
        actual expected value moves with each new migration. Chat 34
        (Prompt 2.8a) bumps it to 0037_subcontracts; Chat 35 (Prompt
        2.8b) bumps it to 0039_committed_single_writer; Chat 41
        (Prompt 2.7-BE-rev-A) bumps it to 0040_contact_book_rework.
        Chat 41 §R-eyeball-Step2A (Prompt 2.7-FE-revision) bumps it to
        0041_drop_vat_registered."""
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            head = db.execute(text(
                "SELECT version_num FROM alembic_version"
            )).scalar()
        finally:
            db.close()
        assert head == "0043_document_folders", (
            f"Expected alembic head 0041_drop_vat_registered; got {head}"
        )

    def test_budget_changes_tables_exist(self, db_engine):
        with db_engine.connect() as c:
            assert c.execute(text(
                "SELECT to_regclass('budget_changes')"
            )).scalar() == "budget_changes"
            assert c.execute(text(
                "SELECT to_regclass('budget_change_lines')"
            )).scalar() == "budget_change_lines"

    def test_budget_lines_has_is_contingency(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text("""
                SELECT data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name='budget_lines'
                  AND column_name='is_contingency'
            """)).first()
        assert row is not None, "budget_lines.is_contingency must exist"
        assert row[0] == "boolean"
        assert row[1] == "NO"  # NOT NULL
        # Existing rows backfilled false.
        with db_engine.connect() as c:
            non_false = c.execute(text(
                "SELECT COUNT(*) FROM budget_lines WHERE is_contingency IS NOT FALSE"
            )).scalar()
        assert non_false == 0, (
            "All existing budget_lines must backfill is_contingency=false"
        )
