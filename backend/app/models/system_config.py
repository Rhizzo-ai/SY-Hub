"""SQLAlchemy models for system_config + notifications (Prompt 1.7)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


CONFIG_VALUE_TYPES = ("String", "Integer", "Decimal", "Boolean", "JSON", "Date")
CONFIG_CATEGORIES = (
    "Finance", "Appraisal", "Budget", "CashFlow", "Programme",
    "Document", "Security", "Integration", "Notification", "Reporting",
    "Audit", "System",
)


def _e(values, name):
    return SAEnum(*values, name=name, create_type=False, native_enum=True)


class SystemConfig(Base):
    __tablename__ = "system_config"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_key = Column(String(100), nullable=False, unique=True)
    config_value = Column(Text, nullable=False)
    value_type = Column(_e(CONFIG_VALUE_TYPES, "system_config_value_type"), nullable=False)
    category = Column(_e(CONFIG_CATEGORIES, "system_config_category"), nullable=False)
    description = Column(Text, nullable=False)
    is_system_locked = Column(Boolean, nullable=False, default=False)
    minimum_role_to_edit = Column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    default_value = Column(Text, nullable=False)
    last_changed_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
    )
    last_changed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
