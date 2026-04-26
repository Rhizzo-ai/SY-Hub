"""SQLAlchemy model for notifications (Prompt 1.7)."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


NOTIFICATION_TYPES = (
    "Approval_Requested", "Approval_Decision", "Budget_Variance",
    "Programme_Alert", "Document_Shared", "Mention", "Assignment",
    "System_Announcement", "Integration_Error", "Security_Alert",
    "Deadline_Approaching", "Task_Overdue", "Xero_Sync_Error",
    "Insurance_Expiry", "Certificate_Expiry",
)
NOTIFICATION_PRIORITIES = ("Low", "Normal", "High", "Critical")


def _e(values, name):
    return SAEnum(*values, name=name, create_type=False, native_enum=True)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type = Column(_e(NOTIFICATION_TYPES, "notification_type"), nullable=False)
    priority = Column(_e(NOTIFICATION_PRIORITIES, "notification_priority"),
                      nullable=False, default="Normal")
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    related_resource_type = Column(String(100))
    related_resource_id = Column(UUID(as_uuid=True))
    action_url = Column(Text)
    action_label = Column(String(50))
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True))
    is_dismissed = Column(Boolean, nullable=False, default=False)
    dismissed_at = Column(DateTime(timezone=True))
    email_sent = Column(Boolean, nullable=False, default=False)
    email_sent_at = Column(DateTime(timezone=True))
    sms_sent = Column(Boolean, nullable=False, default=False)
    sms_sent_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
