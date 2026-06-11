"""SQLAlchemy models for cost codes (Prompt 1.6)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, Integer, String,
    Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db import Base


P_AND_L_CATEGORIES = ("COS", "Overhead", "Finance", "Tax")
DEFAULT_ENTITY_VALUES = ("Parent", "SPV", "ConstructionCo", "Context_Dependent")
VAT_TREATMENTS = (
    "Standard", "Reduced", "Zero_New_Build",
    "Exempt", "Reverse_Charge", "Mixed",
)
COST_CODE_STATUSES = ("Active", "Retired")
SUBCAT_UNITS = (
    "each", "m", "m_squared", "m_cubed",
    "tonnes", "sum", "hours", "day", "week",
)


def _e(values, name):
    return SAEnum(*values, name=name, create_type=False, native_enum=True)


class CostCodeSection(Base):
    __tablename__ = "cost_code_sections"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    display_order = Column(Integer, nullable=False)
    is_direct_cost = Column(Boolean, nullable=False, default=True)
    default_p_and_l_category = Column(_e(P_AND_L_CATEGORIES, "cost_section_p_and_l"),
                                      nullable=False, default="COS")
    # B88 Pack 1 — two-tier group hierarchy.
    # parent_section_id NULL  → this row is a parent group (tier-1).
    # parent_section_id SET   → this row is a subgroup (tier-2).
    # Only sections with allows_subgroups=True may receive children;
    # only Construction (code "4") ships that way.
    parent_section_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cost_code_sections.id", ondelete="RESTRICT"),
        nullable=True,
    )
    allows_subgroups = Column(Boolean, nullable=False, server_default="false")
    # B88 Pack 2 — backend-enforced construction-scope filter.
    # Tier 2 callers (Construction Budget screen) only see lines whose
    # cost code rolls up to a section row carrying this flag. Migration
    # 0045 backfills true on code '4' + its subgroups; operators can
    # retoggle via PATCH /cost-code-sections/{id}.
    included_in_construction_scope = Column(
        Boolean, nullable=False, server_default="false",
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CostCode(Base):
    __tablename__ = "cost_codes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(10), nullable=False, unique=True)
    prefix = Column(String(3), nullable=False)
    sequence = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    section_id = Column(UUID(as_uuid=True),
                        ForeignKey("cost_code_sections.id", ondelete="RESTRICT"),
                        nullable=False)
    nrm_reference = Column(String(20))
    buildertrend_category = Column(String(100))
    applies_to_parent = Column(Boolean, nullable=False, default=False)
    applies_to_spv = Column(Boolean, nullable=False, default=True)
    applies_to_construction_co = Column(Boolean, nullable=False, default=False)
    default_entity = Column(_e(DEFAULT_ENTITY_VALUES, "cost_code_default_entity"),
                            nullable=False, default="SPV")
    entity_rule_notes = Column(Text)
    xero_nominal_code = Column(String(10))
    xero_nominal_name = Column(String(255))
    is_vattable = Column(Boolean, nullable=False, default=True)
    vat_treatment = Column(_e(VAT_TREATMENTS, "cost_code_vat_treatment"),
                           nullable=False, default="Standard")
    is_cis_applicable = Column(Boolean, nullable=False, default=False)
    is_retention_applicable = Column(Boolean, nullable=False, default=False)
    is_capitalisable = Column(Boolean, nullable=False, default=True)
    status = Column(_e(COST_CODE_STATUSES, "cost_code_status"),
                    nullable=False, default="Active")
    retired_at = Column(DateTime(timezone=True))
    retired_reason = Column(Text)
    replaced_by_code_id = Column(UUID(as_uuid=True),
                                 ForeignKey("cost_codes.id", ondelete="SET NULL"))
    display_order = Column(Integer, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("prefix", "sequence", name="uq_cost_codes_prefix_sequence"),
    )


class CostCodeSubcategory(Base):
    __tablename__ = "cost_code_subcategories"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cost_code_id = Column(UUID(as_uuid=True),
                          ForeignKey("cost_codes.id", ondelete="RESTRICT"),
                          nullable=False)
    code = Column(String(15), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    default_unit = Column(_e(SUBCAT_UNITS, "cost_code_subcat_unit"))
    display_order = Column(Integer, nullable=False)
    status = Column(_e(COST_CODE_STATUSES, "cost_code_status"),
                    nullable=False, default="Active")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CostCodeEntityMapping(Base):
    __tablename__ = "cost_code_entity_mapping"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cost_code_id = Column(UUID(as_uuid=True),
                          ForeignKey("cost_codes.id", ondelete="CASCADE"),
                          nullable=False)
    entity_id = Column(UUID(as_uuid=True),
                       ForeignKey("entities.id", ondelete="CASCADE"),
                       nullable=False)
    is_allowed = Column(Boolean, nullable=False, default=True)
    xero_nominal_code_override = Column(String(10))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("cost_code_id", "entity_id", name="uq_cost_code_entity_mapping"),
    )


class ProjectCostCode(Base):
    __tablename__ = "project_cost_codes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True),
                        ForeignKey("projects.id", ondelete="CASCADE"),
                        nullable=False)
    cost_code_id = Column(UUID(as_uuid=True),
                          ForeignKey("cost_codes.id", ondelete="RESTRICT"),
                          nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    project_override_name = Column(String(255))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "cost_code_id", name="uq_project_cost_codes"),
    )
