"""0020 — Enum fidelity fix for Prompt 2.2 permission + audit codes.

Revision ID: 0020_permission_action_submit
Revises: 0019_appraisals_core

Adds three enum values so the `permissions.action` and `audit_log.action`
columns can carry codes that are 1:1 with what the application actually
means, rather than reusing neighbouring labels:

- `permission_action` += 'submit'          (for `appraisals.submit`)
- `permission_action` += 'view_financials' (for `appraisals.view_financials`)
- `audit_action`      += 'Submit'          (for /submit endpoint events)

Postgres ENUMs require ALTER TYPE ... ADD VALUE to run outside a
transaction, so we use the alembic `autocommit_block` pattern set up
in migration 0017.

Also backfills existing permission rows inserted by 0019 under the old
action codes so the data-on-disk matches the new 1:1 convention:
- appraisals.submit:          action 'approve'         → 'submit'
- appraisals.view_financials: action 'view_sensitive'  → 'view_financials'

Downgrade is a no-op for the ENUM values (Postgres doesn't support
ALTER TYPE ... DROP VALUE). The permission-row data revert is
implemented for tidiness.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_permission_action_submit"
down_revision = "0019_appraisals_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE permission_action ADD VALUE IF NOT EXISTS 'submit'"
        )
        op.execute(
            "ALTER TYPE permission_action "
            "ADD VALUE IF NOT EXISTS 'view_financials'"
        )
        op.execute(
            "ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'Submit'"
        )

    # Backfill permission rows to use the newly-added action codes.
    # The rows were inserted by 0019 under the old shortcut action names.
    op.execute(
        "UPDATE permissions SET action = 'submit' "
        "WHERE code = 'appraisals.submit'"
    )
    op.execute(
        "UPDATE permissions SET action = 'view_financials' "
        "WHERE code = 'appraisals.view_financials'"
    )


def downgrade() -> None:
    # ENUM values can't be dropped in Postgres — leave them in place.
    # Revert the row-level action codes so the enum-value abandon is
    # purely an information cost.
    op.execute(
        "UPDATE permissions SET action = 'approve' "
        "WHERE code = 'appraisals.submit'"
    )
    op.execute(
        "UPDATE permissions SET action = 'view_sensitive' "
        "WHERE code = 'appraisals.view_financials'"
    )
