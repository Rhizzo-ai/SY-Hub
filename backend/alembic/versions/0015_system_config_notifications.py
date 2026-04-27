"""0015 system_config + notifications tables — Prompt 1.7

Revision ID: 0015_system_config_notifications
Revises: 0014_cost_codes_permissions

Creates:
- system_config: typed key/value store for runtime-tunable settings
  (global catalogue, no tenant_id). Adds the spec-listed columns plus
  `default_value` (snapshot of seed value, used by /restore endpoint).
- notifications: user-scoped dispatch records. ON DELETE CASCADE on
  recipient_user_id so user deletion cleans inbox.

Both tables get the standard set_updated_at trigger only where the
table has an updated_at column (system_config only — notifications is
append-flagged via PATCH so we skip the trigger by spec).

Spec deviations:
- Added `default_value` column to system_config (supports /restore
  without re-running seed).
- Extended `system_config_category` enum with `Audit` and `System`
  (the audit retention / timezone keys need a home).
"""
from alembic import op
import sqlalchemy as sa


revision = "0015_system_config_notifications"
down_revision = "0014_cost_code_permissions"
branch_labels = None
depends_on = None


CONFIG_VALUE_TYPES = ("String", "Integer", "Decimal", "Boolean", "JSON", "Date")
CONFIG_CATEGORIES = (
    "Finance", "Appraisal", "Budget", "CashFlow", "Programme",
    "Document", "Security", "Integration", "Notification", "Reporting",
    "Audit", "System",
)
NOTIFICATION_TYPES = (
    "Approval_Requested", "Approval_Decision", "Budget_Variance",
    "Programme_Alert", "Document_Shared", "Mention", "Assignment",
    "System_Announcement", "Integration_Error", "Security_Alert",
    "Deadline_Approaching", "Task_Overdue", "Xero_Sync_Error",
    "Insurance_Expiry", "Certificate_Expiry",
)
NOTIFICATION_PRIORITIES = ("Low", "Normal", "High", "Critical")


def upgrade() -> None:
    value_type_enum = sa.Enum(*CONFIG_VALUE_TYPES, name="system_config_value_type")
    category_enum = sa.Enum(*CONFIG_CATEGORIES, name="system_config_category")
    notif_type_enum = sa.Enum(*NOTIFICATION_TYPES, name="notification_type")
    notif_priority_enum = sa.Enum(*NOTIFICATION_PRIORITIES, name="notification_priority")

    op.create_table(
        "system_config",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("config_key", sa.String(100), nullable=False, unique=True),
        sa.Column("config_value", sa.Text, nullable=False),
        sa.Column("value_type", value_type_enum, nullable=False),
        sa.Column("category", category_enum, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("is_system_locked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("minimum_role_to_edit",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("default_value", sa.Text, nullable=False),
        sa.Column("last_changed_by_user_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("last_changed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_system_config_category", "system_config", ["category"])

    op.execute(
        "CREATE TRIGGER trg_system_config_updated_at "
        "BEFORE UPDATE ON system_config "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("recipient_user_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("notification_type", notif_type_enum, nullable=False),
        sa.Column("priority", notif_priority_enum, nullable=False, server_default="Normal"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("related_resource_type", sa.String(100)),
        sa.Column("related_resource_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("action_url", sa.Text),
        sa.Column("action_label", sa.String(50)),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("is_dismissed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column("email_sent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("email_sent_at", sa.DateTime(timezone=True)),
        sa.Column("sms_sent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sms_sent_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_notifications_recipient_unread_created",
        "notifications", ["recipient_user_id", "is_read", "created_at"],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_notifications_related_resource",
        "notifications", ["related_resource_type", "related_resource_id"],
    )
    op.create_index(
        "ix_notifications_expires_at",
        "notifications", ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_expires_at", table_name="notifications")
    op.drop_index("ix_notifications_related_resource", table_name="notifications")
    op.drop_index("ix_notifications_recipient_unread_created", table_name="notifications")
    op.drop_table("notifications")
    op.execute("DROP TRIGGER IF EXISTS trg_system_config_updated_at ON system_config;")
    op.drop_index("ix_system_config_category", table_name="system_config")
    op.drop_table("system_config")
    op.execute("DROP TYPE IF EXISTS notification_priority;")
    op.execute("DROP TYPE IF EXISTS notification_type;")
    op.execute("DROP TYPE IF EXISTS system_config_category;")
    op.execute("DROP TYPE IF EXISTS system_config_value_type;")
