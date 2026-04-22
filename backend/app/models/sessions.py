"""Session + login-history + email-log models — Prompt 1.3 stage 1b."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, uuid4


SESSION_REVOKED_REASONS = (
    "Logout", "Password_Change", "Password_Reset", "Admin_Revoke",
    "Suspicious_Activity", "Expiry", "Replay_Detected", "User_Suspended",
)

LOGIN_HISTORY_EVENTS = (
    "Login_Success", "Login_Failed", "Logout",
    "Password_Change", "Password_Reset_Requested", "Password_Reset_Completed",
    "MFA_Success", "MFA_Failed", "MFA_Enrolled", "MFA_Disabled",
    "Account_Locked", "Account_Unlocked",
    "Session_Revoked", "Refresh_Success", "Refresh_Failed",
    "SSO_Link", "SSO_Unlink",
    "Impersonation_Start", "Impersonation_End",
    "Suspicious_Activity_Detected",
)

LOGIN_HISTORY_FAILURE_REASONS = (
    "Invalid_Password", "Unknown_Email", "MFA_Invalid", "MFA_Missing",
    "Account_Locked", "Account_Suspended",
    "Invitation_Expired", "Invitation_Used",
    "Reset_Token_Invalid", "Reset_Token_Expired",
    "Refresh_Token_Invalid", "Refresh_Token_Replay",
    "SSO_Provider_Error", "SSO_Email_Mismatch",
    "Rate_Limited",
)

# create_type=False — Alembic 0004 already created the PG types.
session_revoked_reason_enum = SAEnum(
    *SESSION_REVOKED_REASONS, name="session_revoked_reason", create_type=False
)
login_history_event_enum = SAEnum(
    *LOGIN_HISTORY_EVENTS, name="login_history_event_type", create_type=False
)
login_history_failure_enum = SAEnum(
    *LOGIN_HISTORY_FAILURE_REASONS, name="login_history_failure_reason", create_type=False
)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    access_token_jti: Mapped[str] = mapped_column(String(64), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
    device_fingerprint: Mapped[Optional[str]] = mapped_column(Text)
    device_name: Mapped[Optional[str]] = mapped_column(String(100))
    previous_refresh_token_hash: Mapped[Optional[str]] = mapped_column(Text)
    location_country: Mapped[Optional[str]] = mapped_column(String(50))
    location_city: Mapped[Optional[str]] = mapped_column(String(100))
    location_latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6))
    location_longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6))
    impersonator_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
    )
    remember_me: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[Optional[str]] = mapped_column(session_revoked_reason_enum)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class UserLoginHistory(Base):
    __tablename__ = "user_login_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
    )
    email_attempted: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(login_history_event_enum, nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(login_history_failure_enum)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
    location_country: Mapped[Optional[str]] = mapped_column(String(50))
    location_city: Mapped[Optional[str]] = mapped_column(String(100))
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_sessions.id", ondelete="SET NULL"),
    )
    # Column renamed to avoid SQLAlchemy's reserved `metadata` attribute.
    metadata_json: Mapped[dict] = mapped_column("metadata_json", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class EmailSendLog(Base):
    __tablename__ = "email_send_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    template_id: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
