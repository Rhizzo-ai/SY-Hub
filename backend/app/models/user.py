"""User model — Prompt 1.2."""
from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, uuid4


PASSWORD_ALGORITHMS = ("argon2id", "bcrypt")
USER_TYPES = (
    "Internal",
    "External_Subcontractor",
    "External_Consultant",
    "External_Funder",
    "Service_Account",
)
MFA_METHODS = ("TOTP", "SMS", "Email")
USER_STATUSES = ("Pending_Invitation", "Active", "Suspended", "Archived")


password_algorithm_enum = SAEnum(
    *PASSWORD_ALGORITHMS, name="password_algorithm", create_type=True
)
user_type_enum = SAEnum(*USER_TYPES, name="user_type", create_type=True)
mfa_method_enum = SAEnum(*MFA_METHODS, name="mfa_method", create_type=True)
user_status_enum = SAEnum(*USER_STATUSES, name="user_status", create_type=True)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)  # lowercase
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    password_algorithm: Mapped[Optional[str]] = mapped_column(
        password_algorithm_enum, server_default=text("'argon2id'::password_algorithm")
    )
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    password_history: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    job_title: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)

    user_type: Mapped[str] = mapped_column(
        user_type_enum, nullable=False, server_default=text("'Internal'::user_type")
    )

    primary_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )

    timezone: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("'Europe/London'"))
    locale: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'en-GB'"))

    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    mfa_method: Mapped[Optional[str]] = mapped_column(mfa_method_enum)
    mfa_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    mfa_backup_codes_encrypted: Mapped[Optional[str]] = mapped_column(Text)
    mfa_enrolled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45))
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lockout_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    password_reset_token_hash: Mapped[Optional[str]] = mapped_column(Text)
    password_reset_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        user_status_enum, nullable=False, server_default=text("'Pending_Invitation'::user_status")
    )
    suspended_reason: Mapped[Optional[str]] = mapped_column(Text)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    invitation_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    invitation_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    invitation_token_hash: Mapped[Optional[str]] = mapped_column(Text)
    invitation_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    invited_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    admin_notes: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_users_email_lower",
            text("tenant_id"),
            text("LOWER(email)"),
            unique=True,
        ),
        Index("ix_users_status_created", "tenant_id", "status", "created_at"),
        Index("ix_users_user_type", "tenant_id", "user_type"),
    )
