"""Chat 33 §R1 (Prompt 2.6) — Budget Change Requests (BCRs) & Forecasts.

This migration delivers Build Pack 2.6 §R1.

Changes:
  - permission_action enum += 'apply' (idempotent ALTER TYPE ADD VALUE).
    'submit' is already in the enum (Prompt 2.2). 'view'/'create'/'edit'/
    'approve' exist. The 'budget_changes' resource is already in the
    permission_resource enum (pre-seeded in an earlier chat).
  - Add `budget_lines.is_contingency` Boolean NOT NULL DEFAULT false.
    Backfill: server_default 'false' applies to existing rows.
  - New table `budget_changes` (BCR header) with status state machine
    Draft → Submitted → Approved → Applied (+Rejected, +Withdrawn).
    Carries denormalised `tenant_id` (per `purchase_orders.tenant_id`
    Chat 24 R2 precedent) for list-time tenant filtering.
  - New table `budget_change_lines` (BCR detail) with signed `delta`.
  - New permission catalogue rows for `budget_changes.submit` +
    `budget_changes.apply`. The pre-existing 4 rows
    (view/create/edit/approve) are left untouched.
  - Role grants: project_manager + finance receive .submit + .apply
    (mirror operator decision Chat 33 §R0). super_admin + director
    receive via the seed_rbac.py wildcard.

DEFERRED FK: `budget_changes.source_variation_id` is a nullable UUID
with NO FK constraint. 2.8 will add the FK to
`subcontract_variations.id` once that table exists.

DEVIATION (operator-confirmed Chat 33 §R0): Build Pack §R2 sample list
omits the `edit` action and predicts +5 perms / count 115. The live
seed already carried `view/create/edit/approve` on `budget_changes`
prior to 2.6; we add only `submit` + `apply` (net +2 → count 112). Test
gate 31 reads baseline+2.

Revision id:  0036_budget_changes
Revises:      0035_subcontractors
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0036_budget_changes"
down_revision = "0035_subcontractors"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, new_value: str) -> None:
    """Idempotent ALTER TYPE ADD VALUE — must run outside transaction."""
    with op.get_context().autocommit_block():
        op.execute(
            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{new_value}'"
        )


def upgrade() -> None:
    # ─── 1. Enum extensions ────────────────────────────────────────────────
    # 'apply' is new to permission_action. 'submit' already exists.
    _add_enum_value_if_missing("permission_action", "apply")

    # ─── 2. budget_lines.is_contingency ────────────────────────────────────
    op.add_column(
        "budget_lines",
        sa.Column(
            "is_contingency", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ─── 3. budget_changes (BCR header) ────────────────────────────────────
    op.create_table(
        "budget_changes",
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
            "budget_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(30), nullable=False),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default=sa.text("'Draft'"),
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "net_impact", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        # 2.8 stub — NO FK yet.
        sa.Column("source_variation_id", postgresql.UUID(as_uuid=True),
                  nullable=True),

        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "submitted_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "applied_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rejected_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.Text, nullable=True),

        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.CheckConstraint(
            "change_type IN ('Transfer','ContingencyDrawdown','Adjustment')",
            name="ck_budget_changes_type",
        ),
        sa.CheckConstraint(
            "status IN ('Draft','Submitted','Approved','Applied','Rejected','Withdrawn')",
            name="ck_budget_changes_status",
        ),
        sa.UniqueConstraint(
            "budget_id", "reference",
            name="uq_budget_changes_budget_reference",
        ),
    )
    op.create_index(
        "ix_budget_changes_budget_status",
        "budget_changes", ["budget_id", "status"],
    )
    op.create_index(
        "ix_budget_changes_tenant_id",
        "budget_changes", ["tenant_id"],
    )

    # ─── 4. budget_change_lines (BCR detail) ───────────────────────────────
    op.create_table(
        "budget_change_lines",
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
            "budget_change_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_changes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "budget_line_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_lines.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("delta", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_budget_change_lines_change_id",
        "budget_change_lines", ["budget_change_id"],
    )

    # ─── 5. Permission catalogue rows (idempotent INSERT) ──────────────────
    # The pre-existing 4 rows (view/create/edit/approve) are untouched.
    op.execute("""
        INSERT INTO permissions (id, code, resource, action, description, is_sensitive)
        VALUES
            (gen_random_uuid(), 'budget_changes.submit',
             'budget_changes'::permission_resource,
             'submit'::permission_action,
             'Submit a budget change request for approval.', FALSE),
            (gen_random_uuid(), 'budget_changes.apply',
             'budget_changes'::permission_resource,
             'apply'::permission_action,
             'Apply an approved BCR (writes budget_lines.approved_changes).',
             TRUE)
        ON CONFLICT (code) DO NOTHING;
    """)

    # ─── 6. Role grants ────────────────────────────────────────────────────
    # super_admin + director receive everything via the seed_rbac.py
    # ALL_PERMISSION_CODES path on next boot. Migration explicitly grants
    # the new perms to:
    #   - super_admin, director: full set (all 6 budget_changes.*)
    #   - finance:           view + approve + apply
    #   - project_manager:   view + create + edit + submit + approve + apply
    # This re-states the seed_rbac.py mapping so the migration on its own
    # (fresh DB, no app boot yet) is consistent with seed_rbac.
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p ON p.code = ANY (CASE r.code
                WHEN 'super_admin' THEN ARRAY[
                    'budget_changes.submit','budget_changes.apply']
                WHEN 'director' THEN ARRAY[
                    'budget_changes.submit','budget_changes.apply']
                WHEN 'finance' THEN ARRAY[
                    'budget_changes.apply']
                WHEN 'project_manager' THEN ARRAY[
                    'budget_changes.submit','budget_changes.apply']
                ELSE ARRAY[]::text[]
            END)
         WHERE r.code IN (
                'super_admin','director','finance','project_manager')
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    # Reverse order.

    # 6. Remove role grants for the 2 new permissions.
    op.execute("""
        DELETE FROM role_permissions
         WHERE permission_id IN (
            SELECT id FROM permissions WHERE code IN (
                'budget_changes.submit','budget_changes.apply'
            )
         )
    """)

    # 5. Remove permission catalogue rows for the 2 new permissions.
    op.execute("""
        DELETE FROM permissions
         WHERE code IN (
            'budget_changes.submit','budget_changes.apply'
         )
    """)

    # 4. Drop budget_change_lines.
    op.drop_index(
        "ix_budget_change_lines_change_id",
        table_name="budget_change_lines",
    )
    op.drop_table("budget_change_lines")

    # 3. Drop budget_changes.
    op.drop_index(
        "ix_budget_changes_tenant_id",
        table_name="budget_changes",
    )
    op.drop_index(
        "ix_budget_changes_budget_status",
        table_name="budget_changes",
    )
    op.drop_table("budget_changes")

    # 2. Drop budget_lines.is_contingency.
    op.drop_column("budget_lines", "is_contingency")

    # 1. Enum-value removal: Postgres does NOT support ALTER TYPE DROP VALUE.
    #    The 'apply' value remains in permission_action; inert without
    #    catalogue rows or grants. Asymmetry consistent with the
    #    0029/0035 downgrade pattern.
