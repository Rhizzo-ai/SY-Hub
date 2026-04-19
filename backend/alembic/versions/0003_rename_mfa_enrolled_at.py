"""0003 — rename users.mfa_enforced_at → mfa_enrolled_at.

Prompt 1.2 addendum: per user feedback the column represents the moment
the user completed enrolment, not policy enforcement, so the name is
changed to reflect that.
"""
from __future__ import annotations

from alembic import op


revision = "0003_rename_mfa_enrolled_at"
down_revision = "0002_users_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "mfa_enforced_at", new_column_name="mfa_enrolled_at")


def downgrade() -> None:
    op.alter_column("users", "mfa_enrolled_at", new_column_name="mfa_enforced_at")
