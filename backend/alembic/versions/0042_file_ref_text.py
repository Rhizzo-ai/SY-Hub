"""Chat 41 §R5.0 (Build Pack 2.7-BE-rev-B) — widen supplier_documents.file_ref to Text.

rev-B replaces the free-text `file_ref` placeholder with a serialised
`StoredObjectRef` JSON pointer (item_id, drive_id, web_url, name, size,
content_type). Microsoft Graph web URLs and the JSON envelope routinely
exceed the previous `String(500)` cap, so widen to `Text`.

upgrade: alter `supplier_documents.file_ref` String(500) -> Text.
downgrade: alter back to String(500). Operator note — only safe if all
live values are <= 500 chars; in production downgrade would truncate
Graph refs and is therefore advisory only (mirrors the dev-safety
contract for 0040 / 0041).

Revision id:  0042_file_ref_text
Revises:      0041_drop_vat_registered
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0042_file_ref_text"
down_revision = "0041_drop_vat_registered"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "supplier_documents",
        "file_ref",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="file_ref::text",
    )


def downgrade() -> None:
    op.alter_column(
        "supplier_documents",
        "file_ref",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=True,
        postgresql_using="file_ref::varchar(500)",
    )
