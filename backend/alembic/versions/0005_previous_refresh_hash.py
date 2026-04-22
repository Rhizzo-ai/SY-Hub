"""0005 previous refresh hash for replay detection

Revision ID: 0005_previous_refresh_hash
Revises: 0004_sessions_and_history
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_previous_refresh_hash"
down_revision = "0004_sessions_and_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_sessions",
        sa.Column("previous_refresh_token_hash", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_user_sessions_prev_refresh_hash",
        "user_sessions",
        ["previous_refresh_token_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_prev_refresh_hash", table_name="user_sessions")
    op.drop_column("user_sessions", "previous_refresh_token_hash")
