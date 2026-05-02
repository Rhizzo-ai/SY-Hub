"""Reference-data models for Track 2 — Prompt 2.1.

- `SdltRateBand` — global SDLT band row. Append-only versioning via
  (effective_from, effective_to). No tenant_id.
- `AppraisalDefaultSetting` — tenant-scoped appraisal default.
  Reuses `project_type_enum` from migration 0010 (1.5 projects).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Column, Date, DateTime, Enum as SAEnum, ForeignKey, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


SDLT_CATEGORIES = (
    "Residential_Standard",
    "Residential_Surcharge",
    "Non_Residential",
    "Corporate_Flat_Rate",
)
APPRAISAL_SETTING_TYPES = ("Percentage", "Absolute", "Boolean")

# Shared with `app/models/projects.PROJECT_TYPES` — keep in sync.
PROJECT_TYPES = ("Pure_Dev", "Dev_Build", "DB_Contract", "JV", "Main_Contract")


def _e(values, name):
    return SAEnum(*values, name=name, create_type=False, native_enum=True)


class SdltRateBand(Base):
    __tablename__ = "sdlt_rate_bands"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date)  # null = current
    category = Column(_e(SDLT_CATEGORIES, "sdlt_band_category"), nullable=False)
    band_lower = Column(Numeric(14, 2), nullable=False, default=0)
    band_upper = Column(Numeric(14, 2))  # null = no upper
    rate_pct = Column(Numeric(6, 3), nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AppraisalDefaultSetting(Base):
    __tablename__ = "appraisal_default_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    setting_key = Column(String(100), nullable=False)
    setting_value = Column(Numeric(14, 4), nullable=False)
    setting_type = Column(
        _e(APPRAISAL_SETTING_TYPES, "appraisal_setting_type"), nullable=False,
    )
    applies_to_project_type = Column(
        _e(PROJECT_TYPES, "project_type_enum"),
    )
    description = Column(Text, nullable=False)
    updated_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "setting_key", "applies_to_project_type",
            name="uq_appraisal_setting_key_scope",
        ),
    )
