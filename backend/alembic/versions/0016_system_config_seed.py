"""0016 system_config — placeholder (Prompt 1.7).

Revision ID: 0016_system_config_seed
Revises: 0015_system_config_notifications

The 38-key seed lives in `app/seed_system_config.py` because it depends
on `roles.id` from RBAC seeding. Alembic runs BEFORE seed_rbac at
lifespan time, so a pure-SQL data migration would fail FK resolution
on first boot. This migration is intentionally a no-op so the version
chain stays linear.
"""
from alembic import op  # noqa: F401  (kept for parity with sibling migrations)


revision = "0016_system_config_seed"
down_revision = "0015_system_config_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
