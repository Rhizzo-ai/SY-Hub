"""0004 sessions and login history

Revision ID: 0004_sessions_and_history
Revises: 0003_rename_mfa_enrolled_at
Create Date: 2026-04-21

Adds user_sessions + user_login_history tables and an append-only trigger on
user_login_history. Part of Prompt 1.3 stage 1b (sessions + refresh tokens +
login history + password reset).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_sessions_and_history"
down_revision = "0003_rename_mfa_enrolled_at"
branch_labels = None
depends_on = None


SESSION_REVOKED_REASONS = (
    "Logout",
    "Password_Change",
    "Password_Reset",
    "Admin_Revoke",
    "Suspicious_Activity",
    "Expiry",
    "Replay_Detected",
    "User_Suspended",
)

LOGIN_HISTORY_EVENTS = (
    "Login_Success",
    "Login_Failed",
    "Logout",
    "Password_Change",
    "Password_Reset_Requested",
    "Password_Reset_Completed",
    "MFA_Success",
    "MFA_Failed",
    "MFA_Enrolled",
    "MFA_Disabled",
    "Account_Locked",
    "Account_Unlocked",
    "Session_Revoked",
    "Refresh_Success",
    "Refresh_Failed",
    "SSO_Link",
    "SSO_Unlink",
    "Impersonation_Start",
    "Impersonation_End",
    "Suspicious_Activity_Detected",
)

LOGIN_HISTORY_FAILURE_REASONS = (
    "Invalid_Password",
    "Unknown_Email",
    "MFA_Invalid",
    "MFA_Missing",
    "Account_Locked",
    "Account_Suspended",
    "Invitation_Expired",
    "Invitation_Used",
    "Reset_Token_Invalid",
    "Reset_Token_Expired",
    "Refresh_Token_Invalid",
    "Refresh_Token_Replay",
    "SSO_Provider_Error",
    "SSO_Email_Mismatch",
    "Rate_Limited",
)


def upgrade() -> None:
    # Enums
    reason_enum = postgresql.ENUM(
        *SESSION_REVOKED_REASONS,
        name="session_revoked_reason",
        create_type=True,
    )
    event_enum = postgresql.ENUM(
        *LOGIN_HISTORY_EVENTS,
        name="login_history_event_type",
        create_type=True,
    )
    failure_enum = postgresql.ENUM(
        *LOGIN_HISTORY_FAILURE_REASONS,
        name="login_history_failure_reason",
        create_type=True,
    )
    reason_enum.create(op.get_bind(), checkfirst=True)
    event_enum.create(op.get_bind(), checkfirst=True)
    failure_enum.create(op.get_bind(), checkfirst=True)

    # ----- user_sessions -----
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("access_token_jti", sa.String(64), nullable=False),
        sa.Column("refresh_token_hash", sa.Text, nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("user_agent", sa.Text, nullable=False),
        sa.Column("device_fingerprint", sa.Text),
        sa.Column("device_name", sa.String(100)),
        sa.Column("location_country", sa.String(50)),
        sa.Column("location_city", sa.String(100)),
        sa.Column("location_latitude", sa.Numeric(9, 6)),
        sa.Column("location_longitude", sa.Numeric(9, 6)),
        sa.Column("impersonator_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("remember_me", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason",
                  postgresql.ENUM(name="session_revoked_reason", create_type=False)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_user_sessions_user_revoked",
                    "user_sessions", ["user_id", "revoked_at"])
    op.create_index("ix_user_sessions_refresh_hash",
                    "user_sessions", ["refresh_token_hash"])
    op.create_index("ix_user_sessions_expires",
                    "user_sessions", ["expires_at"])

    # ----- user_login_history -----
    op.create_table(
        "user_login_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("email_attempted", sa.String(255), nullable=False),
        sa.Column("event_type",
                  postgresql.ENUM(name="login_history_event_type", create_type=False),
                  nullable=False),
        sa.Column("failure_reason",
                  postgresql.ENUM(name="login_history_failure_reason", create_type=False)),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("user_agent", sa.Text, nullable=False),
        sa.Column("location_country", sa.String(50)),
        sa.Column("location_city", sa.String(100)),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("user_sessions.id", ondelete="SET NULL")),
        sa.Column("metadata_json", postgresql.JSONB,
                  nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_login_history_user_created",
                    "user_login_history", ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_login_history_email_created",
                    "user_login_history", ["email_attempted", sa.text("created_at DESC")])
    op.create_index("ix_login_history_event_created",
                    "user_login_history", ["event_type", sa.text("created_at DESC")])

    # Append-only enforcement trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION user_login_history_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'user_login_history is append-only (% denied)', TG_OP;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER user_login_history_append_only_trigger
        BEFORE UPDATE OR DELETE ON user_login_history
        FOR EACH ROW EXECUTE FUNCTION user_login_history_append_only();
    """)

    # ----- email_send_log -----
    op.create_table(
        "email_send_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("to_address", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("template_id", sa.String(50)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_email_send_log_created", "email_send_log",
                    [sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_email_send_log_created", table_name="email_send_log")
    op.drop_table("email_send_log")

    op.execute("DROP TRIGGER IF EXISTS user_login_history_append_only_trigger ON user_login_history;")
    op.execute("DROP FUNCTION IF EXISTS user_login_history_append_only();")
    op.drop_index("ix_login_history_event_created", table_name="user_login_history")
    op.drop_index("ix_login_history_email_created", table_name="user_login_history")
    op.drop_index("ix_login_history_user_created", table_name="user_login_history")
    op.drop_table("user_login_history")

    op.drop_index("ix_user_sessions_expires", table_name="user_sessions")
    op.drop_index("ix_user_sessions_refresh_hash", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_revoked", table_name="user_sessions")
    op.drop_table("user_sessions")

    postgresql.ENUM(name="login_history_failure_reason").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="login_history_event_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="session_revoked_reason").drop(op.get_bind(), checkfirst=True)
