"""Chat 35 §R1 (Prompt 2.8b) — Subcontract Valuations, Payment Notices,
Retention Releases.

Delivers Build Pack 2.8b §R1.

Changes:
  - permission_action enum += 'certify', 'release' (idempotent
    ALTER TYPE ADD VALUE — outside transaction).
  - permission_resource enum += 'subcontract_valuations',
    'payment_notices' (idempotent — CHANGELOG deviation note: BP §R1.4
    listed permission_action only; resource enum addition agreed
    in Chat 35 §R0 reconciliation).
  - New table `subcontract_valuations` (cumulative JCT valuation chain).
  - New table `payment_notices` (Payment + PayLess notices).
  - New table `retention_releases` (PC / DLP release events).
  - Add FK `actuals.related_subcontract_id → subcontracts.id`
    ON DELETE SET NULL. Idempotent guard (column existed since 2.5;
    target table since 2.8a; FK deferred until now per Chat 35 §R0).
  - 7 new permissions: 4 subcontract_valuations.{view, view_sensitive,
    create, certify}, 3 payment_notices.{view, create, release}.
  - Role grants mirroring Chat 34 §R2 finance/director (certify +
    release authority) + PM (create/view).

Revision id:  0038_sc_valuations
Revises:      0037_subcontracts
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0038_sc_valuations"
down_revision = "0037_subcontracts"
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
    _add_enum_value_if_missing("permission_action", "certify")
    _add_enum_value_if_missing("permission_action", "release")
    _add_enum_value_if_missing("permission_resource", "subcontract_valuations")
    _add_enum_value_if_missing("permission_resource", "payment_notices")

    # ─── 2. subcontract_valuations table ──────────────────────────────────
    op.create_table(
        "subcontract_valuations",
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
            sa.ForeignKey("subcontracts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(30), nullable=False),
        sa.Column("valuation_number", sa.Integer, nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default=sa.text("'Draft'"),
        ),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column(
            "gross_applied_to_date", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "gross_this_cert", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "labour_portion", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "materials_portion", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        # Snapshots stored at certification.
        sa.Column("previous_certified_net", sa.Numeric(14, 2), nullable=True),
        sa.Column("retention_rate_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("retention_this_cert", sa.Numeric(14, 2), nullable=True),
        sa.Column("cis_rate_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "cis_deduction_this_cert", sa.Numeric(14, 2), nullable=True,
        ),
        sa.Column("net_payable_this_cert", sa.Numeric(14, 2), nullable=True),
        sa.Column("over_claim_flag", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("over_claim_note", sa.Text, nullable=True),
        # FK to posted actual on certification.
        sa.Column(
            "posted_actual_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actuals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Workflow stamps.
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "submitted_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "certified_by", postgresql.UUID(as_uuid=True),
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
            "status IN ('Draft','Submitted','Certified','Rejected')",
            name="ck_subcontract_valuations_status",
        ),
        sa.UniqueConstraint(
            "subcontract_id", "reference",
            name="uq_subcontract_valuations_ref",
        ),
        sa.UniqueConstraint(
            "subcontract_id", "valuation_number",
            name="uq_subcontract_valuations_number",
        ),
    )
    op.create_index(
        "ix_subcontract_valuations_subcontract_number",
        "subcontract_valuations", ["subcontract_id", "valuation_number"],
    )
    op.create_index(
        "ix_subcontract_valuations_tenant_id",
        "subcontract_valuations", ["tenant_id"],
    )

    # ─── 3. payment_notices table ─────────────────────────────────────────
    op.create_table(
        "payment_notices",
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
            "subcontract_valuation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "subcontract_valuations.id", ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("reference", sa.String(30), nullable=False),
        sa.Column(
            "notice_type", sa.String(20), nullable=False,
            server_default=sa.text("'Payment'"),
        ),
        sa.Column(
            "gross_certified", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "retention", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cis_deducted", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "net_due", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column(
            "issued_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.CheckConstraint(
            "notice_type IN ('Payment','PayLess')",
            name="ck_payment_notices_type",
        ),
    )
    op.create_index(
        "ix_payment_notices_valuation_id",
        "payment_notices", ["subcontract_valuation_id"],
    )
    op.create_index(
        "ix_payment_notices_tenant_id",
        "payment_notices", ["tenant_id"],
    )

    # ─── 4. retention_releases table ──────────────────────────────────────
    op.create_table(
        "retention_releases",
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
            sa.ForeignKey("subcontracts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("release_type", sa.String(10), nullable=False),
        sa.Column(
            "release_pct", sa.Numeric(5, 2), nullable=False,
            server_default=sa.text("50"),
        ),
        sa.Column(
            "amount_released", sa.Numeric(14, 2), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("released_on", sa.Date, nullable=False),
        sa.Column(
            "released_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "posted_actual_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("actuals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text, nullable=True),
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
            "release_type IN ('PC','DLP')",
            name="ck_retention_releases_type",
        ),
        sa.UniqueConstraint(
            "subcontract_id", "release_type",
            name="uq_retention_releases_subcontract_type",
        ),
    )
    op.create_index(
        "ix_retention_releases_subcontract_id",
        "retention_releases", ["subcontract_id"],
    )
    op.create_index(
        "ix_retention_releases_tenant_id",
        "retention_releases", ["tenant_id"],
    )

    # ─── 5. Deferred FK on actuals.related_subcontract_id ─────────────────
    # Column existed since 2.5; target table since 2.8a; FK added now.
    # Idempotent guard.
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT 1 FROM pg_constraint "
        "WHERE conname = 'fk_actuals_related_subcontract_id'"
    )).scalar()
    if not exists:
        op.create_foreign_key(
            "fk_actuals_related_subcontract_id",
            source_table="actuals",
            referent_table="subcontracts",
            local_cols=["related_subcontract_id"],
            remote_cols=["id"],
            ondelete="SET NULL",
        )

    # ─── 6. Permission catalogue rows (idempotent INSERT) ─────────────────
    op.execute("""
        INSERT INTO permissions (id, code, resource, action, description, is_sensitive)
        VALUES
            (gen_random_uuid(), 'subcontract_valuations.view',
             'subcontract_valuations'::permission_resource,
             'view'::permission_action,
             'View subcontract valuations.', FALSE),
            (gen_random_uuid(), 'subcontract_valuations.view_sensitive',
             'subcontract_valuations'::permission_resource,
             'view_sensitive'::permission_action,
             'View sensitive valuation fields (CIS / net payable).',
             TRUE),
            (gen_random_uuid(), 'subcontract_valuations.create',
             'subcontract_valuations'::permission_resource,
             'create'::permission_action,
             'Create / submit a subcontract valuation.', FALSE),
            (gen_random_uuid(), 'subcontract_valuations.certify',
             'subcontract_valuations'::permission_resource,
             'certify'::permission_action,
             'Certify a subcontract valuation (posts the actual).',
             TRUE),
            (gen_random_uuid(), 'payment_notices.view',
             'payment_notices'::permission_resource,
             'view'::permission_action,
             'View payment notices.', FALSE),
            (gen_random_uuid(), 'payment_notices.create',
             'payment_notices'::permission_resource,
             'create'::permission_action,
             'Issue a PayLess notice against a certified valuation.',
             FALSE),
            (gen_random_uuid(), 'payment_notices.release',
             'payment_notices'::permission_resource,
             'release'::permission_action,
             'Release retention (PC or DLP) on a subcontract.', TRUE)
        ON CONFLICT (code) DO NOTHING;
    """)

    # ─── 7. Role grants ────────────────────────────────────────────────────
    # Mirror Chat 34 §R2 mapping for the 2.8b actions:
    #   super_admin: ALL
    #   director:    ALL (sensitive included)
    #   finance:     view + view_sensitive + certify + payment_notices.*
    #                (the money-authorising surface — mirrors finance's
    #                subcontract_variations.approve/issue + .release for
    #                retention release).
    #   project_manager: view + create + payment_notices.view (raise +
    #                read; certify/release authority is finance/director).
    #   site_manager: view (read-only).
    #   read_only:    view (read-only).
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p ON p.code = ANY (CASE r.code
                WHEN 'super_admin' THEN ARRAY[
                    'subcontract_valuations.view',
                    'subcontract_valuations.view_sensitive',
                    'subcontract_valuations.create',
                    'subcontract_valuations.certify',
                    'payment_notices.view',
                    'payment_notices.create',
                    'payment_notices.release']
                WHEN 'director' THEN ARRAY[
                    'subcontract_valuations.view',
                    'subcontract_valuations.view_sensitive',
                    'subcontract_valuations.create',
                    'subcontract_valuations.certify',
                    'payment_notices.view',
                    'payment_notices.create',
                    'payment_notices.release']
                WHEN 'finance' THEN ARRAY[
                    'subcontract_valuations.view',
                    'subcontract_valuations.view_sensitive',
                    'subcontract_valuations.certify',
                    'payment_notices.view',
                    'payment_notices.create',
                    'payment_notices.release']
                WHEN 'project_manager' THEN ARRAY[
                    'subcontract_valuations.view',
                    'subcontract_valuations.view_sensitive',
                    'subcontract_valuations.create',
                    'payment_notices.view']
                WHEN 'site_manager' THEN ARRAY[
                    'subcontract_valuations.view',
                    'payment_notices.view']
                WHEN 'read_only' THEN ARRAY[
                    'subcontract_valuations.view',
                    'payment_notices.view']
                ELSE ARRAY[]::text[]
            END)
         WHERE r.code IN (
                'super_admin','director','finance','project_manager',
                'site_manager','read_only')
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    # Reverse order.

    # 7. Remove role grants for the 7 new permissions.
    op.execute("""
        DELETE FROM role_permissions
         WHERE permission_id IN (
            SELECT id FROM permissions WHERE code IN (
                'subcontract_valuations.view',
                'subcontract_valuations.view_sensitive',
                'subcontract_valuations.create',
                'subcontract_valuations.certify',
                'payment_notices.view',
                'payment_notices.create',
                'payment_notices.release'
            )
         )
    """)

    # 6. Remove permission catalogue rows.
    op.execute("""
        DELETE FROM permissions
         WHERE code IN (
            'subcontract_valuations.view',
            'subcontract_valuations.view_sensitive',
            'subcontract_valuations.create',
            'subcontract_valuations.certify',
            'payment_notices.view',
            'payment_notices.create',
            'payment_notices.release'
         )
    """)

    # 5. Drop the actuals FK.
    op.drop_constraint(
        "fk_actuals_related_subcontract_id",
        "actuals",
        type_="foreignkey",
    )

    # 4. Drop retention_releases.
    op.drop_index(
        "ix_retention_releases_tenant_id",
        table_name="retention_releases",
    )
    op.drop_index(
        "ix_retention_releases_subcontract_id",
        table_name="retention_releases",
    )
    op.drop_table("retention_releases")

    # 3. Drop payment_notices.
    op.drop_index(
        "ix_payment_notices_tenant_id", table_name="payment_notices",
    )
    op.drop_index(
        "ix_payment_notices_valuation_id", table_name="payment_notices",
    )
    op.drop_table("payment_notices")

    # 2. Drop subcontract_valuations.
    op.drop_index(
        "ix_subcontract_valuations_tenant_id",
        table_name="subcontract_valuations",
    )
    op.drop_index(
        "ix_subcontract_valuations_subcontract_number",
        table_name="subcontract_valuations",
    )
    op.drop_table("subcontract_valuations")

    # 1. Enum-value removal: Postgres does NOT support ALTER TYPE DROP VALUE.
    #    'certify' / 'release' remain in permission_action; new resources
    #    remain in permission_resource. Inert without catalogue rows.
