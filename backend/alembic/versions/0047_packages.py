"""0047 — B88 Pack 3: Packages (the tendering spine).

Revision ID: 0047_packages
Revises: 0046_rbac_operator_overrides

Creates six new tables (packages + 5 children) and four PG ENUM types
backing the package state machines. Adds 'award' to permission_action.

Up:
  - ALTER TYPE permission_action ADD VALUE 'award' (in autocommit_block).
  - CREATE TYPE package_kind / package_status / package_bid_status /
    package_award_status.
  - CREATE TABLE packages, package_lines, package_bids, package_bid_lines,
    package_awards, package_award_lines (with named CHECK constraints +
    UNIQUEs + indexes).

Down:
  - DROP TABLE (children first, then packages).
  - DROP TYPE (4 enums).
  - permission_action ENUM value 'award' is intentionally left in place
    (Postgres can't drop enum values; matches precedent 0020).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0047_packages"
down_revision = "0046_rbac_operator_overrides"
branch_labels = None
depends_on = None


PACKAGE_KIND_VALUES = ("labour", "materials")
PACKAGE_STATUS_VALUES = (
    "draft", "out_to_tender", "partially_awarded", "awarded", "cancelled",
)
PACKAGE_BID_STATUS_VALUES = (
    "invited", "received", "declined", "withdrawn",
)
PACKAGE_AWARD_STATUS_VALUES = ("active", "cancelled")


def upgrade() -> None:
    # ── 1. Extend permission_action enum with 'award' and
    # permission_resource with 'packages' (idempotent, must be outside
    # a transaction). Mirrors precedents 0020 + 0026.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE permission_action "
            "ADD VALUE IF NOT EXISTS 'award'"
        )
        op.execute(
            "ALTER TYPE permission_resource "
            "ADD VALUE IF NOT EXISTS 'packages'"
        )

    # ── 2. Create new ENUM types.
    package_kind = postgresql.ENUM(
        *PACKAGE_KIND_VALUES, name="package_kind", create_type=False,
    )
    package_status = postgresql.ENUM(
        *PACKAGE_STATUS_VALUES, name="package_status", create_type=False,
    )
    package_bid_status = postgresql.ENUM(
        *PACKAGE_BID_STATUS_VALUES, name="package_bid_status",
        create_type=False,
    )
    package_award_status = postgresql.ENUM(
        *PACKAGE_AWARD_STATUS_VALUES, name="package_award_status",
        create_type=False,
    )
    package_kind.create(op.get_bind(), checkfirst=True)
    package_status.create(op.get_bind(), checkfirst=True)
    package_bid_status.create(op.get_bind(), checkfirst=True)
    package_award_status.create(op.get_bind(), checkfirst=True)

    # ── 3. packages
    op.create_table(
        "packages",
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
            "project_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "budget_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("kind", package_kind, nullable=False),
        sa.Column(
            "status", package_status,
            nullable=False, server_default=sa.text("'draft'::package_status"),
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "total_net", sa.Numeric(14, 2),
            nullable=False, server_default=sa.text("0"),
        ),
        sa.Column(
            "awarded_net", sa.Numeric(14, 2),
            nullable=False, server_default=sa.text("0"),
        ),
        sa.Column("out_to_tender_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "out_to_tender_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "awarded_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancelled_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column("cancelled_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id", "reference", name="uq_packages_project_reference",
        ),
        sa.CheckConstraint(
            "kind IN ('labour','materials')", name="ck_packages_kind_values",
        ),
        sa.CheckConstraint(
            "status IN ('draft','out_to_tender','partially_awarded',"
            "'awarded','cancelled')",
            name="ck_packages_status_values",
        ),
    )
    op.create_index("ix_packages_tenant_id", "packages", ["tenant_id"])
    op.create_index(
        "ix_packages_project_status", "packages", ["project_id", "status"],
    )

    # ── 4. package_lines
    op.create_table(
        "package_lines",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "package_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("packages.id", ondelete="CASCADE"),
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
            "quantity", sa.Numeric(14, 4),
            nullable=False, server_default=sa.text("1"),
        ),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("budgeted_unit_rate", sa.Numeric(14, 4), nullable=False),
        sa.Column("budgeted_net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "package_id", "budget_line_id",
            name="uq_package_lines_package_budget_line",
        ),
        sa.UniqueConstraint(
            "package_id", "line_number",
            name="uq_package_lines_package_line_number",
        ),
        sa.CheckConstraint(
            "quantity > 0", name="ck_package_lines_quantity_positive",
        ),
        sa.CheckConstraint(
            "budgeted_unit_rate >= 0",
            name="ck_package_lines_rate_non_negative",
        ),
    )
    op.create_index(
        "ix_package_lines_package_id", "package_lines", ["package_id"],
    )
    op.create_index(
        "ix_package_lines_budget_line_id", "package_lines", ["budget_line_id"],
    )

    # ── 5. package_bids
    op.create_table(
        "package_bids",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "package_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "supplier_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status", package_bid_status,
            nullable=False,
            server_default=sa.text("'invited'::package_bid_status"),
        ),
        sa.Column(
            "total_net", sa.Numeric(14, 2),
            nullable=False, server_default=sa.text("0"),
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "package_id", "supplier_id",
            name="uq_package_bids_package_supplier",
        ),
        sa.CheckConstraint(
            "status IN ('invited','received','declined','withdrawn')",
            name="ck_package_bids_status_values",
        ),
    )
    op.create_index(
        "ix_package_bids_package_id", "package_bids", ["package_id"],
    )
    op.create_index(
        "ix_package_bids_supplier_id", "package_bids", ["supplier_id"],
    )

    # ── 6. package_bid_lines
    op.create_table(
        "package_bid_lines",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "package_bid_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("package_bids.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "package_line_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("package_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quoted_unit_rate", sa.Numeric(14, 4), nullable=False),
        sa.Column("quoted_net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "package_bid_id", "package_line_id",
            name="uq_package_bid_lines_bid_line",
        ),
        sa.CheckConstraint(
            "quoted_unit_rate >= 0",
            name="ck_package_bid_lines_rate_non_negative",
        ),
        sa.CheckConstraint(
            "quoted_net_amount >= 0",
            name="ck_package_bid_lines_net_non_negative",
        ),
    )
    op.create_index(
        "ix_package_bid_lines_bid_id",
        "package_bid_lines", ["package_bid_id"],
    )

    # ── 7. package_awards
    op.create_table(
        "package_awards",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "package_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "supplier_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_bid_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("package_bids.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status", package_award_status,
            nullable=False,
            server_default=sa.text("'active'::package_award_status"),
        ),
        sa.Column("awarded_net", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_purchase_order_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_subcontract_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subcontracts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancelled_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column("cancelled_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Exactly one downstream when active. The service creates the
        # downstream PO/SC FIRST, then INSERTs the award row with the
        # downstream id already populated — so this CHECK is satisfied at
        # row-insert time (Postgres does not allow DEFERRABLE on CHECK
        # constraints).
        sa.CheckConstraint(
            "(status <> 'active') OR ("
            " (created_purchase_order_id IS NOT NULL"
            "  AND created_subcontract_id IS NULL)"
            " OR ("
            "  created_purchase_order_id IS NULL"
            "  AND created_subcontract_id IS NOT NULL)"
            ")",
            name="ck_package_awards_one_downstream",
        ),
        sa.CheckConstraint(
            "awarded_net >= 0",
            name="ck_package_awards_net_non_negative",
        ),
    )
    op.create_index(
        "ix_package_awards_package_id", "package_awards", ["package_id"],
    )

    # ── 8. package_award_lines
    op.create_table(
        "package_award_lines",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "package_award_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("package_awards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "package_line_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("package_lines.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(14, 4), nullable=False),
        sa.Column("awarded_unit_rate", sa.Numeric(14, 4), nullable=False),
        sa.Column("awarded_net", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "package_award_id", "package_line_id",
            name="uq_package_award_lines_award_line",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_package_award_lines_quantity_positive",
        ),
        sa.CheckConstraint(
            "awarded_unit_rate >= 0",
            name="ck_package_award_lines_rate_non_negative",
        ),
        sa.CheckConstraint(
            "awarded_net >= 0",
            name="ck_package_award_lines_net_non_negative",
        ),
    )
    op.create_index(
        "ix_package_award_lines_award_id",
        "package_award_lines", ["package_award_id"],
    )
    op.create_index(
        "ix_package_award_lines_package_line_id",
        "package_award_lines", ["package_line_id"],
    )


def downgrade() -> None:
    # Drop children → parents to satisfy FKs.
    op.drop_index(
        "ix_package_award_lines_package_line_id",
        table_name="package_award_lines",
    )
    op.drop_index(
        "ix_package_award_lines_award_id",
        table_name="package_award_lines",
    )
    op.drop_table("package_award_lines")

    op.drop_index("ix_package_awards_package_id", table_name="package_awards")
    op.drop_table("package_awards")

    op.drop_index("ix_package_bid_lines_bid_id", table_name="package_bid_lines")
    op.drop_table("package_bid_lines")

    op.drop_index("ix_package_bids_supplier_id", table_name="package_bids")
    op.drop_index("ix_package_bids_package_id", table_name="package_bids")
    op.drop_table("package_bids")

    op.drop_index(
        "ix_package_lines_budget_line_id", table_name="package_lines",
    )
    op.drop_index("ix_package_lines_package_id", table_name="package_lines")
    op.drop_table("package_lines")

    op.drop_index("ix_packages_project_status", table_name="packages")
    op.drop_index("ix_packages_tenant_id", table_name="packages")
    op.drop_table("packages")

    bind = op.get_bind()
    postgresql.ENUM(name="package_award_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="package_bid_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="package_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="package_kind").drop(bind, checkfirst=True)
    # NOTE: 'award' is left in permission_action — Postgres cannot drop
    # enum values; matches precedent 0020_permission_action_submit.
