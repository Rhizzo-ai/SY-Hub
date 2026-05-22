"""Chat 26 §R7.0b (Prompt 2.5 Track 2) — audit_action enum extension.

Adds the `SendBack` value to the `audit_action` PostgreSQL enum so the
`POST /purchase-orders/{po_id}/send-back` service (po_approvals.send_back_po)
can persist its audit row.

Scope is deliberately one statement: `ALTER TYPE audit_action ADD VALUE IF
NOT EXISTS 'SendBack'`. No other DDL, no permission/role row touched.

Rationale (P0.13 resolution): the build pack §R7.0b requires
`action="SendBack"` in record_audit and T5 asserts `action == "SendBack"`.
Every prior new audit verb in this repo (Reject/Unlock/Issue/Receipt/
Archive/Restore/Seed_Run) was added via the same idempotent
`_add_enum_value_if_missing` pattern, four migrations running (0029 →
0031 → 0032 → 0033). This migration extends that line by exactly one
verb. `po_approval_resolution` enum and all `purchase_orders` columns
are UNCHANGED.

Revision id:  0034_audit_sendback
Revises:      0033_po_receipts
"""
from __future__ import annotations

from alembic import op


revision = "0034_audit_sendback"
down_revision = "0033_po_receipts"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, new_value: str) -> None:
    """Add a value to a PostgreSQL ENUM, idempotently, outside the
    migration's transaction (ALTER TYPE ADD VALUE cannot run inside one)."""
    with op.get_context().autocommit_block():
        op.execute(
            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{new_value}'"
        )


def upgrade() -> None:
    _add_enum_value_if_missing("audit_action", "SendBack")


def downgrade() -> None:
    # PostgreSQL doesn't support removing an enum value without rewriting
    # the type. Consistent with 0031/0032/0033 (Issue/Reject/Unlock/
    # Receipt all left in audit_action on downgrade).
    pass
