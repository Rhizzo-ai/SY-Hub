"""0014 cost code permission grants

Revision ID: 0014_cost_code_permissions
Revises: 0013_cost_codes_seed

cost_codes.view + cost_codes.admin already exist in PERMISSION_CATALOGUE
(seeded by app.seed_rbac on startup). Per Prompt 1.6 §H, role grants
need to be extended for finance, project_manager, site_manager, sales,
read_only, investor_read_only, and consultant_portal.

We insert role_permission pairs idempotently here so existing DBs (which
have the catalogue but missing role grants) catch up. seed_rbac.py is
also updated in this commit so fresh boots Just Work.
"""
import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0014_cost_code_permissions"
down_revision = "0013_cost_codes_seed"
branch_labels = None
depends_on = None


MIGRATION_AUDIT_NAMESPACE = uuid.UUID("3a14a3e0-1f2c-4f8a-9c5d-bb1f6f3e0001")


# Roles that get cost_codes.view (per §H)
VIEW_ROLES = (
    "director", "finance", "project_manager", "site_manager",
    "sales", "read_only", "investor_read_only", "consultant_portal",
    "super_admin",
)

# Roles that get cost_codes.admin (per §H)
ADMIN_ROLES = ("super_admin", "director", "finance")


def upgrade() -> None:
    bind = op.get_bind()
    inserted = 0
    for role_code, perm_code in (
        *[(r, "cost_codes.view") for r in VIEW_ROLES],
        *[(r, "cost_codes.admin") for r in ADMIN_ROLES],
    ):
        # Idempotent insert via NOT EXISTS join
        result = bind.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.code = :role AND p.code = :perm
              AND NOT EXISTS (
                SELECT 1 FROM role_permissions rp
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """), {"role": role_code, "perm": perm_code})
        inserted += result.rowcount or 0

    rev_uuid = uuid.uuid5(MIGRATION_AUDIT_NAMESPACE, revision)
    bind.execute(sa.text("""
        INSERT INTO audit_log
            (id, action, resource_type, resource_id, field_changes,
             metadata_json, created_at)
        VALUES (gen_random_uuid(), 'Permission_Change', 'migration', :rid,
                CAST('[]' AS jsonb), CAST(:meta AS jsonb), :now)
    """), {
        "rid": str(rev_uuid),
        "meta": json.dumps({
            "kind": "seed_run", "revision": revision,
            "target": "role_permissions",
            "permissions": ["cost_codes.view", "cost_codes.admin"],
            "rows_inserted": inserted,
        }),
        "now": datetime.now(timezone.utc),
    })


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions rp
        USING permissions p
        WHERE rp.permission_id = p.id
          AND p.code IN ('cost_codes.view', 'cost_codes.admin')
    """)
