"""Chat 23 Build Pack A — R1.4 migration 0028 user_preferences smoke tests.

Verifies the migration applied cleanly and the table has the partial
unique indexes that enforce the (user, surface)-uniqueness semantics:
  - At most ONE row with name IS NULL per (user_id, surface_key)
  - At most ONE row with a given name per (user_id, surface_key)
"""
from __future__ import annotations

import os
import uuid

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


class TestMigration0028Schema:
    def test_alembic_head_is_0028(self, engine):
        with engine.connect() as c:
            head = c.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        # Live head bumped again by Chat 24 R1/R2/R3/R4 (Prompt 2.5).
        # Function name retained per Future_Tasks polish entry.
        assert head == "0034_audit_sendback", (
            f"expected 0034_audit_sendback, got {head!r}"
        )

    def test_table_and_partial_unique_indexes_present(self, engine):
        with engine.connect() as c:
            cols = c.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name='user_preferences'
                ORDER BY ordinal_position
            """)).scalars().all()
        assert cols == [
            "id", "user_id", "surface_key", "name",
            "payload", "created_at", "updated_at",
        ]

        # Both partial unique indexes exist.
        with engine.connect() as c:
            indexes = c.execute(text("""
                SELECT indexname, indexdef FROM pg_indexes
                WHERE tablename='user_preferences'
                ORDER BY indexname
            """)).all()
        names = {r.indexname for r in indexes}
        assert "ix_user_preferences_user_surface_current" in names
        assert "ix_user_preferences_user_surface_named" in names
        for r in indexes:
            if r.indexname == "ix_user_preferences_user_surface_current":
                assert "WHERE (name IS NULL)" in r.indexdef
                assert "UNIQUE" in r.indexdef.upper()
            if r.indexname == "ix_user_preferences_user_surface_named":
                assert "WHERE (name IS NOT NULL)" in r.indexdef
                assert "UNIQUE" in r.indexdef.upper()

    def test_partial_index_enforces_one_current_per_surface(self, engine):
        """Inserting two NULL-name rows for the same (user, surface) must
        raise IntegrityError via the partial unique index."""
        with engine.begin() as c:
            tenant_id = c.execute(
                text("SELECT id FROM tenants LIMIT 1")
            ).scalar()
            uid = uuid.uuid4()
            c.execute(text("""
                INSERT INTO users (
                    id, tenant_id, email, first_name, last_name,
                    password_hash, user_type, status
                ) VALUES (
                    :id, :t, :email, 'Mig', 'Tmp',
                    'x', 'Internal', 'Active'
                )
            """), {
                "id": uid, "t": tenant_id,
                "email": f"mig28-{uid}@example.test",
            })
            c.execute(text("""
                INSERT INTO user_preferences (user_id, surface_key, payload)
                VALUES (:u, 'mig.test', '{}'::jsonb)
            """), {"u": uid})

        # Second insert with same (user, surface) and name IS NULL → conflict.
        with pytest.raises(IntegrityError):
            with engine.begin() as c:
                c.execute(text("""
                    INSERT INTO user_preferences
                        (user_id, surface_key, payload)
                    VALUES (:u, 'mig.test', '{}'::jsonb)
                """), {"u": uid})

        # Cleanup.
        with engine.begin() as c:
            c.execute(text("DELETE FROM user_preferences WHERE user_id=:u"),
                      {"u": uid})
            c.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
