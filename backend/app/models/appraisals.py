"""Appraisal models — Prompt 2.2.

Four tables that back the commercial appraisal engine:
- Appraisal                 (header + cached KPIs + RLV)
- AppraisalUnit             (unit mix)
- AppraisalCostLine         (cost lines with auto_source enum)
- AppraisalFinanceFacility  (debt / equity facilities)
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum as SAEnum, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db import Base


APPRAISAL_STATES = ("Draft", "Submitted", "Approved", "Rejected", "Superseded")
UNIT_TYPES = ("Detached", "Semi_Detached", "Terraced", "Flat", "Bungalow",
              "Commercial", "Other")
TENURE_TYPES = ("Open_Market", "Affordable_Rent", "Shared_Ownership",
                "Social_Rent", "Build_To_Rent", "Private_Rent")
AUTO_SOURCES = (
    "Manual",
    "Percentage_Of_GDV",
    "Percentage_Of_Build_Cost",
    "Percentage_Of_Land",
    "SDLT_Engine",
    "Finance_Engine",
    "RLV_Engine",
)
COST_CATEGORIES = ("Acquisition", "Construction", "Professional_Fees",
                   "Statutory", "Finance", "Contingency", "Sales", "Other")
FINANCE_TYPES = ("Debt", "Equity", "Mezzanine", "Grant")
INTEREST_MODES = ("Simple_Monthly", "Compound_Monthly", "Rolled_Up", "Serviced")


def _e(values, name):
    return SAEnum(*values, name=name, create_type=False, native_enum=True)


class Appraisal(Base):
    __tablename__ = "appraisals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True),
                        ForeignKey("projects.id", ondelete="CASCADE"),
                        nullable=False)
    version = Column(Integer, nullable=False, default=1)
    previous_version_id = Column(UUID(as_uuid=True),
                                 ForeignKey("appraisals.id", ondelete="SET NULL"))
    name = Column(String(255), nullable=False)
    state = Column(_e(APPRAISAL_STATES, "appraisal_state"),
                   nullable=False, default="Draft")
    reference_date = Column(Date, nullable=False)

    land_purchase_price = Column(Numeric(14, 2), nullable=False, default=0)
    sdlt_category = Column(String(40), nullable=False,
                           default="Residential_Standard")
    developer_relief = Column(Boolean, nullable=False, default=False)

    contingency_pct = Column(Numeric(6, 3), nullable=False, default=5)
    target_profit_on_cost_pct = Column(Numeric(6, 3), nullable=False, default=20)
    target_profit_on_gdv_pct = Column(Numeric(6, 3), nullable=False, default=17)
    project_duration_months = Column(Integer, nullable=False, default=18)

    total_gdv = Column(Numeric(14, 2), nullable=False, default=0)
    total_acquisition_cost = Column(Numeric(14, 2), nullable=False, default=0)
    total_build_cost = Column(Numeric(14, 2), nullable=False, default=0)
    total_professional_fees = Column(Numeric(14, 2), nullable=False, default=0)
    total_statutory_cost = Column(Numeric(14, 2), nullable=False, default=0)
    total_finance_cost = Column(Numeric(14, 2), nullable=False, default=0)
    total_contingency = Column(Numeric(14, 2), nullable=False, default=0)
    total_sales_cost = Column(Numeric(14, 2), nullable=False, default=0)
    total_other_cost = Column(Numeric(14, 2), nullable=False, default=0)
    total_cost = Column(Numeric(14, 2), nullable=False, default=0)
    total_profit = Column(Numeric(14, 2), nullable=False, default=0)
    profit_on_cost_pct = Column(Numeric(8, 4), nullable=False, default=0)
    profit_on_gdv_pct = Column(Numeric(8, 4), nullable=False, default=0)

    rlv_enabled = Column(Boolean, nullable=False, default=False)
    rlv_target_basis = Column(String(16), nullable=False, default="on_cost")
    rlv_target_value = Column(Numeric(6, 3), nullable=False, default=20)
    rlv_computed_land_value = Column(Numeric(14, 2))
    rlv_iterations = Column(Integer)
    rlv_converged = Column(Boolean)
    rlv_computed_at = Column(DateTime(timezone=True))

    submitted_by_user_id = Column(UUID(as_uuid=True),
                                  ForeignKey("users.id", ondelete="SET NULL"))
    submitted_at = Column(DateTime(timezone=True))
    approved_by_user_id = Column(UUID(as_uuid=True),
                                 ForeignKey("users.id", ondelete="SET NULL"))
    approved_at = Column(DateTime(timezone=True))
    rejection_reason = Column(Text)
    notes = Column(Text)
    computation_metadata = Column(JSONB, nullable=False, default=dict)
    is_stale = Column(Boolean, nullable=False, default=False)
    created_by_user_id = Column(UUID(as_uuid=True),
                                ForeignKey("users.id", ondelete="RESTRICT"),
                                nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "version",
                         name="uq_appraisals_project_version"),
    )

    units = relationship("AppraisalUnit", cascade="all, delete-orphan",
                         order_by="AppraisalUnit.display_order",
                         backref="appraisal")
    cost_lines = relationship("AppraisalCostLine", cascade="all, delete-orphan",
                              order_by="AppraisalCostLine.display_order",
                              backref="appraisal")
    finance_facilities = relationship(
        "AppraisalFinanceFacility", cascade="all, delete-orphan",
        order_by="AppraisalFinanceFacility.display_order",
        backref="appraisal",
    )


class AppraisalUnit(Base):
    __tablename__ = "appraisal_units"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appraisal_id = Column(UUID(as_uuid=True),
                          ForeignKey("appraisals.id", ondelete="CASCADE"),
                          nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    unit_label = Column(String(100), nullable=False)
    unit_type = Column(_e(UNIT_TYPES, "appraisal_unit_type"),
                       nullable=False, default="Detached")
    tenure = Column(_e(TENURE_TYPES, "appraisal_unit_tenure"),
                    nullable=False, default="Open_Market")
    quantity = Column(Integer, nullable=False, default=1)
    beds = Column(Integer)
    gia_sqm = Column(Numeric(10, 2))
    price_per_unit = Column(Numeric(14, 2), nullable=False, default=0)
    build_cost_per_unit = Column(Numeric(14, 2), nullable=False, default=0)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())


class AppraisalCostLine(Base):
    __tablename__ = "appraisal_cost_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appraisal_id = Column(UUID(as_uuid=True),
                          ForeignKey("appraisals.id", ondelete="CASCADE"),
                          nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    cost_code_id = Column(UUID(as_uuid=True),
                          ForeignKey("cost_codes.id", ondelete="RESTRICT"))
    label = Column(String(255), nullable=False)
    category = Column(_e(COST_CATEGORIES, "appraisal_cost_category"),
                      nullable=False, default="Other")
    auto_source = Column(_e(AUTO_SOURCES, "appraisal_cost_auto_source"),
                         nullable=False, default="Manual")
    percentage = Column(Numeric(8, 4))
    amount = Column(Numeric(14, 2), nullable=False, default=0)
    is_locked = Column(Boolean, nullable=False, default=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())


class AppraisalFinanceFacility(Base):
    __tablename__ = "appraisal_finance_model"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appraisal_id = Column(UUID(as_uuid=True),
                          ForeignKey("appraisals.id", ondelete="CASCADE"),
                          nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    label = Column(String(255), nullable=False)
    facility_type = Column(_e(FINANCE_TYPES, "appraisal_finance_type"),
                           nullable=False, default="Debt")
    principal_amount = Column(Numeric(14, 2), nullable=False, default=0)
    interest_rate_pct = Column(Numeric(6, 3), nullable=False, default=0)
    arrangement_fee_pct = Column(Numeric(6, 3), nullable=False, default=0)
    exit_fee_pct = Column(Numeric(6, 3), nullable=False, default=0)
    interest_mode = Column(_e(INTEREST_MODES, "appraisal_interest_mode"),
                           nullable=False, default="Simple_Monthly")
    drawn_from_month = Column(Integer, nullable=False, default=0)
    drawn_to_month = Column(Integer, nullable=False, default=18)
    total_interest = Column(Numeric(14, 2), nullable=False, default=0)
    total_fees = Column(Numeric(14, 2), nullable=False, default=0)
    total_finance_cost = Column(Numeric(14, 2), nullable=False, default=0)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
