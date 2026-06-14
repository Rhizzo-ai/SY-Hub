"""0048 — B88 Pack 3.5: 3-value package kind + package↔order links.

Revision ID: 0048_package_kind_3value_links
Revises: 0047_packages

DEVIATION FROM BUILD PACK: revision id shortened from the Build Pack's
stated `0048_package_kind_3value_and_links` (34 chars) to
`0048_package_kind_3value_links` (29 chars) because
`alembic_version.version_num` is `varchar(32)`. Same semantics, same
target migration; only the identifier is trimmed.

Up:
  1. ALTER TYPE package_kind ADD VALUE 'subcontract' (autocommit_block).
     ALTER TYPE package_kind ADD VALUE 'consultant'  (autocommit_block).
  2. UPDATE packages SET kind='subcontract' WHERE kind='labour'
     — runs in the migration's own (post-autocommit) transaction; the
     newly added enum value is only usable in a transaction that did NOT
     also add it. `labour` is left as an orphaned enum member (precedent
     0020/0047 — Postgres cannot drop enum values inside a transaction
     and we deliberately do not attempt to). The CHECK constraint below
     enforces the live allowed set.
  3. DROP + recreate the named CHECK ck_packages_kind_values to the new
     3-value live set: ('materials','subcontract','consultant').
  4. ADD nullable `package_id` UUID column (FK → packages.id ON DELETE
     SET NULL, plus index) to purchase_orders and subcontracts. The
     SET NULL rule guarantees that deleting a package never cascades
     into the destruction of a real financial order — the link nulls;
     the order survives.

Down (best-effort; demo-data-only forward migration):
  - DROP the two FKs, indexes, and `package_id` columns.
  - DROP + recreate ck_packages_kind_values back to ('labour','materials').
  - Reverse the data migration: UPDATE packages SET kind='labour' WHERE
    kind='subcontract'. Genuine `consultant` rows have no pre-image —
    in a non-live env the operator MUST delete any `consultant` rows
    BEFORE downgrading or the restored CHECK will reject them. This is
    acceptable given the locked "demo-data-only on live" decision.
  - Enum values 'subcontract' and 'consultant' are NOT dropped (Postgres
    can't drop enum values; matches precedent 0020 / 0047).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0048_package_kind_3value_links"
down_revision = "0047_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Extend the PG enum additively. MUST be in autocommit_block
    # because Postgres does not permit `ALTER TYPE ... ADD VALUE` inside
    # a regular transaction. Mirrors precedents 0020 / 0047.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE package_kind "
            "ADD VALUE IF NOT EXISTS 'subcontract'"
        )
        op.execute(
            "ALTER TYPE package_kind "
            "ADD VALUE IF NOT EXISTS 'consultant'"
        )

    # ── 2. Drop the old 2-value CHECK so the impending UPDATE to
    # `kind='subcontract'` is not blocked by the live constraint.
    # NOTE — order deviation from Build Pack §1.1 (which lists
    # UPDATE before DROP+RECREATE): live CHECK is
    # `kind IN ('labour','materials')` at this point, so any UPDATE
    # to 'subcontract' would raise ck_packages_kind_values violation.
    # The audit (Pass 1 C1) only addressed transaction-boundary
    # ordering for ALTER TYPE / UPDATE, not CHECK-vs-UPDATE ordering.
    # Drop-first / UPDATE / recreate-with-new-values is the only
    # correct sequence.
    op.drop_constraint(
        "ck_packages_kind_values", "packages", type_="check",
    )

    # ── 3. Data-migrate existing rows. Runs in the migration's own
    # (post-autocommit) transaction, where the new enum values are
    # already committed and usable. On live the only `labour` packages
    # are demo data — light gate, no production-backup ceremony.
    op.execute(
        "UPDATE packages SET kind = 'subcontract' WHERE kind = 'labour'"
    )

    # ── 4. Install the new 3-value CHECK. `labour` is deliberately
    # absent; no live row carries it after step 3, and no new row may
    # be created with it going forward.
    op.create_check_constraint(
        "ck_packages_kind_values",
        "packages",
        "kind IN ('materials','subcontract','consultant')",
    )

    # ── 5. package_id on purchase_orders.
    op.add_column(
        "purchase_orders",
        sa.Column(
            "package_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_purchase_orders_package_id",
        "purchase_orders",
        "packages",
        ["package_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_purchase_orders_package_id",
        "purchase_orders",
        ["package_id"],
    )

    # ── 5. package_id on subcontracts.
    op.add_column(
        "subcontracts",
        sa.Column(
            "package_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_subcontracts_package_id",
        "subcontracts",
        "packages",
        ["package_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_subcontracts_package_id",
        "subcontracts",
        ["package_id"],
    )


def downgrade() -> None:
    # ── 5'. Drop subcontracts.package_id artifacts.
    op.drop_index(
        "ix_subcontracts_package_id", table_name="subcontracts",
    )
    op.drop_constraint(
        "fk_subcontracts_package_id", "subcontracts", type_="foreignkey",
    )
    op.drop_column("subcontracts", "package_id")

    # ── 4'. Drop purchase_orders.package_id artifacts.
    op.drop_index(
        "ix_purchase_orders_package_id", table_name="purchase_orders",
    )
    op.drop_constraint(
        "fk_purchase_orders_package_id",
        "purchase_orders",
        type_="foreignkey",
    )
    op.drop_column("purchase_orders", "package_id")

    # ── 3'. Drop the 3-value CHECK so we can move rows back.
    # Operator MUST have cleared any genuine `consultant` rows before
    # invoking this downgrade in a non-live env; the recreated 2-value
    # CHECK has no representation for them. Acceptable for a
    # demo-data-only forward migration.
    op.drop_constraint(
        "ck_packages_kind_values", "packages", type_="check",
    )

    # ── 2'. Reverse the data migration. Runs while no CHECK is in
    # force on `kind`, so the move from 'subcontract' back to 'labour'
    # is unconstrained.
    op.execute(
        "UPDATE packages SET kind = 'labour' WHERE kind = 'subcontract'"
    )

    # ── 1'. Restore the original 2-value CHECK.
    op.create_check_constraint(
        "ck_packages_kind_values",
        "packages",
        "kind IN ('labour','materials')",
    )

    # NOTE: 'subcontract' and 'consultant' remain in the PG enum
    # `package_kind` — Postgres cannot drop enum values; matches
    # precedent 0020 / 0047.
