"""0049 — B102: Unbudgeted-Order Handling (flag-not-block).

Revision ID: 0049_unbudgeted_order_lines
Revises: 0048_package_kind_3value_links

Adds the schema scaffolding for B102. A purchase-order line or package
line raised against a cost code that has NO matching budget line will
auto-create a flagged £0 budget line (one per unbudgeted order line
group). The new columns track the flag, the raiser's reason, the
provenance (PO vs package), and the director acknowledgement audit
trail. The variance scan must NEVER touch the variance_status /
requires_attention of an unacknowledged unbudgeted line (D-E1) — that
isolation lives in the service layer, but the dedicated `is_unbudgeted`
+ `unbudgeted_cleared_at` columns are what make it possible to
distinguish "needs director sign-off" from "ordinary Red variance".

Up:
  Part A — six additive columns on `budget_lines`:
    1. is_unbudgeted         BOOLEAN  NOT NULL  server_default=false
    2. unbudgeted_reason     TEXT     NULL
    3. unbudgeted_source     VARCHAR(20) NULL   ('purchase_order' | 'package')
    4. unbudgeted_created_by UUID NULL  FK→users.id ON DELETE SET NULL
       (fk_budget_lines_unbudgeted_created_by_users)
    5. unbudgeted_cleared_by UUID NULL  FK→users.id ON DELETE SET NULL
       (fk_budget_lines_unbudgeted_cleared_by_users)
    6. unbudgeted_cleared_at TIMESTAMP(timezone=True) NULL

    The NOT NULL boolean lands its server_default at ALTER time so the
    ALTER succeeds against existing rows (mirrors the
    `requires_attention` / `is_contingency` / `is_locked` pattern in
    migration 0024). server_default is RETAINED on the live column —
    it is the intended permanent default and the model carries the
    same default; matches the precedent of the other NOT-NULL booleans
    on `budget_lines` whose server_defaults were never dropped after
    create_table.

  Part B — extend the `permission_action` PG enum:
    ALTER TYPE permission_action ADD VALUE IF NOT EXISTS 'clear_unbudgeted'
    Must run inside an autocommit_block — Postgres forbids ALTER TYPE
    ... ADD VALUE inside a regular transaction. Precedent 0020 / 0048.
    `IF NOT EXISTS` makes a partial-re-run safe.

    The new enum value is INTENTIONALLY NOT used in this migration's
    body. The budgets.clear_unbudgeted permission ROW is seeded by
    seed_rbac in a separate transaction at bootstrap time (D2 ordering
    lesson — a newly-added enum value is unusable in the same
    transaction that added it).

  Part A and Part B are independent: A touches no enum, B is
  self-contained inside its autocommit block. Either order works; we
  run B first so the migration's transactional DDL block (Part A)
  contains only the column adds.

Down:
  - Drop the two named FK constraints first, then the six columns
    (reverse add order).
  - The 'clear_unbudgeted' value remains in the `permission_action`
    PG enum, orphaned. Postgres cannot DROP an enum value inside a
    transaction; we deliberately do not attempt it. Precedent 0020
    (orphaned 'submit' / 'view_financials'), 0047, 0048 (orphaned
    'labour' / 'subcontract' / 'consultant'). The orphan is a
    pure-information cost — no row references it after downgrade.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0049_unbudgeted_order_lines"
down_revision = "0048_package_kind_3value_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Part B. Extend the PG enum. MUST be in an autocommit_block:
    # Postgres does not allow ALTER TYPE ... ADD VALUE inside a normal
    # transaction. Precedent 0020 / 0048. `IF NOT EXISTS` keeps the
    # operation idempotent against a partial prior run.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE permission_action "
            "ADD VALUE IF NOT EXISTS 'clear_unbudgeted'"
        )

    # ── Part A. Six additive columns on budget_lines.
    # Column 1 — is_unbudgeted (NOT NULL boolean; server_default lets
    # the ALTER succeed against pre-existing rows and is retained,
    # matching the pattern set by requires_attention / is_contingency
    # / is_locked in migration 0024).
    op.add_column(
        "budget_lines",
        sa.Column(
            "is_unbudgeted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Column 2 — unbudgeted_reason (raiser's mandatory "why no
    # budget?" note; nullable because legacy rows have no reason).
    op.add_column(
        "budget_lines",
        sa.Column(
            "unbudgeted_reason",
            sa.Text(),
            nullable=True,
        ),
    )

    # Column 3 — unbudgeted_source ('purchase_order' | 'package').
    # Plain VARCHAR(20) rather than a new PG enum: the value set is
    # small, stable, and not referenced by any other table, so the
    # enum maintenance cost is not justified. The service layer is
    # the single writer and only emits the two valid strings.
    op.add_column(
        "budget_lines",
        sa.Column(
            "unbudgeted_source",
            sa.String(length=20),
            nullable=True,
        ),
    )

    # Column 4 — unbudgeted_created_by (FK → users.id, SET NULL).
    op.add_column(
        "budget_lines",
        sa.Column(
            "unbudgeted_created_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_budget_lines_unbudgeted_created_by_users",
        "budget_lines",
        "users",
        ["unbudgeted_created_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # Column 5 — unbudgeted_cleared_by (FK → users.id, SET NULL).
    op.add_column(
        "budget_lines",
        sa.Column(
            "unbudgeted_cleared_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_budget_lines_unbudgeted_cleared_by_users",
        "budget_lines",
        "users",
        ["unbudgeted_cleared_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # Column 6 — unbudgeted_cleared_at (timezone-aware DateTime,
    # mirroring last_actual_posted_at / created_at conventions on
    # this table).
    op.add_column(
        "budget_lines",
        sa.Column(
            "unbudgeted_cleared_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # ── Part A'. Drop columns in reverse order. Drop the two named
    # FK constraints first so the column drops don't have to chase
    # a dependency.
    op.drop_column("budget_lines", "unbudgeted_cleared_at")

    op.drop_constraint(
        "fk_budget_lines_unbudgeted_cleared_by_users",
        "budget_lines",
        type_="foreignkey",
    )
    op.drop_column("budget_lines", "unbudgeted_cleared_by")

    op.drop_constraint(
        "fk_budget_lines_unbudgeted_created_by_users",
        "budget_lines",
        type_="foreignkey",
    )
    op.drop_column("budget_lines", "unbudgeted_created_by")

    op.drop_column("budget_lines", "unbudgeted_source")
    op.drop_column("budget_lines", "unbudgeted_reason")
    op.drop_column("budget_lines", "is_unbudgeted")

    # ── Part B'. The 'clear_unbudgeted' value remains in the
    # `permission_action` PG enum (orphaned). Postgres cannot DROP
    # an enum value inside a transaction; we deliberately do not
    # attempt it. Precedent: 0020 (orphaned 'submit',
    # 'view_financials'), 0047, 0048 (orphaned 'labour',
    # 'subcontract', 'consultant'). After downgrade no permission
    # row references it, so the orphan is a pure-information cost.
