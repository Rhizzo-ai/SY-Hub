"""Chat 32 §R1 (Prompt 2.7) — Subcontractors, CIS Verifications & Supplier Documents.

This migration delivers Build Pack 2.7 §R1.

Changes:
  - permission_action enum += 'verify' (idempotent ALTER TYPE ADD VALUE)
  - permission_resource enum += 'cis', 'supplier_documents' (idempotent)
  - CREATE TYPE supplier_type AS ENUM ('Supplier','Subcontractor') (idempotent)
  - Extend `suppliers` with 5 new columns:
        supplier_type        supplier_type NOT NULL DEFAULT 'Supplier'
        cis_subtype          VARCHAR(30) NULL
        cis_registered       BOOLEAN NOT NULL DEFAULT false
        utr                  VARCHAR(13) NULL  (sensitive — UK UTR, 10 digits)
        current_cis_status   VARCHAR(20) NULL  (service-maintained cache)
  - New table `subcontractor_cis_verifications` (append-only history)
  - New table `supplier_documents` (lightweight; soft-delete)
  - New permission catalogue rows for `cis.*` and `supplier_documents.*`
    + role grants (mirrors suppliers.create role distribution; sensitive
    actions follow suppliers.view_sensitive distribution; .verify mirrors
    suppliers.create.)

DEVIATION NOTE: The existing `suppliers.cis_status` column (added in
migration 0029) is LEFT IN PLACE. The new `current_cis_status` is the
authoritative cache populated by the CIS verification service. Dropping
the legacy column is OUT OF SCOPE for Prompt 2.7 (see CHANGELOG).

Revision id:  0035_subcontractors
Revises:      0034_audit_sendback
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0035_subcontractors"
down_revision = "0034_audit_sendback"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, new_value: str) -> None:
    """Idempotent ALTER TYPE ADD VALUE — must run outside transaction."""
    with op.get_context().autocommit_block():
        op.execute(
            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{new_value}'"
        )


def upgrade() -> None:
    # ─── 1. Enum extensions (existing PG enums) ─────────────────────────────
    _add_enum_value_if_missing("permission_action", "verify")
    _add_enum_value_if_missing("permission_resource", "cis")
    _add_enum_value_if_missing("permission_resource", "supplier_documents")

    # ─── 2. NEW PG enum supplier_type ───────────────────────────────────────
    # Guarded CREATE TYPE (idempotent). Plain CREATE TYPE has no IF NOT
    # EXISTS — use a DO block.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'supplier_type'
            ) THEN
                CREATE TYPE supplier_type AS ENUM ('Supplier', 'Subcontractor');
            END IF;
        END$$;
    """)

    # ─── 3. Extend suppliers ────────────────────────────────────────────────
    # `supplier_type` NOT NULL with server_default 'Supplier' — backfills
    # existing rows cleanly.
    op.add_column(
        "suppliers",
        sa.Column(
            "supplier_type",
            postgresql.ENUM(
                "Supplier", "Subcontractor",
                name="supplier_type", create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'Supplier'::supplier_type"),
        ),
    )
    op.add_column(
        "suppliers",
        sa.Column("cis_subtype", sa.String(30), nullable=True),
    )
    op.add_column(
        "suppliers",
        sa.Column(
            "cis_registered", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "suppliers",
        sa.Column("utr", sa.String(13), nullable=True),
    )
    op.add_column(
        "suppliers",
        sa.Column("current_cis_status", sa.String(20), nullable=True),
    )

    # ─── 4. subcontractor_cis_verifications (append-only) ───────────────────
    op.create_table(
        "subcontractor_cis_verifications",
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
            "supplier_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("verification_number", sa.String(20), nullable=True),
        sa.Column("match_status", sa.String(20), nullable=False),
        sa.Column("tax_rate_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("verified_on", sa.Date, nullable=False),
        sa.Column("expires_on", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "match_status IN ('Gross', 'Net', 'Unmatched')",
            name="ck_cis_match_status",
        ),
        sa.CheckConstraint(
            "tax_rate_pct IS NULL OR "
            "(tax_rate_pct >= 0 AND tax_rate_pct <= 100)",
            name="ck_cis_tax_rate_range",
        ),
    )
    op.create_index(
        "ix_cis_supplier_verified_desc",
        "subcontractor_cis_verifications",
        ["supplier_id", sa.text("verified_on DESC")],
    )
    op.create_index(
        "ix_cis_tenant_id",
        "subcontractor_cis_verifications",
        ["tenant_id"],
    )

    # ─── 5. supplier_documents (lightweight) ────────────────────────────────
    op.create_table(
        "supplier_documents",
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
            "supplier_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("file_ref", sa.String(500), nullable=True),
        sa.Column("issued_on", sa.Date, nullable=True),
        sa.Column("expires_on", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "is_archived", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "archived_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "archived_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.CheckConstraint(
            "doc_type IN ("
            "'Public_Liability','Employers_Liability',"
            "'Professional_Indemnity','CIS_Certificate',"
            "'Accreditation','Insurance_Other','Other'"
            ")",
            name="ck_supplier_documents_doc_type",
        ),
    )
    op.create_index(
        "ix_supplier_documents_supplier_doc_type",
        "supplier_documents",
        ["supplier_id", "doc_type"],
    )
    op.create_index(
        "ix_supplier_documents_tenant_id",
        "supplier_documents",
        ["tenant_id"],
    )

    # ─── 6. Permission catalogue rows ───────────────────────────────────────
    op.execute("""
        INSERT INTO permissions (id, code, resource, action, description, is_sensitive)
        VALUES
            (gen_random_uuid(), 'cis.view',
             'cis'::permission_resource,
             'view'::permission_action,
             'View CIS verification history for subcontractors.', FALSE),
            (gen_random_uuid(), 'cis.view_sensitive',
             'cis'::permission_resource,
             'view_sensitive'::permission_action,
             'View sensitive CIS fields (verification number, full history).', TRUE),
            (gen_random_uuid(), 'cis.verify',
             'cis'::permission_resource,
             'verify'::permission_action,
             'Record a new HMRC CIS verification on a subcontractor.', TRUE),
            (gen_random_uuid(), 'supplier_documents.view',
             'supplier_documents'::permission_resource,
             'view'::permission_action,
             'View supplier compliance documents (non-sensitive metadata).', FALSE),
            (gen_random_uuid(), 'supplier_documents.view_sensitive',
             'supplier_documents'::permission_resource,
             'view_sensitive'::permission_action,
             'View sensitive document fields (file refs, internal notes).', TRUE),
            (gen_random_uuid(), 'supplier_documents.create',
             'supplier_documents'::permission_resource,
             'create'::permission_action,
             'Upload supplier compliance documents.', FALSE),
            (gen_random_uuid(), 'supplier_documents.edit',
             'supplier_documents'::permission_resource,
             'edit'::permission_action,
             'Edit supplier compliance document metadata.', FALSE),
            (gen_random_uuid(), 'supplier_documents.archive',
             'supplier_documents'::permission_resource,
             'archive'::permission_action,
             'Archive/unarchive supplier compliance documents.', TRUE)
        ON CONFLICT (code) DO NOTHING;
    """)

    # ─── 7. Role grants ─────────────────────────────────────────────────────
    # Build pack §R2: cis.verify and supplier_documents.* go to the roles
    # that hold suppliers.create today. In this repo that resolves to:
    #   super_admin, director, finance, project_manager.
    # super_admin and director receive all perms automatically via the
    # ALL_PERMISSION_CODES seed path; finance and project_manager carry
    # explicit role-permission lists in seed_rbac.py. We mirror that here.
    #
    # cis.view / supplier_documents.view → broader (roles with suppliers.view):
    #   super_admin, director, finance, PM, site_manager, read_only.
    # cis.view_sensitive / supplier_documents.view_sensitive →
    #   roles with suppliers.view_sensitive: super_admin, director, finance.
    # cis.verify, supplier_documents.{create,edit,archive} → roles with
    #   suppliers.create: super_admin, director, finance, PM.
    #
    # Explicit grants here re-state the seed_rbac.py mapping so the
    # migration on its own (fresh DB, no app boot yet) is consistent.
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p ON p.code = ANY (CASE r.code
                WHEN 'super_admin' THEN ARRAY[
                    'cis.view','cis.view_sensitive','cis.verify',
                    'supplier_documents.view','supplier_documents.view_sensitive',
                    'supplier_documents.create','supplier_documents.edit',
                    'supplier_documents.archive']
                WHEN 'director' THEN ARRAY[
                    'cis.view','cis.view_sensitive','cis.verify',
                    'supplier_documents.view','supplier_documents.view_sensitive',
                    'supplier_documents.create','supplier_documents.edit',
                    'supplier_documents.archive']
                WHEN 'finance' THEN ARRAY[
                    'cis.view','cis.view_sensitive','cis.verify',
                    'supplier_documents.view','supplier_documents.view_sensitive',
                    'supplier_documents.create','supplier_documents.edit',
                    'supplier_documents.archive']
                WHEN 'project_manager' THEN ARRAY[
                    'cis.view','cis.verify',
                    'supplier_documents.view',
                    'supplier_documents.view_sensitive',
                    'supplier_documents.create','supplier_documents.edit',
                    'supplier_documents.archive']
                WHEN 'site_manager' THEN ARRAY[
                    'cis.view']
                WHEN 'read_only' THEN ARRAY[
                    'cis.view']
                ELSE ARRAY[]::text[]
            END)
         WHERE r.code IN (
                'super_admin','director','finance',
                'project_manager','site_manager','read_only')
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    # Reverse order of upgrade.

    # 7. Remove role grants for the 8 new permissions.
    op.execute("""
        DELETE FROM role_permissions
         WHERE permission_id IN (
            SELECT id FROM permissions WHERE code IN (
                'cis.view','cis.view_sensitive','cis.verify',
                'supplier_documents.view','supplier_documents.view_sensitive',
                'supplier_documents.create','supplier_documents.edit',
                'supplier_documents.archive'
            )
         )
    """)

    # 6. Remove permission catalogue rows.
    op.execute("""
        DELETE FROM permissions
         WHERE code IN (
            'cis.view','cis.view_sensitive','cis.verify',
            'supplier_documents.view','supplier_documents.view_sensitive',
            'supplier_documents.create','supplier_documents.edit',
            'supplier_documents.archive'
         )
    """)

    # 5. Drop supplier_documents.
    op.drop_index(
        "ix_supplier_documents_tenant_id",
        table_name="supplier_documents",
    )
    op.drop_index(
        "ix_supplier_documents_supplier_doc_type",
        table_name="supplier_documents",
    )
    op.drop_table("supplier_documents")

    # 4. Drop subcontractor_cis_verifications.
    op.drop_index(
        "ix_cis_tenant_id",
        table_name="subcontractor_cis_verifications",
    )
    op.drop_index(
        "ix_cis_supplier_verified_desc",
        table_name="subcontractor_cis_verifications",
    )
    op.drop_table("subcontractor_cis_verifications")

    # 3. Drop added supplier columns.
    op.drop_column("suppliers", "current_cis_status")
    op.drop_column("suppliers", "utr")
    op.drop_column("suppliers", "cis_registered")
    op.drop_column("suppliers", "cis_subtype")
    op.drop_column("suppliers", "supplier_type")

    # 2. Drop the supplier_type enum (now that no column references it).
    op.execute("DROP TYPE IF EXISTS supplier_type")

    # 1. Enum-value removals: Postgres does NOT support ALTER TYPE DROP VALUE.
    #    The 'cis' / 'supplier_documents' resources and 'verify' action
    #    remain in their respective enums; they are inert without catalogue
    #    rows or grants. This asymmetry is consistent with the
    #    0029_suppliers_prefixes downgrade pattern.
