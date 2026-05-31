"""Chat 34 §R1 (Prompt 2.8a) — Subcontracts & Variations.

Delivers Build Pack 2.8a §R1.

Changes:
  - permission_action enum += 'cost' (idempotent ALTER TYPE ADD VALUE).
    'issue' is already in the enum (PO 2.5). 'view'/'create'/'approve'
    exist.
  - New table `subcontracts` (subcontract header) with state machine
    Draft → Active → Completed (+ Terminated terminal). Linked
    optionally to a purchase order (LD1 nullable + service-guarded)
    and to a `suppliers` row where `supplier_type='Subcontractor'`
    (LD2, validated at service layer).
  - New table `subcontract_variations` (variation header) with state
    machine Raised → Costed → Approved → Issued (+ Rejected /
    Withdrawn terminal).
  - Deferred FK: `budget_changes.source_variation_id` →
    `subcontract_variations.id` ON DELETE SET NULL (LD3). The column
    already existed (2.6 stub); this migration adds the constraint
    only.
  - 10 new permissions (5 subcontracts + 5 subcontract_variations).
  - Role grants mirroring the live `seed_rbac.py` map (operator
    decision Chat 34 §R0): super_admin + director full set;
    project_manager create/edit/cost (+ view); finance approve/issue
    (+ view); read_only view only.

Revision id:  0037_subcontracts
Revises:      0036_budget_changes
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0037_subcontracts"
down_revision = "0036_budget_changes"
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
    # 'cost' is new to permission_action. 'issue' already exists (PO 2.5).
    _add_enum_value_if_missing("permission_action", "cost")
    # New resource enum values for the catalogue rows below.
    _add_enum_value_if_missing("permission_resource", "subcontracts")
    _add_enum_value_if_missing("permission_resource", "subcontract_variations")

    # ─── 2. subcontracts header table ──────────────────────────────────────
    op.create_table(
        "subcontracts",
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
            "subcontractor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "purchase_order_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reference", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("scope_description", sa.Text, nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default=sa.text("'Draft'"),
        ),
        sa.Column(
            "original_contract_sum", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "current_contract_sum", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "retention_pct", sa.Numeric(5, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cis_applies", sa.Boolean, nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("start_on", sa.Date, nullable=True),
        sa.Column("end_on", sa.Date, nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "signed_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("po_reconciliation_note", sa.Text, nullable=True),
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
            "status IN ('Draft','Active','Completed','Terminated')",
            name="ck_subcontracts_status",
        ),
        sa.UniqueConstraint(
            "project_id", "reference",
            name="uq_subcontracts_project_reference",
        ),
    )
    op.create_index(
        "ix_subcontracts_project_status",
        "subcontracts", ["project_id", "status"],
    )
    op.create_index(
        "ix_subcontracts_tenant_id",
        "subcontracts", ["tenant_id"],
    )
    op.create_index(
        "ix_subcontracts_subcontractor_id",
        "subcontracts", ["subcontractor_id"],
    )

    # ─── 3. subcontract_variations header table ───────────────────────────
    op.create_table(
        "subcontract_variations",
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
            "subcontract_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subcontracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default=sa.text("'Raised'"),
        ),
        sa.Column("estimated_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("agreed_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("cost_treatment", sa.String(20), nullable=True),
        sa.Column(
            "generated_bcr_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("budget_changes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("costed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "costed_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "issued_by", postgresql.UUID(as_uuid=True),
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
            "status IN ('Raised','Costed','Approved','Issued',"
            "'Rejected','Withdrawn')",
            name="ck_subcontract_variations_status",
        ),
        sa.CheckConstraint(
            "cost_treatment IS NULL OR cost_treatment IN "
            "('WithinContractSum','BudgetChange')",
            name="ck_subcontract_variations_cost_treatment",
        ),
        sa.UniqueConstraint(
            "subcontract_id", "reference",
            name="uq_subcontract_variations_ref",
        ),
    )
    op.create_index(
        "ix_subcontract_variations_subcontract_status",
        "subcontract_variations", ["subcontract_id", "status"],
    )
    op.create_index(
        "ix_subcontract_variations_tenant_id",
        "subcontract_variations", ["tenant_id"],
    )

    # ─── 4. Deferred FK from 2.6 stub (LD3) ───────────────────────────────
    # The column already exists on budget_changes; add the constraint only.
    op.create_foreign_key(
        "fk_budget_changes_source_variation_id",
        source_table="budget_changes",
        referent_table="subcontract_variations",
        local_cols=["source_variation_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # ─── 5. Permission catalogue rows (idempotent INSERT) ─────────────────
    op.execute("""
        INSERT INTO permissions (id, code, resource, action, description, is_sensitive)
        VALUES
            (gen_random_uuid(), 'subcontracts.view',
             'subcontracts'::permission_resource,
             'view'::permission_action,
             'View subcontracts.', FALSE),
            (gen_random_uuid(), 'subcontracts.view_sensitive',
             'subcontracts'::permission_resource,
             'view_sensitive'::permission_action,
             'View sensitive subcontract fields (contract sums).', TRUE),
            (gen_random_uuid(), 'subcontracts.create',
             'subcontracts'::permission_resource,
             'create'::permission_action,
             'Create a subcontract.', FALSE),
            (gen_random_uuid(), 'subcontracts.edit',
             'subcontracts'::permission_resource,
             'edit'::permission_action,
             'Edit a subcontract.', FALSE),
            (gen_random_uuid(), 'subcontracts.approve',
             'subcontracts'::permission_resource,
             'approve'::permission_action,
             'Approve / activate / terminate a subcontract.', TRUE),
            (gen_random_uuid(), 'subcontract_variations.view',
             'subcontract_variations'::permission_resource,
             'view'::permission_action,
             'View subcontract variations.', FALSE),
            (gen_random_uuid(), 'subcontract_variations.create',
             'subcontract_variations'::permission_resource,
             'create'::permission_action,
             'Raise a subcontract variation.', FALSE),
            (gen_random_uuid(), 'subcontract_variations.cost',
             'subcontract_variations'::permission_resource,
             'cost'::permission_action,
             'Set the agreed value on a subcontract variation.', FALSE),
            (gen_random_uuid(), 'subcontract_variations.approve',
             'subcontract_variations'::permission_resource,
             'approve'::permission_action,
             'Approve a subcontract variation (folds into contract sum '
             'or generates a BCR).', TRUE),
            (gen_random_uuid(), 'subcontract_variations.issue',
             'subcontract_variations'::permission_resource,
             'issue'::permission_action,
             'Issue (formal instruction) an approved subcontract '
             'variation.', TRUE)
        ON CONFLICT (code) DO NOTHING;
    """)

    # ─── 6. Role grants ────────────────────────────────────────────────────
    # Mirror live seed_rbac.py mapping (Chat 34 §R0):
    #   super_admin: ALL (via wildcard at boot — explicit here for fresh DB).
    #   director:    ALL except super_admin-only (none new).
    #   finance:     view + view_sensitive + approve + issue (money +
    #                authority surface mirrors `budget_changes.approve/apply`
    #                + `pos.approve` finance mapping).
    #   project_manager: view + create + edit + variation.create + .cost
    #                    (PM raises and costs; approval gated to
    #                    director/finance per Build Pack §R2).
    #   site_manager:    view (read-only).
    #   read_only:       view (read-only).
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p ON p.code = ANY (CASE r.code
                WHEN 'super_admin' THEN ARRAY[
                    'subcontracts.view','subcontracts.view_sensitive',
                    'subcontracts.create','subcontracts.edit',
                    'subcontracts.approve',
                    'subcontract_variations.view',
                    'subcontract_variations.create',
                    'subcontract_variations.cost',
                    'subcontract_variations.approve',
                    'subcontract_variations.issue']
                WHEN 'director' THEN ARRAY[
                    'subcontracts.view','subcontracts.view_sensitive',
                    'subcontracts.create','subcontracts.edit',
                    'subcontracts.approve',
                    'subcontract_variations.view',
                    'subcontract_variations.create',
                    'subcontract_variations.cost',
                    'subcontract_variations.approve',
                    'subcontract_variations.issue']
                WHEN 'finance' THEN ARRAY[
                    'subcontracts.view','subcontracts.view_sensitive',
                    'subcontracts.approve',
                    'subcontract_variations.view',
                    'subcontract_variations.approve',
                    'subcontract_variations.issue']
                WHEN 'project_manager' THEN ARRAY[
                    'subcontracts.view','subcontracts.view_sensitive',
                    'subcontracts.create','subcontracts.edit',
                    'subcontract_variations.view',
                    'subcontract_variations.create',
                    'subcontract_variations.cost']
                WHEN 'site_manager' THEN ARRAY[
                    'subcontracts.view',
                    'subcontract_variations.view']
                WHEN 'read_only' THEN ARRAY[
                    'subcontracts.view',
                    'subcontract_variations.view']
                ELSE ARRAY[]::text[]
            END)
         WHERE r.code IN (
                'super_admin','director','finance','project_manager',
                'site_manager','read_only')
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    # Reverse order.

    # 6. Remove role grants for the 10 new permissions.
    op.execute("""
        DELETE FROM role_permissions
         WHERE permission_id IN (
            SELECT id FROM permissions WHERE code IN (
                'subcontracts.view','subcontracts.view_sensitive',
                'subcontracts.create','subcontracts.edit',
                'subcontracts.approve',
                'subcontract_variations.view',
                'subcontract_variations.create',
                'subcontract_variations.cost',
                'subcontract_variations.approve',
                'subcontract_variations.issue'
            )
         )
    """)

    # 5. Remove permission catalogue rows.
    op.execute("""
        DELETE FROM permissions
         WHERE code IN (
            'subcontracts.view','subcontracts.view_sensitive',
            'subcontracts.create','subcontracts.edit',
            'subcontracts.approve',
            'subcontract_variations.view',
            'subcontract_variations.create',
            'subcontract_variations.cost',
            'subcontract_variations.approve',
            'subcontract_variations.issue'
         )
    """)

    # 4. Drop the source_variation_id FK constraint (column stays — 2.6 stub).
    op.drop_constraint(
        "fk_budget_changes_source_variation_id",
        "budget_changes",
        type_="foreignkey",
    )

    # 3. Drop subcontract_variations.
    op.drop_index(
        "ix_subcontract_variations_tenant_id",
        table_name="subcontract_variations",
    )
    op.drop_index(
        "ix_subcontract_variations_subcontract_status",
        table_name="subcontract_variations",
    )
    op.drop_table("subcontract_variations")

    # 2. Drop subcontracts.
    op.drop_index(
        "ix_subcontracts_subcontractor_id", table_name="subcontracts",
    )
    op.drop_index(
        "ix_subcontracts_tenant_id", table_name="subcontracts",
    )
    op.drop_index(
        "ix_subcontracts_project_status", table_name="subcontracts",
    )
    op.drop_table("subcontracts")

    # 1. Enum-value removal: Postgres does NOT support ALTER TYPE DROP VALUE.
    #    The 'cost' value remains in permission_action; inert without
    #    catalogue rows or grants. Asymmetry consistent with the
    #    0029/0035/0036 downgrade pattern.
