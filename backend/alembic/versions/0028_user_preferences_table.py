"""0028 — Create user_preferences table.

Revision ID: 0028_user_preferences_table
Revises: 0027_default_line_items_backfill

Chat 23 Build Pack A R1.4: per-user JSON storage for UI surface state.
Used by:
  - BudgetGrid v2 column layout, sort, filters, visibility toggles
  - BudgetGrid v2 saved views (one record per saved view)
  - Future surfaces (any tabular UI with state)

Surface keys are open-ended strings; the application layer decides what
they mean. No enum constraint — adding a new surface is a code-only
change. Initial usage: `budgets.grid.v2`.

Design notes:
  - `name IS NULL`     => the "current" record (autosaved on change).
                         Exactly one per (user_id, surface_key).
  - `name IS NOT NULL` => a named saved view. Multiple per (user_id,
                         surface_key).
  - Partial unique indexes (Postgres feature) enforce these semantics in
    the DB layer so the service can rely on them.
  - JSONB (not JSON) for efficient indexing + partial updates. Full-
    replace is the API contract though; no JSON Patch.
  - No tenant_id column — preferences are user-scoped only. The user_id
    FK to users.id (CASCADE on user delete) is the scope.

No audit trigger on this table — high-volume autosaves would dominate
audit_log. Named-view CUD is audited via the route layer; autosave PUT
is deliberately NOT audited.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0028_user_preferences_table"
down_revision = "0027_default_line_items_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("surface_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"), nullable=False,
        ),
    )
    # One "current" record per (user, surface). Saved views have non-NULL
    # names and are constrained on the triple.
    op.create_index(
        "ix_user_preferences_user_surface_current",
        "user_preferences", ["user_id", "surface_key"],
        unique=True, postgresql_where=sa.text("name IS NULL"),
    )
    op.create_index(
        "ix_user_preferences_user_surface_named",
        "user_preferences", ["user_id", "surface_key", "name"],
        unique=True, postgresql_where=sa.text("name IS NOT NULL"),
    )
    op.create_index(
        "ix_user_preferences_user", "user_preferences", ["user_id"],
    )

    # Auto-bump updated_at via the shared trigger function set up in
    # app/db.py::ensure_updated_at_trigger. We mirror it inline here so
    # the schema is self-contained (Pattern α — migrations don't import
    # app code).
    op.execute("""
        DROP TRIGGER IF EXISTS trg_user_preferences_updated_at
        ON user_preferences;
        CREATE TRIGGER trg_user_preferences_updated_at
        BEFORE UPDATE ON user_preferences
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_user_preferences_updated_at "
        "ON user_preferences;"
    )
    op.drop_index(
        "ix_user_preferences_user", table_name="user_preferences",
    )
    op.drop_index(
        "ix_user_preferences_user_surface_named",
        table_name="user_preferences",
    )
    op.drop_index(
        "ix_user_preferences_user_surface_current",
        table_name="user_preferences",
    )
    op.drop_table("user_preferences")
