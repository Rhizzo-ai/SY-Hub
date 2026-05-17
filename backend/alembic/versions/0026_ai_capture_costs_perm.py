"""0026 — ai_capture.view_costs permission (B38 cost dashboard).

Revision ID: 0026_ai_capture_costs_perm
Revises: 0025_actuals

Adds:
  - permission_resource enum value 'ai_capture'
  - permission_action enum value 'view_costs'
  - permissions row code='ai_capture.view_costs' (is_sensitive=true)
  - role_permissions grants for super_admin, director, finance

Idempotent. Safe to re-run.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0026_ai_capture_costs_perm"
down_revision = "0025_actuals"
branch_labels = None
depends_on = None


MIGRATION_AUDIT_NAMESPACE = uuid.UUID("3a14a3e0-1f2c-4f8a-9c5d-bb1f6f3e0026")

ROLES_GRANTED = ("super_admin", "director", "finance")


def upgrade() -> None:
    # ENUM extensions must run outside a transaction (Postgres limitation).
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE permission_resource ADD VALUE IF NOT EXISTS 'ai_capture'"
        )
        op.execute(
            "ALTER TYPE permission_action ADD VALUE IF NOT EXISTS 'view_costs'"
        )

    bind = op.get_bind()

    # Insert permission row (idempotent via ON CONFLICT).
    bind.execute(sa.text("""
        INSERT INTO permissions (id, code, resource, action, description, is_sensitive)
        VALUES (
            gen_random_uuid(),
            'ai_capture.view_costs',
            'ai_capture',
            'view_costs',
            'View aggregated AI capture cost / token / volume statistics',
            true
        )
        ON CONFLICT (code) DO NOTHING
    """))

    # Grant to roles (idempotent via NOT EXISTS join).
    inserted = 0
    for role_code in ROLES_GRANTED:
        result = bind.execute(sa.text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.code = :role AND p.code = 'ai_capture.view_costs'
              AND NOT EXISTS (
                SELECT 1 FROM role_permissions rp
                WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
        """), {"role": role_code})
        inserted += result.rowcount or 0

    # Audit row.
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
            "target": "permissions + role_permissions",
            "permissions": ["ai_capture.view_costs"],
            "roles_granted": list(ROLES_GRANTED),
            "rows_inserted": inserted,
        }),
        "now": datetime.now(timezone.utc),
    })


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions rp
        USING permissions p
        WHERE rp.permission_id = p.id
          AND p.code = 'ai_capture.view_costs'
    """)
    op.execute(
        "DELETE FROM permissions WHERE code = 'ai_capture.view_costs'"
    )
    # ENUM values not removable in Postgres; leave in place.
