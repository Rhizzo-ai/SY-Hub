"""Chat 41 §R-eyeball-Step2A (Prompt 2.7-FE-revision) — drop suppliers.vat_registered.

Operator decision post-Gate-1 eyeball: the standalone `vat_registered`
flag is dropped. "Has a VAT number" is the de-facto registered signal,
invoice rate carries on each PO line, and Xero owns VAT logic. Same
hard-drop approach used for `default_vat_rate` + `cis_subtype` in 0040.

upgrade: drop suppliers.vat_registered (no data preserved — operator
agreed).
downgrade: re-add the column as BOOLEAN NOT NULL DEFAULT false, so the
0040 → 0041 round-trip is symmetrical for dev safety. (Production never
downgrades; this exists only for `alembic downgrade -1` round-trips.)

Revision id:  0041_drop_vat_registered
Revises:      0040_contact_book_rework
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0041_drop_vat_registered"
down_revision = "0040_contact_book_rework"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("suppliers", "vat_registered")


def downgrade() -> None:
    op.add_column(
        "suppliers",
        sa.Column(
            "vat_registered",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Drop the server default after backfill so the column matches the
    # 0040 schema exactly (NOT NULL, no lingering default) — mirrors the
    # 0040 pattern verbatim.
    op.alter_column("suppliers", "vat_registered", server_default=None)
