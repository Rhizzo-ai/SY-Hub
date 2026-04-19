"""0002 — users + RBAC + entities.created_by_user_id (Prompt 1.2).

Revision ID: 0002_users_rbac
Revises: 0001_initial_entities
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import func


revision = "0002_users_rbac"
down_revision = "0001_initial_entities"
branch_labels = None
depends_on = None


PASSWORD_ALGORITHMS = ("argon2id", "bcrypt")
USER_TYPES = (
    "Internal", "External_Subcontractor", "External_Consultant",
    "External_Funder", "Service_Account",
)
MFA_METHODS = ("TOTP", "SMS", "Email")
USER_STATUSES = ("Pending_Invitation", "Active", "Suspended", "Archived")
RESOURCES = (
    "entities", "projects", "users", "roles", "audit",
    "cost_codes", "appraisals", "budgets", "actuals",
    "commitments", "budget_changes", "cash_flow",
    "programmes", "programme_tasks", "documents",
    "document_registers", "certificates",
    "xero_connections", "xero_bills", "xero_invoices", "xero_sync",
    "system_config", "notifications", "reports",
)
ACTIONS = (
    "view", "view_sensitive", "create", "edit", "delete",
    "approve", "reopen", "export", "admin",
)
ENTITY_SCOPES = ("All", "Specific")
PROJECT_SCOPES = ("All", "Specific", "None")
USER_ROLE_STATUSES = ("Active", "Expired", "Revoked")


def _attach_updated_at(table: str) -> None:
    op.execute(
        f"""
        DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};
        CREATE TRIGGER trg_{table}_updated_at
        BEFORE UPDATE ON {table}
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def upgrade() -> None:
    bind = op.get_bind()

    # Enums
    for name, values in (
        ("password_algorithm", PASSWORD_ALGORITHMS),
        ("user_type", USER_TYPES),
        ("mfa_method", MFA_METHODS),
        ("user_status", USER_STATUSES),
        ("permission_resource", RESOURCES),
        ("permission_action", ACTIONS),
        ("entity_scope", ENTITY_SCOPES),
        ("project_scope", PROJECT_SCOPES),
        ("user_role_status", USER_ROLE_STATUSES),
    ):
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("password_hash", sa.Text),
        sa.Column(
            "password_algorithm",
            postgresql.ENUM(*PASSWORD_ALGORITHMS, name="password_algorithm", create_type=False),
            server_default=sa.text("'argon2id'::password_algorithm"),
        ),
        sa.Column("password_changed_at", sa.DateTime(timezone=True)),
        sa.Column("password_history", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("job_title", sa.String(255)),
        sa.Column("phone", sa.String(20)),
        sa.Column("phone_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("avatar_url", sa.Text),
        sa.Column(
            "user_type",
            postgresql.ENUM(*USER_TYPES, name="user_type", create_type=False),
            nullable=False, server_default=sa.text("'Internal'::user_type"),
        ),
        sa.Column(
            "primary_entity_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
        ),
        sa.Column("timezone", sa.String(50), nullable=False, server_default=sa.text("'Europe/London'")),
        sa.Column("locale", sa.String(10), nullable=False, server_default=sa.text("'en-GB'")),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "mfa_method",
            postgresql.ENUM(*MFA_METHODS, name="mfa_method", create_type=False),
        ),
        sa.Column("mfa_secret_encrypted", sa.Text),
        sa.Column("mfa_backup_codes_encrypted", sa.Text),
        sa.Column("mfa_enforced_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_ip", sa.String(45)),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("lockout_level", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("password_reset_token_hash", sa.Text),
        sa.Column("password_reset_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "status",
            postgresql.ENUM(*USER_STATUSES, name="user_status", create_type=False),
            nullable=False, server_default=sa.text("'Pending_Invitation'::user_status"),
        ),
        sa.Column("suspended_reason", sa.Text),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("invitation_sent_at", sa.DateTime(timezone=True)),
        sa.Column("invitation_accepted_at", sa.DateTime(timezone=True)),
        sa.Column("invitation_token_hash", sa.Text),
        sa.Column("invitation_expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "invited_by_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("admin_notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    _attach_updated_at("users")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_users_email_lower
        ON users (tenant_id, LOWER(email));
        """
    )
    op.create_index("ix_users_status_created", "users", ["tenant_id", "status", "created_at"])
    op.create_index("ix_users_user_type", "users", ["tenant_id", "user_type"])

    # roles
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("is_system_role", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("priority", sa.Integer, nullable=False, server_default=sa.text("50")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    _attach_updated_at("roles")

    # permissions
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "resource",
            postgresql.ENUM(*RESOURCES, name="permission_resource", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "action",
            postgresql.ENUM(*ACTIONS, name="permission_action", create_type=False),
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("is_sensitive", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
    )

    # role_permissions
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # user_roles
    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "entity_scope",
            postgresql.ENUM(*ENTITY_SCOPES, name="entity_scope", create_type=False),
            nullable=False, server_default=sa.text("'All'::entity_scope"),
        ),
        sa.Column(
            "project_scope",
            postgresql.ENUM(*PROJECT_SCOPES, name="project_scope", create_type=False),
            nullable=False, server_default=sa.text("'All'::project_scope"),
        ),
        sa.Column("view_overrides", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("assigned_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("revoked_reason", sa.Text),
        sa.Column(
            "status",
            postgresql.ENUM(*USER_ROLE_STATUSES, name="user_role_status", create_type=False),
            nullable=False, server_default=sa.text("'Active'::user_role_status"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    _attach_updated_at("user_roles")
    op.create_index("ix_user_roles_user_status", "user_roles", ["user_id", "status"])
    op.create_index("ix_user_roles_role", "user_roles", ["role_id"])
    op.create_index(
        "ix_user_roles_expires", "user_roles", ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )

    # user_role_entities
    op.create_table(
        "user_role_entities",
        sa.Column("user_role_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("user_roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_role_id", "entity_id"),
    )

    # user_role_projects — FK to projects added in Prompt 1.5
    op.create_table(
        "user_role_projects",
        sa.Column("user_role_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("user_roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_role_id", "project_id"),
    )

    # entities.created_by_user_id (retroactive from Prompt 1.1)
    op.add_column(
        "entities",
        sa.Column(
            "created_by_user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_entities_created_by", "entities", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_entities_created_by", table_name="entities")
    op.drop_column("entities", "created_by_user_id")

    op.drop_table("user_role_projects")
    op.drop_table("user_role_entities")

    op.execute("DROP TRIGGER IF EXISTS trg_user_roles_updated_at ON user_roles;")
    op.drop_index("ix_user_roles_expires", table_name="user_roles")
    op.drop_index("ix_user_roles_role", table_name="user_roles")
    op.drop_index("ix_user_roles_user_status", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_table("role_permissions")
    op.drop_table("permissions")

    op.execute("DROP TRIGGER IF EXISTS trg_roles_updated_at ON roles;")
    op.drop_table("roles")

    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users;")
    op.drop_index("ix_users_user_type", table_name="users")
    op.drop_index("ix_users_status_created", table_name="users")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")

    for name in (
        "user_role_status", "project_scope", "entity_scope",
        "permission_action", "permission_resource",
        "user_status", "mfa_method", "user_type", "password_algorithm",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name};")
