"""Chat 45 §R1 (Build Pack 2.7-DOCS-BE) — Document Folder Engine.

This migration delivers Build Pack 2.7-DOCS-BE §R1, §R4.1, §R4.2, §R0.5.

Changes:
  - permission_action enum += 'move' (idempotent ALTER TYPE ADD VALUE
    inside an autocommit_block — mirrors 0020_permission_action_submit).
  - NEW table `document_folders` (polymorphic, self-referential, tenant-
    scoped, soft-delete via is_archived):
        id, tenant_id, owner_type, owner_id, parent_id (self-FK
        ON DELETE RESTRICT), name, is_archived, archived_at, archived_by,
        created_at/by, updated_at/by.
    Indexes: tenant_id, (owner_type, owner_id), parent_id.
    Constraints: CHECK owner_type IN ('supplier'); partial UNIQUE on
    (tenant_id, owner_type, owner_id, COALESCE(parent_id, '...zero...'), name)
    WHERE is_archived = false — prevents duplicate live sibling names.
  - RELAX `supplier_documents`:
        DROP CHECK ck_supplier_documents_doc_type (doc_type no longer
        constrained to the 7-value tuple at the DB layer; the validator
        still runs in the service when a value is supplied).
        ALTER doc_type → nullable.
        ALTER title    → nullable.
        ADD folder_id UUID nullable, FK document_folders.id ON DELETE
        SET NULL, indexed (ix_supplier_documents_folder_id).
  - DATA STEP (D2): create one 'Compliance' folder per supplier that has
    >=1 supplier_documents row (archived included). UPDATE every existing
    supplier_documents row to point at that folder. Author = the
    supplier's `created_by` user (sentinel pattern: 0018 precedent).
    Idempotent: skip suppliers that already own a 'Compliance' folder at
    the root (parent_id NULL, owner_type='supplier').
  - New permission catalogue row `documents.move` (sensitive=false) +
    role grants per §R4.3 (union of roles holding documents.edit OR
    supplier_documents.edit → project_manager + finance + super_admin +
    director). Per §R4.3b, finance also receives documents.create and
    documents.edit (new grants only — codes already exist from earlier
    seeds, but on a fresh DB the permissions catalogue is populated from
    seed_rbac.py at bootstrap and may not run before this migration body
    on alembic-only test paths — therefore we INSERT documents.move's
    catalogue row here as a belt-and-braces, then ON CONFLICT DO NOTHING
    if seed_rbac inserted it first; grants for already-existing codes
    use a sub-SELECT and likewise ON CONFLICT DO NOTHING).

Downgrade is best-effort. The doc_type / title NOT NULL re-add will FAIL
if any rows have NULL values created post-upgrade. Folder rows are
deleted and the supplier_documents.folder_id column dropped. The
permission_action enum value 'move' cannot be removed (Postgres
limitation); the grants + permission row are deleted for tidiness. The
documents.create/edit grants given to finance are NOT removed on
downgrade (they're operator-intent broadening, not migration-owned).

Revision id:  0043_document_folders
Revises:      0042_file_ref_text
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "0043_document_folders"
down_revision = "0042_file_ref_text"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, new_value: str) -> None:
    """Idempotent ALTER TYPE ADD VALUE — must run outside transaction."""
    with op.get_context().autocommit_block():
        op.execute(
            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{new_value}'"
        )


def upgrade() -> None:
    # ─── 1. permission_action enum += 'move' ────────────────────────────────
    _add_enum_value_if_missing("permission_action", "move")

    # ─── 2. Create document_folders table ───────────────────────────────────
    op.create_table(
        "document_folders",
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
        sa.Column("owner_type", sa.String(40), nullable=False),
        sa.Column(
            "owner_id", postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            "parent_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_folders.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
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
            "owner_type IN ('supplier')",
            name="ck_document_folders_owner_type",
        ),
    )
    op.create_index(
        "ix_document_folders_tenant_id",
        "document_folders",
        ["tenant_id"],
    )
    op.create_index(
        "ix_document_folders_owner",
        "document_folders",
        ["owner_type", "owner_id"],
    )
    op.create_index(
        "ix_document_folders_parent",
        "document_folders",
        ["parent_id"],
    )

    # Partial unique index — sibling-name uniqueness among LIVE rows.
    # COALESCE substitutes a sentinel UUID for NULL parent_id so root
    # siblings are deduped too. Postgres treats NULL distinct in a
    # plain UNIQUE; COALESCE forces a value.
    op.create_index(
        "uq_document_folders_sibling_name",
        "document_folders",
        [
            "tenant_id", "owner_type", "owner_id",
            sa.text(
                "COALESCE(parent_id, "
                "'00000000-0000-0000-0000-000000000000'::uuid)"
            ),
            "name",
        ],
        unique=True,
        postgresql_where=sa.text("is_archived = false"),
    )

    # ─── 3. Relax supplier_documents ────────────────────────────────────────
    op.drop_constraint(
        "ck_supplier_documents_doc_type", "supplier_documents", type_="check",
    )
    op.alter_column(
        "supplier_documents", "doc_type",
        existing_type=sa.String(40), nullable=True,
    )
    op.alter_column(
        "supplier_documents", "title",
        existing_type=sa.String(200), nullable=True,
    )
    op.add_column(
        "supplier_documents",
        sa.Column(
            "folder_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_supplier_documents_folder_id",
        "supplier_documents",
        ["folder_id"],
    )

    # ─── 4. DATA STEP (D2) — one 'Compliance' folder per supplier ───────────
    # Idempotent: only create a Compliance folder if the supplier has
    # supplier_documents AND no live Compliance folder already exists.
    # Author = the supplier's created_by (sentinel pattern: 0018 fallback).
    # All documents (archived included) get pointed at the folder so
    # unarchive lands them sensibly.
    op.execute(
        """
        WITH suppliers_with_docs AS (
            SELECT DISTINCT s.id AS supplier_id, s.tenant_id, s.created_by
              FROM suppliers s
              JOIN supplier_documents sd ON sd.supplier_id = s.id
        ),
        existing_folders AS (
            SELECT df.owner_id AS supplier_id
              FROM document_folders df
             WHERE df.owner_type = 'supplier'
               AND df.parent_id IS NULL
               AND df.name = 'Compliance'
               AND df.is_archived = false
        ),
        inserted AS (
            INSERT INTO document_folders (
                id, tenant_id, owner_type, owner_id, parent_id, name,
                is_archived, created_at, created_by, updated_at, updated_by
            )
            SELECT gen_random_uuid(), swd.tenant_id, 'supplier',
                   swd.supplier_id, NULL, 'Compliance',
                   false, now(), swd.created_by, now(), swd.created_by
              FROM suppliers_with_docs swd
              LEFT JOIN existing_folders ef
                     ON ef.supplier_id = swd.supplier_id
             WHERE ef.supplier_id IS NULL
            RETURNING id, owner_id
        )
        UPDATE supplier_documents sd
           SET folder_id = COALESCE(
                   (SELECT i.id FROM inserted i
                     WHERE i.owner_id = sd.supplier_id),
                   (SELECT df.id FROM document_folders df
                     WHERE df.owner_type = 'supplier'
                       AND df.owner_id = sd.supplier_id
                       AND df.parent_id IS NULL
                       AND df.name = 'Compliance'
                       AND df.is_archived = false
                     LIMIT 1)
               )
         WHERE sd.folder_id IS NULL;
        """
    )

    # ─── 5. Permission catalogue row + role grants for documents.move ──────
    op.execute(
        """
        INSERT INTO permissions (id, code, resource, action, description, is_sensitive)
        VALUES (
            gen_random_uuid(),
            'documents.move',
            'documents'::permission_resource,
            'move'::permission_action,
            'Move documents (and document folders) between folders.',
            FALSE
        )
        ON CONFLICT (code) DO NOTHING;
        """
    )
    # Role grants — §R4.3 union (roles holding documents.edit OR
    # supplier_documents.edit) = project_manager + finance. super_admin
    # and director receive everything via the catalogue-wildcard seed
    # path; mirror that here so a fresh-DB alembic-only upgrade is
    # self-consistent (matches 0035_subcontractors precedent).
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p ON p.code = 'documents.move'
         WHERE r.code IN (
                'super_admin', 'director',
                'project_manager', 'finance'
         )
        ON CONFLICT DO NOTHING;
        """
    )
    # §R4.3b — finance gains documents.create + documents.edit (already
    # seeded as catalogue rows). These are grant-only inserts.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p ON p.code IN ('documents.create','documents.edit')
         WHERE r.code = 'finance'
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    # 5. Remove role grants + permission row for documents.move.
    # NOTE: finance's documents.create/documents.edit grants are NOT
    # removed (they pre-existed for other roles and were a deliberate
    # broadening; downgrade is not the place to revoke them).
    op.execute(
        """
        DELETE FROM role_permissions
         WHERE permission_id IN (
            SELECT id FROM permissions WHERE code = 'documents.move'
         )
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'documents.move'")

    # 4. Data step reverse: clear folder_id pointers so the column drop
    #    succeeds cleanly (the FK is SET NULL on folder delete, but we
    #    drop the column itself; clearing avoids any future surprise).
    op.execute("UPDATE supplier_documents SET folder_id = NULL")

    # 3. Reverse supplier_documents relaxations. This will FAIL with a
    #    NOT NULL violation if any post-upgrade row has NULL doc_type or
    #    NULL title. Documented in the module docstring as best-effort.
    op.drop_index(
        "ix_supplier_documents_folder_id",
        table_name="supplier_documents",
    )
    op.drop_column("supplier_documents", "folder_id")
    op.alter_column(
        "supplier_documents", "title",
        existing_type=sa.String(200), nullable=False,
    )
    op.alter_column(
        "supplier_documents", "doc_type",
        existing_type=sa.String(40), nullable=False,
    )
    op.create_check_constraint(
        "ck_supplier_documents_doc_type",
        "supplier_documents",
        "doc_type IN ("
        "'Public_Liability','Employers_Liability',"
        "'Professional_Indemnity','CIS_Certificate',"
        "'Accreditation','Insurance_Other','Other'"
        ")",
    )

    # 2. Drop document_folders + its indexes.
    op.drop_index(
        "uq_document_folders_sibling_name", table_name="document_folders",
    )
    op.drop_index(
        "ix_document_folders_parent", table_name="document_folders",
    )
    op.drop_index(
        "ix_document_folders_owner", table_name="document_folders",
    )
    op.drop_index(
        "ix_document_folders_tenant_id", table_name="document_folders",
    )
    op.drop_table("document_folders")

    # 1. Enum-value removal: Postgres does NOT support ALTER TYPE DROP
    #    VALUE. The 'move' action remains in permission_action; it is
    #    inert without catalogue rows or grants. Consistent with the
    #    0020_permission_action_submit / 0035_subcontractors pattern.
