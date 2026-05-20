"""Chat 24 §R4 (Prompt 2.5) — Purchase Order Receipts.

Adds three child tables of purchase_order_lines + a recompute trigger
that keeps purchase_order_lines.receipted_quantity in sync with the
SUM of quantity_received across all receipt lines for that PO line.
The GENERATED column is_fully_receipted (added in 0030) reads from
receipted_quantity, so this trigger is the canonical write path.

Money invariant
---------------
Receipts do NOT change purchase_order_lines.committed_value or any
budget_line commitment. Money moves to actuals via Bills in a later
chat. The trigger in 0032 (status -> commitments) is left untouched.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0033_po_receipts"
down_revision = "0032_po_approvals"
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
    # ─── 1. Enum extensions ──────────────────────────────────────────────────
    _add_enum_value_if_missing("audit_action", "Receipt")
    _add_enum_value_if_missing("notification_type", "po.partial_receipt")
    _add_enum_value_if_missing("notification_type", "po.fully_receipted")

    # ─── 1b. Backfill: read_only.suppliers.view ─────────────────────────────
    # 0029 granted suppliers.* to admin/director/finance/PM/site_manager but
    # NOT to read_only — that grant lived in seed_rbac.py only, so any
    # downgrade past 0029 then upgrade lost it. Make the migration chain
    # self-sufficient: backfill the read_only grant here (idempotent).
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p ON p.code = 'suppliers.view'
         WHERE r.code = 'read_only'
        ON CONFLICT DO NOTHING;
    """)

    # ─── 2. purchase_order_receipts (header) ────────────────────────────────
    op.create_table(
        "purchase_order_receipts",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "purchase_order_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("received_date", sa.Date, nullable=False),
        sa.Column(
            "received_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("delivery_note_reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_por_purchase_order_id", "purchase_order_receipts",
        ["purchase_order_id"],
    )
    op.create_index(
        "ix_por_tenant_id", "purchase_order_receipts", ["tenant_id"],
    )
    op.execute(
        "CREATE TRIGGER trg_purchase_order_receipts_updated_at "
        "BEFORE UPDATE ON purchase_order_receipts "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    # ─── 3. purchase_order_receipt_lines ────────────────────────────────────
    op.create_table(
        "purchase_order_receipt_lines",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "receipt_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_order_receipts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "po_line_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity_received", sa.Numeric(14, 4), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "quantity_received > 0",
            name="ck_porl_quantity_positive",
        ),
    )
    op.create_index(
        "ix_porl_receipt_id", "purchase_order_receipt_lines", ["receipt_id"],
    )
    op.create_index(
        "ix_porl_po_line_id", "purchase_order_receipt_lines", ["po_line_id"],
    )

    # ─── 4. purchase_order_receipt_photos ───────────────────────────────────
    # Receipt proof file references. No global `documents` table exists in
    # the repo (the build pack's `document_id` concept maps to direct
    # file metadata here, mirroring actual_attachments).
    op.create_table(
        "purchase_order_receipt_photos",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "receipt_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_order_receipts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("caption", sa.String(500), nullable=True),
        sa.Column(
            "uploaded_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "file_size_bytes > 0",
            name="ck_porp_size_positive",
        ),
        sa.UniqueConstraint(
            "receipt_id", "file_path", name="ux_porp_receipt_file_path",
        ),
    )
    op.create_index(
        "ix_porp_receipt_id", "purchase_order_receipt_photos", ["receipt_id"],
    )

    # ─── 5. Recompute trigger ───────────────────────────────────────────────
    # Keep purchase_order_lines.receipted_quantity in sync with
    # SUM(quantity_received) over receipt lines for that po_line.
    # The GENERATED column is_fully_receipted reads from receipted_quantity
    # and resolves automatically on the same row update.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_pol_recompute_receipted_qty(
            p_po_line_id uuid
        ) RETURNS void AS $$
        BEGIN
            UPDATE purchase_order_lines pol
            SET receipted_quantity = COALESCE((
                SELECT SUM(rl.quantity_received)
                FROM purchase_order_receipt_lines rl
                WHERE rl.po_line_id = p_po_line_id
            ), 0)
            WHERE pol.id = p_po_line_id;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_porl_recompute_trg()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                PERFORM fn_pol_recompute_receipted_qty(OLD.po_line_id);
                RETURN OLD;
            ELSIF TG_OP = 'UPDATE' AND OLD.po_line_id <> NEW.po_line_id THEN
                -- Re-target: recompute both old and new line.
                PERFORM fn_pol_recompute_receipted_qty(OLD.po_line_id);
                PERFORM fn_pol_recompute_receipted_qty(NEW.po_line_id);
                RETURN NEW;
            ELSE
                PERFORM fn_pol_recompute_receipted_qty(NEW.po_line_id);
                RETURN NEW;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_pol_receipted_qty
        AFTER INSERT OR UPDATE OR DELETE ON purchase_order_receipt_lines
        FOR EACH ROW EXECUTE FUNCTION fn_porl_recompute_trg();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_pol_receipted_qty ON purchase_order_receipt_lines;")
    op.execute("DROP FUNCTION IF EXISTS fn_porl_recompute_trg();")
    op.execute("DROP FUNCTION IF EXISTS fn_pol_recompute_receipted_qty(uuid);")
    op.drop_index("ix_porp_receipt_id", table_name="purchase_order_receipt_photos")
    op.drop_table("purchase_order_receipt_photos")
    op.drop_index("ix_porl_po_line_id", table_name="purchase_order_receipt_lines")
    op.drop_index("ix_porl_receipt_id", table_name="purchase_order_receipt_lines")
    op.drop_table("purchase_order_receipt_lines")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_purchase_order_receipts_updated_at "
        "ON purchase_order_receipts;"
    )
    op.drop_index("ix_por_tenant_id", table_name="purchase_order_receipts")
    op.drop_index("ix_por_purchase_order_id", table_name="purchase_order_receipts")
    op.drop_table("purchase_order_receipts")
    # ALTER TYPE DROP VALUE is unsupported by Postgres; 'Receipt' enum
    # value is left in audit_action (consistent with 0031/0032 pattern).
