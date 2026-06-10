"""Chat 41 §R-eyeball-Step2A (Prompt 2.7-FE-revision) — migration 0041
schema VERIFY tests.

DB-only assertions (no API). Mirrors test_migration_0040_contact_book.py.

Scope:
  - alembic head is 0041_drop_vat_registered.
  - suppliers.vat_registered column ABSENT at head (dropped by 0041).
  - All other rev-A columns (trade_id, supplier_type, cis_registered,
    utr, current_cis_status) still present.

The 0040 + 0041 round-trip (upgrade → downgrade → upgrade) is exercised
manually in the dev runbook (see CHANGELOG); the assertion here pins the
final-head state which is what production will see.
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
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


def test_alembic_head_is_0041(engine):
    with engine.connect() as c:
        head = c.execute(text(
            "SELECT version_num FROM alembic_version"
        )).scalar()
    assert head == "0044_cost_code_groups", head


def test_vat_registered_column_absent_at_head(engine):
    """The column added in 0040 must be gone at head — operator
    decision (Step 2A). "Has a VAT number" is the de-facto registered
    signal; Xero owns VAT logic.
    """
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = 'suppliers'
               AND column_name = 'vat_registered'
        """)).all()
    assert rows == [], (
        f"suppliers.vat_registered must be absent at head "
        f"(dropped by 0041); found rows={rows!r}"
    )


def test_surviving_rev_a_columns_still_present(engine):
    """0041 drops only vat_registered. The other rev-A additions
    (trade_id + the Contractor fields) must remain so the contact-book
    surface is intact.
    """
    needed = {
        "trade_id", "supplier_type",
        "cis_registered", "utr", "current_cis_status",
    }
    with engine.connect() as c:
        cols = {r[0] for r in c.execute(text("""
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'suppliers'
        """)).all()}
    missing = needed - cols
    assert not missing, f"missing rev-A columns at head: {sorted(missing)}"
