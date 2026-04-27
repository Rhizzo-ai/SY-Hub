"""0006 audit_log table + append-only trigger (Prompt 1.4)

Revision ID: 0006_audit_log
Revises: 0005_previous_refresh_hash
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_audit_log"
down_revision = "0005_previous_refresh_hash"
branch_labels = None
depends_on = None


AUDIT_ACTIONS = (
    "Create", "Update", "Delete",
    "Approve", "Reject", "Reopen",
    "Login", "Logout",
    "Export", "Permission_Change",
    "Stage_Change", "Status_Change",
)


def upgrade() -> None:
    audit_action = postgresql.ENUM(*AUDIT_ACTIONS, name="audit_action", create_type=True)
    audit_action.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("impersonator_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action",
                  postgresql.ENUM(*AUDIT_ACTIONS, name="audit_action", create_type=False),
                  nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True),
        # project_id FK deferred to Prompt 1.5 per spec; plain UUID for now.
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("field_changes", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("user_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )

    op.create_index("ix_audit_log_actor_created",
                    "audit_log", ["actor_user_id", sa.text("created_at DESC")])
    op.create_index("ix_audit_log_resource",
                    "audit_log", ["resource_type", "resource_id"])
    op.create_index("ix_audit_log_entity_created",
                    "audit_log", ["entity_id", sa.text("created_at DESC")])
    op.create_index("ix_audit_log_project_created",
                    "audit_log", ["project_id", sa.text("created_at DESC")])
    op.create_index("ix_audit_log_created",
                    "audit_log", [sa.text("created_at DESC")])
    op.create_index("ix_audit_log_action_created",
                    "audit_log", ["action", sa.text("created_at DESC")])

    # Append-only trigger. UPDATE/DELETE raise; bypassed only by the monthly
    # purge job which sets session_replication_role='replica' in its txn
    # (see app/services/audit_retention.py).
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_log_no_modify()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only; UPDATE/DELETE blocked';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_log_block_update
            BEFORE UPDATE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify();
    """)
    op.execute("""
        CREATE TRIGGER audit_log_block_delete
            BEFORE DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_no_modify();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_block_update ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_log_block_delete ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_no_modify()")
    op.drop_index("ix_audit_log_action_created", table_name="audit_log")
    op.drop_index("ix_audit_log_created", table_name="audit_log")
    op.drop_index("ix_audit_log_project_created", table_name="audit_log")
    op.drop_index("ix_audit_log_entity_created", table_name="audit_log")
    op.drop_index("ix_audit_log_resource", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_created", table_name="audit_log")
    op.drop_table("audit_log")
    postgresql.ENUM(name="audit_action").drop(op.get_bind(), checkfirst=True)
