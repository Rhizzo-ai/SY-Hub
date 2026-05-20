"""Chat 24 §R1 (Prompt 2.5) — Suppliers + Project Number Prefixes.

This migration is the foundational schema for Purchase Orders & PO/Bill
numbering (Phase 2 / Prompt 2.5). It adds:

  - `pg_trgm` extension (used by the supplier name search index)
  - `suppliers` table — tenant-scoped supplier directory with portal stubs
  - `project_number_prefixes` table — per-project, per-entity-type
    numbering namespaces (PO and BILL)
  - `pnp_enforce_single_default()` trigger function + AFTER trigger
    ensuring at most one is_default=true row per (project_id, entity_type)
  - Enum extensions: permission_resource += 'suppliers',
    permission_action += 'archive'
  - 5 supplier permissions + role grants per Chat 24 §2.3 (mapped to
    real roles: super_admin auto, director auto, project_manager,
    finance, site_manager)
  - Data backfill: for every existing project, seed two
    null-middle is_default=true rows (one for entity_type='po', one for
    entity_type='bill')

Bills entity itself is OUT OF SCOPE for Prompt 2.5 — only the numbering
namespace is allocated.

Revision id:  0029_suppliers_prefixes
Revises:      0028_user_preferences_table
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0029_suppliers_prefixes"
down_revision = "0028_user_preferences_table"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Enum extensions must run outside any transaction (ALTER TYPE ADD VALUE).
# ---------------------------------------------------------------------------

def _add_enum_value_if_missing(enum_name: str, new_value: str) -> None:
    """Add a value to a PostgreSQL ENUM, idempotently, outside the
    migration's transaction (ALTER TYPE ADD VALUE cannot run inside one)."""
    with op.get_context().autocommit_block():
        op.execute(
            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{new_value}'"
        )


def upgrade() -> None:
    # ─── 1. Extension ────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ─── 2. Enum extensions ──────────────────────────────────────────────────
    _add_enum_value_if_missing("permission_resource", "suppliers")
    _add_enum_value_if_missing("permission_action", "archive")
    _add_enum_value_if_missing("audit_action", "Archive")
    _add_enum_value_if_missing("audit_action", "Restore")

    # ─── 3. suppliers table ──────────────────────────────────────────────────
    op.create_table(
        "suppliers",
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
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("trading_name", sa.String(200), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("contact_email", sa.String(200), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("address_line1", sa.String(200), nullable=True),
        sa.Column("address_line2", sa.String(200), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("postcode", sa.String(20), nullable=True),
        sa.Column(
            "country", sa.String(50), nullable=True,
            server_default=sa.text("'United Kingdom'"),
        ),
        sa.Column("vat_number", sa.String(50), nullable=True),
        sa.Column("company_number", sa.String(50), nullable=True),
        sa.Column("cis_status", sa.String(20), nullable=True),
        sa.Column("bank_name", sa.String(200), nullable=True),
        sa.Column("bank_account_no", sa.String(50), nullable=True),
        sa.Column("bank_sort_code", sa.String(20), nullable=True),
        sa.Column(
            "payment_terms_days", sa.Integer, nullable=True,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "default_vat_rate", sa.Numeric(5, 2), nullable=True,
            server_default=sa.text("20.00"),
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "portal_enabled", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("portal_invite_token", sa.String(128), nullable=True),
        sa.Column(
            "portal_invite_sent_at",
            sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "portal_last_login_at",
            sa.DateTime(timezone=True), nullable=True,
        ),
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
            "cis_status IS NULL OR cis_status IN "
            "('gross', 'net_20', 'net_30', 'not_registered')",
            name="ck_suppliers_cis_status",
        ),
        sa.CheckConstraint(
            "default_vat_rate IS NULL OR "
            "(default_vat_rate >= 0 AND default_vat_rate <= 100)",
            name="ck_suppliers_vat_rate_range",
        ),
        sa.CheckConstraint(
            "payment_terms_days IS NULL OR payment_terms_days >= 0",
            name="ck_suppliers_payment_terms_nonneg",
        ),
    )
    # Standard indexes
    op.create_index(
        "ix_suppliers_tenant_id", "suppliers", ["tenant_id"],
    )
    op.create_index(
        "ix_suppliers_tenant_archived",
        "suppliers", ["tenant_id", "is_archived"],
    )
    # Unique supplier name per tenant (case-insensitive)
    op.create_index(
        "ux_suppliers_tenant_name_ci",
        "suppliers",
        ["tenant_id", sa.text("LOWER(name)")],
        unique=True,
    )
    # Trigram search on name (used by R5 supplier picker)
    op.execute(
        "CREATE INDEX ix_suppliers_name_trgm "
        "ON suppliers USING gin (name gin_trgm_ops)"
    )

    # ─── 4. project_number_prefixes table ───────────────────────────────────
    op.create_table(
        "project_number_prefixes",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(10), nullable=False),
        sa.Column("middle_prefix", sa.String(8), nullable=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column(
            "is_default", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_archived", sa.Boolean, nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "next_sequence", sa.Integer, nullable=False,
            server_default=sa.text("1"),
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
            "entity_type IN ('po', 'bill')",
            name="ck_pnp_entity_type",
        ),
        sa.CheckConstraint(
            # Shape: 1-8 chars, A-Z / 0-9 / dash, no leading or trailing dash.
            "middle_prefix IS NULL OR middle_prefix ~ "
            "'^[A-Z0-9]([A-Z0-9-]{0,6}[A-Z0-9])?$'",
            name="ck_pnp_middle_shape",
        ),
        sa.CheckConstraint(
            "next_sequence >= 1",
            name="ck_pnp_next_sequence_positive",
        ),
    )
    op.create_index(
        "ix_pnp_project_entity",
        "project_number_prefixes",
        ["project_id", "entity_type"],
    )
    # UNIQUE (project_id, entity_type, middle_prefix) — NULLS NOT DISTINCT so
    # the null-middle row is unique per (project_id, entity_type).
    op.execute(
        "CREATE UNIQUE INDEX ux_pnp_project_entity_middle "
        "ON project_number_prefixes "
        "(project_id, entity_type, middle_prefix) NULLS NOT DISTINCT"
    )

    # ─── 5. Single-default trigger ──────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION pnp_enforce_single_default()
        RETURNS TRIGGER AS $$
        BEGIN
            -- When a row is marked default, demote any other default
            -- in the same (project_id, entity_type) namespace.
            IF NEW.is_default IS TRUE THEN
                UPDATE project_number_prefixes
                   SET is_default = FALSE,
                       updated_at = now()
                 WHERE project_id = NEW.project_id
                   AND entity_type = NEW.entity_type
                   AND id <> NEW.id
                   AND is_default IS TRUE;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_pnp_single_default
        AFTER INSERT OR UPDATE OF is_default ON project_number_prefixes
        FOR EACH ROW
        WHEN (NEW.is_default IS TRUE)
        EXECUTE FUNCTION pnp_enforce_single_default();
    """)

    # ─── 6. Permission catalogue rows ───────────────────────────────────────
    # Use ON CONFLICT to remain idempotent against repeat-runs / seed_rbac.
    op.execute("""
        INSERT INTO permissions (id, code, resource, action, description, is_sensitive)
        VALUES
            (gen_random_uuid(), 'suppliers.view',
             'suppliers'::permission_resource,
             'view'::permission_action,
             'View supplier directory (non-sensitive fields).', FALSE),
            (gen_random_uuid(), 'suppliers.view_sensitive',
             'suppliers'::permission_resource,
             'view_sensitive'::permission_action,
             'View supplier banking + VAT + company-number fields.', TRUE),
            (gen_random_uuid(), 'suppliers.create',
             'suppliers'::permission_resource,
             'create'::permission_action,
             'Create new suppliers in the tenant directory.', FALSE),
            (gen_random_uuid(), 'suppliers.edit',
             'suppliers'::permission_resource,
             'edit'::permission_action,
             'Edit supplier records (incl. sensitive fields with view_sensitive).', FALSE),
            (gen_random_uuid(), 'suppliers.archive',
             'suppliers'::permission_resource,
             'archive'::permission_action,
             'Archive or unarchive supplier records (no hard-delete).', TRUE)
        ON CONFLICT (code) DO NOTHING;
    """)

    # ─── 7. Role grants ─────────────────────────────────────────────────────
    # Build pack §2.3 maps to existing roles thus:
    #   super_admin → super_admin   (gets all via seed_rbac; explicit here too)
    #   director   → director      (gets all via seed_rbac; explicit here too)
    #   finance_director → finance
    #   contracts_manager → project_manager
    #   site_manager → site_manager
    #   (admin, designer — no equivalent in this repo; skipped)
    #
    # Grant matrix (role × code):
    #   super_admin / director:      view, view_sensitive, create, edit, archive
    #   finance:                     view, view_sensitive, create, edit, archive
    #   project_manager:             view, create, edit
    #   site_manager:                view
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p ON p.code = ANY (CASE r.code
                WHEN 'super_admin' THEN ARRAY[
                    'suppliers.view','suppliers.view_sensitive',
                    'suppliers.create','suppliers.edit','suppliers.archive']
                WHEN 'director' THEN ARRAY[
                    'suppliers.view','suppliers.view_sensitive',
                    'suppliers.create','suppliers.edit','suppliers.archive']
                WHEN 'finance' THEN ARRAY[
                    'suppliers.view','suppliers.view_sensitive',
                    'suppliers.create','suppliers.edit','suppliers.archive']
                WHEN 'project_manager' THEN ARRAY[
                    'suppliers.view','suppliers.create','suppliers.edit']
                WHEN 'site_manager' THEN ARRAY[
                    'suppliers.view']
                ELSE ARRAY[]::text[]
            END)
         WHERE r.code IN
                ('super_admin','director','finance','project_manager','site_manager')
        ON CONFLICT DO NOTHING;
    """)

    # ─── 8. Backfill null-middle default prefixes for existing projects ─────
    # Each project gets one null-middle is_default=true row per entity_type.
    # created_by/updated_by is set to the first super_admin user; if no
    # super_admin exists yet (fresh tenants pre-seed), use any user with
    # the project's tenant.
    op.execute("""
        WITH seed_user AS (
            SELECT u.id AS user_id
              FROM users u
              JOIN user_roles ur ON ur.user_id = u.id
              JOIN roles r ON r.id = ur.role_id
             WHERE r.code = 'super_admin'
             ORDER BY u.created_at ASC
             LIMIT 1
        )
        INSERT INTO project_number_prefixes (
            project_id, entity_type, middle_prefix, description,
            is_default, is_archived, next_sequence,
            created_by, updated_by
        )
        SELECT p.id,
               et.entity_type,
               NULL,
               'Default ' || UPPER(et.entity_type) || ' numbering',
               TRUE, FALSE, 1,
               (SELECT user_id FROM seed_user),
               (SELECT user_id FROM seed_user)
          FROM projects p
          CROSS JOIN (VALUES ('po'), ('bill')) AS et(entity_type)
         WHERE EXISTS (SELECT 1 FROM seed_user)
        ON CONFLICT (project_id, entity_type, middle_prefix) DO NOTHING;
    """)


def downgrade() -> None:
    # Reverse order of upgrade.

    # 8. Remove backfilled prefix rows (defensive — DROP TABLE below handles
    #    everything, but kept for clarity if the table drop is skipped).
    op.execute("DELETE FROM project_number_prefixes")

    # 7. Remove role grants for the 5 supplier permissions.
    op.execute("""
        DELETE FROM role_permissions
         WHERE permission_id IN (
            SELECT id FROM permissions WHERE code IN (
                'suppliers.view','suppliers.view_sensitive',
                'suppliers.create','suppliers.edit','suppliers.archive'
            )
         )
    """)

    # 6. Remove permission catalogue rows.
    op.execute("""
        DELETE FROM permissions
         WHERE code IN (
            'suppliers.view','suppliers.view_sensitive',
            'suppliers.create','suppliers.edit','suppliers.archive'
         )
    """)

    # 5. Drop trigger + function.
    op.execute("DROP TRIGGER IF EXISTS trg_pnp_single_default ON project_number_prefixes")
    op.execute("DROP FUNCTION IF EXISTS pnp_enforce_single_default()")

    # 4. Drop project_number_prefixes.
    op.drop_index("ix_pnp_project_entity", table_name="project_number_prefixes")
    op.execute("DROP INDEX IF EXISTS ux_pnp_project_entity_middle")
    op.drop_table("project_number_prefixes")

    # 3. Drop suppliers.
    op.execute("DROP INDEX IF EXISTS ix_suppliers_name_trgm")
    op.drop_index("ux_suppliers_tenant_name_ci", table_name="suppliers")
    op.drop_index("ix_suppliers_tenant_archived", table_name="suppliers")
    op.drop_index("ix_suppliers_tenant_id", table_name="suppliers")
    op.drop_table("suppliers")

    # 2. Enum-value removals: Postgres does NOT support ALTER TYPE DROP VALUE.
    #    The 'suppliers' resource and 'archive' action remain in the enum;
    #    they are inert without catalogue rows or grants. This is consistent
    #    with the 0026_ai_capture_costs_perm downgrade pattern.

    # 1. pg_trgm extension is intentionally NOT dropped — other code paths
    #    (e.g. future fuzzy search on cost codes) may depend on it.
