"""Chat 24 §R2 (Prompt 2.5) — Purchase Orders core.

Schema for the PO entity itself plus PO lines. Approval workflow and
commitment-recompute triggers come in 0031 (R3); receipts in 0032 (R4);
permission seed in 0033 (R2 finish).

Adds:
  - po_status ENUM (8 states per §2.4 status machine)
  - purchase_orders table
  - purchase_order_lines table
  - fn_po_recompute_header_totals + trigger trg_po_recompute_header

Revision id:  0030_purchase_orders
Revises:      0029_suppliers_prefixes
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0030_purchase_orders"
down_revision = "0029_suppliers_prefixes"
branch_labels = None
depends_on = None


PO_STATUSES = (
    "draft",
    "pending_approval",
    "approved",
    "issued",
    "partially_receipted",
    "receipted",
    "closed",
    "voided",
)


def upgrade() -> None:
    # ─── 1. po_status enum ──────────────────────────────────────────────────
    po_status = postgresql.ENUM(
        *PO_STATUSES, name="po_status", create_type=True,
    )
    po_status.create(op.get_bind(), checkfirst=True)

    # ─── 2. purchase_orders ─────────────────────────────────────────────────
    op.create_table(
        "purchase_orders",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("po_number", sa.String(50), nullable=False),
        sa.Column(
            "po_number_prefix_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("project_number_prefixes.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("po_sequence", sa.Integer, nullable=True),
        sa.Column(
            "supplier_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "budget_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(*PO_STATUSES, name="po_status", create_type=False),
            nullable=False, server_default=sa.text("'draft'::po_status"),
        ),
        sa.Column("issue_date", sa.Date, nullable=True),
        sa.Column("required_by_date", sa.Date, nullable=True),
        sa.Column("delivery_address", sa.Text, nullable=True),
        sa.Column("delivery_notes", sa.Text, nullable=True),
        sa.Column(
            "subtotal_amount", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "vat_amount", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_amount", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "currency", sa.String(3), nullable=False,
            server_default=sa.text("'GBP'"),
        ),
        # lifecycle stamps
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "submitted_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=True,
        ),
        sa.Column(
            "approval_required", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("approval_reason", sa.Text, nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "issued_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=True,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "closed_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=True,
        ),
        sa.Column("closed_reason", sa.Text, nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "voided_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=True,
        ),
        sa.Column("voided_reason", sa.Text, nullable=True),
        sa.Column("external_reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.CheckConstraint("currency = 'GBP'", name="ck_po_currency_gbp"),
        sa.UniqueConstraint("tenant_id", "po_number", name="ux_po_tenant_number"),
    )
    # Partial unique index — only enforced when po_number_prefix_id is set.
    op.execute(
        "CREATE UNIQUE INDEX ux_po_auto_seq "
        "ON purchase_orders (project_id, po_number_prefix_id, po_sequence) "
        "WHERE po_number_prefix_id IS NOT NULL "
        "AND po_sequence IS NOT NULL"
    )
    op.create_index("ix_po_project_status", "purchase_orders", ["project_id", "status"])
    op.create_index("ix_po_supplier", "purchase_orders", ["supplier_id"])
    op.create_index("ix_po_budget", "purchase_orders", ["budget_id"])
    op.execute(
        "CREATE INDEX ix_po_status_active ON purchase_orders(status) "
        "WHERE status NOT IN ('closed','voided')"
    )

    # ─── 3. purchase_order_lines ────────────────────────────────────────────
    op.create_table(
        "purchase_order_lines",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "purchase_order_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "budget_line_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_lines.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("cost_code", sa.String(20), nullable=False),
        sa.Column("line_number", sa.Integer, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "quantity", sa.Numeric(14, 4), nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("unit_rate", sa.Numeric(14, 4), nullable=False),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "vat_rate", sa.Numeric(5, 2), nullable=False,
            server_default=sa.text("20.00"),
        ),
        sa.Column(
            "vat_amount", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "receipted_quantity", sa.Numeric(14, 4), nullable=False,
            server_default=sa.text("0"),
        ),
        # Generated column — Postgres maintains this automatically.
        sa.Column(
            "is_fully_receipted", sa.Boolean,
            sa.Computed("(receipted_quantity >= quantity)", persisted=True),
            nullable=False,
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="ck_pol_quantity_positive"),
        sa.CheckConstraint("unit_rate >= 0", name="ck_pol_unit_rate_nonneg"),
        sa.CheckConstraint(
            "vat_rate >= 0 AND vat_rate <= 100",
            name="ck_pol_vat_rate_range",
        ),
        sa.CheckConstraint(
            "receipted_quantity >= 0",
            name="ck_pol_receipted_nonneg",
        ),
        sa.CheckConstraint(
            "receipted_quantity <= quantity",
            name="ck_pol_receipted_not_exceeded",
        ),
    )
    op.create_index("ix_pol_po", "purchase_order_lines", ["purchase_order_id"])
    op.create_index("ix_pol_budget_line", "purchase_order_lines", ["budget_line_id"])
    op.create_index(
        "ix_pol_po_linenum", "purchase_order_lines",
        ["purchase_order_id", "line_number"],
    )

    # ─── 4. Header recompute trigger ────────────────────────────────────────
    # Maintains purchase_orders.{subtotal,vat,total}_amount from line sums.
    # Idempotent on no-op updates because the inner SUM is deterministic.
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_po_recompute_header_totals()
        RETURNS TRIGGER AS $$
        DECLARE
            v_po_id uuid;
        BEGIN
            v_po_id := COALESCE(NEW.purchase_order_id, OLD.purchase_order_id);
            UPDATE purchase_orders
               SET subtotal_amount = COALESCE((
                       SELECT SUM(net_amount) FROM purchase_order_lines
                        WHERE purchase_order_id = v_po_id
                   ), 0),
                   vat_amount = COALESCE((
                       SELECT SUM(vat_amount) FROM purchase_order_lines
                        WHERE purchase_order_id = v_po_id
                   ), 0),
                   total_amount = COALESCE((
                       SELECT SUM(gross_amount) FROM purchase_order_lines
                        WHERE purchase_order_id = v_po_id
                   ), 0),
                   updated_at = now()
             WHERE id = v_po_id;
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_po_recompute_header
        AFTER INSERT OR UPDATE OR DELETE ON purchase_order_lines
        FOR EACH ROW EXECUTE FUNCTION fn_po_recompute_header_totals();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_po_recompute_header ON purchase_order_lines")
    op.execute("DROP FUNCTION IF EXISTS fn_po_recompute_header_totals()")

    op.drop_index("ix_pol_po_linenum", table_name="purchase_order_lines")
    op.drop_index("ix_pol_budget_line", table_name="purchase_order_lines")
    op.drop_index("ix_pol_po", table_name="purchase_order_lines")
    op.drop_table("purchase_order_lines")

    op.execute("DROP INDEX IF EXISTS ix_po_status_active")
    op.drop_index("ix_po_budget", table_name="purchase_orders")
    op.drop_index("ix_po_supplier", table_name="purchase_orders")
    op.drop_index("ix_po_project_status", table_name="purchase_orders")
    op.execute("DROP INDEX IF EXISTS ux_po_auto_seq")
    op.drop_table("purchase_orders")

    po_status = postgresql.ENUM(*PO_STATUSES, name="po_status")
    po_status.drop(op.get_bind(), checkfirst=True)
