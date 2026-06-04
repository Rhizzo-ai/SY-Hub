"""Chat 41 §R1 (Prompt 2.7-BE-rev-A) — Suppliers Contact-Book Rework.

This migration delivers Build Pack 2.7-BE-rev-A §R1.

Changes (per locked decisions Chat 40–41):
  - permission_resource enum += 'trades' (idempotent ALTER TYPE ADD VALUE).
  - NEW table `trades` (tenant-scoped managed vocabulary): case-insensitive
    unique (tenant_id, lower(name)).
  - `suppliers.trade_id` UUID FK trades.id ON DELETE SET NULL, indexed, nullable.
  - `suppliers.vat_registered` BOOLEAN NOT NULL DEFAULT false (independent of
    `vat_number`).
  - DROP `suppliers.cis_subtype` (per D1, hard drop).
  - DROP `suppliers.default_vat_rate` (per D2, hard drop). The
    column-scoped CHECK constraint `ck_suppliers_vat_rate_range` (added in
    0029) is dropped automatically by Postgres when the column is dropped;
    asserted via VERIFY.
  - Repurpose `supplier_type` enum from ('Supplier','Subcontractor') to
    ('Contractor','Supplier','Consultant','Other'). Recreated (rename →
    create new → drop default → cast via USING CASE → re-set default → drop
    old) because PG cannot rename/remove existing enum values. Data map:
    Subcontractor → Contractor; Supplier → Supplier. New default: 'Supplier'.

Downgrade lossy-cast caveat: on downgrade the 4-value enum collapses back
to ('Supplier','Subcontractor') with Contractor → Subcontractor and
{Supplier, Consultant, Other} → Supplier. Consultant/Other rows lose their
original semantic distinction. Acceptable because downgrade is a dev-only
safety net (rev-A is a one-way operator-agreed reshape).

Downgrade also leaves the `trades` value on the `permission_resource` enum
in place (PG limitation: enum values cannot be removed). Inert without
catalogue rows / role grants — consistent with the 0035 asymmetry.

Revision id:  0040_contact_book_rework
Revises:      0039_committed_single_writer
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0040_contact_book_rework"
down_revision = "0039_committed_single_writer"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, new_value: str) -> None:
    """Idempotent ALTER TYPE ADD VALUE — must run outside transaction.

    Mirrors the 0035 helper verbatim (autocommit_block is required because
    ADD VALUE cannot run inside the migration transaction).
    """
    with op.get_context().autocommit_block():
        op.execute(
            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{new_value}'"
        )


def upgrade() -> None:
    # ─── 1. permission_resource enum += 'trades' (idempotent) ───────────────
    _add_enum_value_if_missing("permission_resource", "trades")

    # ─── 2. trades table (tenant-scoped managed vocabulary) ─────────────────
    op.create_table(
        "trades",
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
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "is_archived", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_trades_tenant_id", "trades", ["tenant_id"],
    )
    # Case-insensitive uniqueness per tenant — mirrors the suppliers index.
    # This is what makes `get_or_create_trade` idempotent: typing an existing
    # name in any case returns the existing row.
    op.create_index(
        "ux_trades_tenant_name_ci",
        "trades",
        ["tenant_id", sa.text("LOWER(name)")],
        unique=True,
    )

    # ─── 3. suppliers: add trade_id + vat_registered ────────────────────────
    op.add_column(
        "suppliers",
        sa.Column(
            "trade_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trades.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_suppliers_trade_id", "suppliers", ["trade_id"],
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "vat_registered", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ─── 4. suppliers: drop cis_subtype + default_vat_rate ──────────────────
    # Postgres drops the column-scoped CHECK constraint
    # `ck_suppliers_vat_rate_range` automatically when `default_vat_rate`
    # is dropped (the constraint references only this column).
    op.drop_column("suppliers", "cis_subtype")
    op.drop_column("suppliers", "default_vat_rate")

    # ─── 5. supplier_type enum recreation (CAREFUL — §R1.3 order critical) ──
    # PG cannot rename/remove enum values; we must recreate.
    # Order: rename old → create new → DROP default (uses old type) →
    # CAST with USING CASE → re-set default → drop old type.
    op.execute("ALTER TYPE supplier_type RENAME TO supplier_type_old")
    op.execute(
        "CREATE TYPE supplier_type AS ENUM "
        "('Contractor', 'Supplier', 'Consultant', 'Other')"
    )
    # MUST drop the default first (it references supplier_type_old).
    op.execute(
        "ALTER TABLE suppliers ALTER COLUMN supplier_type DROP DEFAULT"
    )
    # Data migration: Subcontractor → Contractor; Supplier → Supplier.
    op.execute(
        "ALTER TABLE suppliers "
        "ALTER COLUMN supplier_type TYPE supplier_type "
        "USING (CASE supplier_type::text "
        "         WHEN 'Subcontractor' THEN 'Contractor' "
        "         ELSE 'Supplier' "
        "       END)::supplier_type"
    )
    # Re-set the default on the new type.
    op.execute(
        "ALTER TABLE suppliers "
        "ALTER COLUMN supplier_type SET DEFAULT 'Supplier'::supplier_type"
    )
    # Old type is now unreferenced — drop it.
    op.execute("DROP TYPE supplier_type_old")


def downgrade() -> None:
    # Reverse order of upgrade.
    #
    # LOSSY-CAST CAVEAT: collapsing the 4-value enum back to the 2-value
    # enum maps Contractor → Subcontractor and {Supplier, Consultant, Other}
    # → Supplier. Consultant/Other rows lose their semantic distinction.
    # This is acceptable because downgrade is a dev-only safety net.
    op.execute("ALTER TYPE supplier_type RENAME TO supplier_type_new")
    op.execute(
        "CREATE TYPE supplier_type AS ENUM ('Supplier', 'Subcontractor')"
    )
    op.execute(
        "ALTER TABLE suppliers ALTER COLUMN supplier_type DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE suppliers "
        "ALTER COLUMN supplier_type TYPE supplier_type "
        "USING (CASE supplier_type::text "
        "         WHEN 'Contractor' THEN 'Subcontractor' "
        "         ELSE 'Supplier' "
        "       END)::supplier_type"
    )
    op.execute(
        "ALTER TABLE suppliers "
        "ALTER COLUMN supplier_type SET DEFAULT 'Supplier'::supplier_type"
    )
    op.execute("DROP TYPE supplier_type_new")

    # Re-add suppliers.default_vat_rate (with original default + CHECK).
    op.add_column(
        "suppliers",
        sa.Column(
            "default_vat_rate", sa.Numeric(5, 2), nullable=True,
            server_default=sa.text("20.00"),
        ),
    )
    op.create_check_constraint(
        "ck_suppliers_vat_rate_range",
        "suppliers",
        "default_vat_rate IS NULL OR "
        "(default_vat_rate >= 0 AND default_vat_rate <= 100)",
    )
    # Re-add suppliers.cis_subtype (empty — historical values not restored).
    op.add_column(
        "suppliers",
        sa.Column("cis_subtype", sa.String(30), nullable=True),
    )

    # Drop suppliers.vat_registered.
    op.drop_column("suppliers", "vat_registered")

    # Drop suppliers.trade_id (index + FK).
    op.drop_index("ix_suppliers_trade_id", table_name="suppliers")
    op.drop_column("suppliers", "trade_id")

    # Drop trades table (+ its indexes).
    op.drop_index("ux_trades_tenant_name_ci", table_name="trades")
    op.drop_index("ix_trades_tenant_id", table_name="trades")
    op.drop_table("trades")

    # `trades` permission_resource enum value remains in place — PG cannot
    # remove enum values. Inert without catalogue rows / role grants.
