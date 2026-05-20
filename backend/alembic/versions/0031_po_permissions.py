"""Chat 24 §R2 (Prompt 2.5) — Purchase Order permissions.

Adds the `pos.*` permission block (R2 catalogue) and grants them to the
in-repo roles per build pack §2.3 mapping:

  super_admin / director:  pos.view, pos.view_sensitive, pos.create,
                           pos.edit, pos.edit_issued, pos.delete,
                           pos.submit, pos.approve, pos.void, pos.close,
                           pos.reopen, pos.receipt
  finance:                 view, view_sensitive, create, edit, edit_issued,
                           approve, void, close, receipt
  project_manager:         view, create, edit, submit, void, receipt
  site_manager:            view, receipt

The `receipt` action is enum-added here even though the actual receipts
table lands in R4 — having the permission seeded now means the auth
guards in R2's PO routes can already check it.

Also adds the `pos` value to the `permission_resource` enum so the new
permission rows are insertable.

Revision id:  0031_po_permissions
Revises:      0030_purchase_orders
"""
from __future__ import annotations

from alembic import op


revision = "0031_po_permissions"
down_revision = "0030_purchase_orders"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, new_value: str) -> None:
    """Add a value to a PostgreSQL ENUM, idempotently, in autocommit mode."""
    bind = op.get_bind()
    with bind.execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(
            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{new_value}'"
        )


def upgrade() -> None:
    # ─── 1. Enum extensions ──────────────────────────────────────────────────
    _add_enum_value_if_missing("permission_resource", "pos")
    _add_enum_value_if_missing("permission_action", "edit_issued")
    _add_enum_value_if_missing("permission_action", "issue")
    _add_enum_value_if_missing("permission_action", "void")
    _add_enum_value_if_missing("permission_action", "close")
    _add_enum_value_if_missing("permission_action", "receipt")
    # audit_action additions for PO state transitions surfaced via audit_log
    _add_enum_value_if_missing("audit_action", "Issue")

    # ─── 2. Permission catalogue rows ───────────────────────────────────────
    # Build pack §2.3 — exactly 11 pos.* rows. Combined with R1's 5
    # suppliers.* rows (migration 0029), this brings the catalogue
    # from 86 → 102 permissions (G2.8 gate).
    op.execute("""
        INSERT INTO permissions (code, resource, action, description, sensitive)
        VALUES
            ('pos.view',
             'pos'::permission_resource,
             'view'::permission_action,
             'View purchase orders.', FALSE),
            ('pos.view_sensitive',
             'pos'::permission_resource,
             'view_sensitive'::permission_action,
             'View pricing on purchase orders.', TRUE),
            ('pos.create',
             'pos'::permission_resource,
             'create'::permission_action,
             'Create draft purchase orders.', FALSE),
            ('pos.edit',
             'pos'::permission_resource,
             'edit'::permission_action,
             'Edit draft + approved purchase orders.', FALSE),
            ('pos.edit_issued',
             'pos'::permission_resource,
             'edit_issued'::permission_action,
             'Annotate header notes / delivery notes / external '
             'reference on issued+ purchase orders.', FALSE),
            ('pos.delete',
             'pos'::permission_resource,
             'delete'::permission_action,
             'Delete draft purchase orders only.', TRUE),
            ('pos.issue',
             'pos'::permission_resource,
             'issue'::permission_action,
             'Move a PO into the issued state — either via submit '
             '(no approval required) or via issue after approval.',
             FALSE),
            ('pos.approve',
             'pos'::permission_resource,
             'approve'::permission_action,
             'Approve / reject pending PO approvals.', FALSE),
            ('pos.void',
             'pos'::permission_resource,
             'void'::permission_action,
             'Void a draft / pending / approved / issued PO.', TRUE),
            ('pos.close',
             'pos'::permission_resource,
             'close'::permission_action,
             'Close a partially-receipted or receipted PO.', FALSE),
            ('pos.receipt',
             'pos'::permission_resource,
             'receipt'::permission_action,
             'Record goods receipts against issued POs.', FALSE)
        ON CONFLICT (code) DO NOTHING;
    """)

    # ─── 3. Role grants ─────────────────────────────────────────────────────
    # Build pack §9.2 maps role intent to the in-repo role catalogue:
    #
    #   spec name           in-repo code      relationship
    #   --------------------------------------------------
    #   super_admin         super_admin       1:1
    #   admin               (none)            director (one step below)
    #                                         already has all-but-admin.
    #   director            director          1:1
    #   finance_director    finance           1:1 (renamed)
    #   contracts_manager   project_manager   1:1 (renamed)
    #   site_manager        site_manager      1:1
    #   designer            (none)            no equivalent in this repo;
    #                                         deliberate no-op for now.
    #
    # Grant matrix (role × code) — per build pack §2.3 default columns:
    #   super_admin / director: ALL 11
    #   finance:                view, view_sensitive, approve
    #                           (finance APPROVES + SEES money; does NOT
    #                            raise/issue/receipt POs — build pack §9.2)
    #   project_manager:        view, view_sensitive, create, edit, issue,
    #                           receipt, close, delete (8 perms — no
    #                           edit_issued, no approve, no void)
    #   site_manager:           view, receipt
    #   read_only:              view  (matches the read-only-everywhere pattern)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
          FROM roles r
          JOIN permissions p ON p.code = ANY (CASE r.code
                WHEN 'super_admin' THEN ARRAY[
                    'pos.view','pos.view_sensitive',
                    'pos.create','pos.edit','pos.edit_issued',
                    'pos.delete','pos.issue','pos.approve',
                    'pos.void','pos.close','pos.receipt']
                WHEN 'director' THEN ARRAY[
                    'pos.view','pos.view_sensitive',
                    'pos.create','pos.edit','pos.edit_issued',
                    'pos.delete','pos.issue','pos.approve',
                    'pos.void','pos.close','pos.receipt']
                WHEN 'finance' THEN ARRAY[
                    'pos.view','pos.view_sensitive','pos.approve']
                WHEN 'project_manager' THEN ARRAY[
                    'pos.view','pos.view_sensitive','pos.create','pos.edit',
                    'pos.issue','pos.receipt','pos.close','pos.delete']
                WHEN 'site_manager' THEN ARRAY[
                    'pos.view','pos.receipt']
                WHEN 'read_only' THEN ARRAY[
                    'pos.view']
                ELSE ARRAY[]::text[]
            END)
         WHERE r.code IN
                ('super_admin','director','finance',
                 'project_manager','site_manager','read_only')
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions
         WHERE permission_id IN (
            SELECT id FROM permissions WHERE code LIKE 'pos.%'
         )
    """)
    op.execute("DELETE FROM permissions WHERE code LIKE 'pos.%'")
    # Enum values: Postgres does not support ALTER TYPE DROP VALUE — left in
    # place (same convention as 0029, 0026).
