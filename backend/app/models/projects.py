"""Projects + project team member models — Prompt 1.5."""
from __future__ import annotations

import uuid
from sqlalchemy import (
    Column, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base


PROJECT_TYPES = ("Pure_Dev", "Dev_Build", "DB_Contract", "JV", "Main_Contract")
LAND_OWNERSHIP = ("Direct_Purchase", "Option", "Conditional_Contract", "JV_Contribution", "Existing_Holding")
TENURES = ("Freehold", "Leasehold", "Long_Leasehold", "Option", "Conditional", "Other")
LAND_TYPES = ("Greenfield", "Brownfield", "Mixed", "Urban_Infill", "Garden_Land")
PLANNING_TYPES = ("Full", "Outline", "Reserved_Matters", "Hybrid", "Permitted_Dev", "Prior_Approval")
PLANNING_STATUSES = ("Pre_App", "Submitted", "Approved", "Refused", "Appeal", "Not_Required")
PROJECT_STAGES = (
    "Lead", "Appraisal", "Deal_Pipeline", "Planning", "Pre_Con",
    "Construction", "Sales", "Post_Completion", "Closed", "Dead",
)
PROJECT_STATUSES = ("Active", "On_Hold", "Dead", "Complete")
TEAM_ROLES = (
    "Project_Lead", "Contracts_Manager", "Site_Manager", "Quantity_Surveyor",
    "Designer", "Consultant", "Finance", "Sales", "Support",
)


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_code = Column(String(20), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    project_type = Column(Enum(*PROJECT_TYPES, name="project_type_enum", create_type=False), nullable=False)
    parent_project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"))
    primary_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False)
    construction_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="RESTRICT"))
    land_ownership_method = Column(Enum(*LAND_OWNERSHIP, name="land_ownership_enum", create_type=False), nullable=False)
    site_address = Column(Text, nullable=False)
    site_postcode = Column(String(10), nullable=False)
    local_authority = Column(String(100))
    site_area_ha = Column(Numeric(10, 4))
    site_area_acres = Column(Numeric(10, 4))
    tenure = Column(Enum(*TENURES, name="project_tenure_enum", create_type=False), nullable=False, default="Freehold")
    lease_years_remaining = Column(Integer)
    land_type = Column(Enum(*LAND_TYPES, name="land_type_enum", create_type=False))
    planning_ref = Column(String(50))
    planning_type = Column(Enum(*PLANNING_TYPES, name="planning_type_enum", create_type=False))
    planning_status = Column(Enum(*PLANNING_STATUSES, name="planning_status_enum", create_type=False))
    planning_approval_date = Column(Date)
    planning_expiry_date = Column(Date)
    implementation_required = Column(Boolean, nullable=False, default=True)
    s106_required = Column(Boolean, default=False)
    cil_required = Column(Boolean, default=False)
    vat_opt_to_tax = Column(Boolean, default=False)
    vat_opt_to_tax_date = Column(Date)
    units_target = Column(Integer)
    units_actual = Column(Integer)
    affordable_housing_pct = Column(Numeric(5, 2), default=0)
    target_start_date = Column(Date)
    target_pc_date = Column(Date)
    actual_start_date = Column(Date)
    actual_pc_date = Column(Date)
    current_stage = Column(Enum(*PROJECT_STAGES, name="project_stage_enum", create_type=False), nullable=False, default="Lead")
    stage_entered_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    status = Column(Enum(*PROJECT_STATUSES, name="project_status_enum", create_type=False), nullable=False, default="Active")
    dead_reason = Column(Text)
    gdv_actual = Column(Numeric(14, 2), default=0)
    build_cost_actual = Column(Numeric(14, 2), default=0)
    all_in_cost_actual = Column(Numeric(14, 2), default=0)
    profit_actual = Column(Numeric(14, 2), default=0)
    margin_actual_pct = Column(Numeric(6, 3), default=0)
    financials_refreshed_at = Column(DateTime(timezone=True))
    project_lead_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    primary_entity = relationship("Entity", foreign_keys=[primary_entity_id])
    construction_entity = relationship("Entity", foreign_keys=[construction_entity_id])
    project_lead = relationship("User", foreign_keys=[project_lead_user_id])


class ProjectTeamMember(Base):
    __tablename__ = "project_team_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    role_on_project = Column(Enum(*TEAM_ROLES, name="team_role_enum", create_type=False), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    assigned_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    removed_at = Column(DateTime(timezone=True))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])
