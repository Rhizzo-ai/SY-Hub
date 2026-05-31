"""ORM models for Budgets Core (Prompt 2.4A).

Phase 1 brief lines 2711-2958 is canonical.

Pattern alpha tenant scoping — NO tenant_id columns on budgets or budget_lines.
Scope is enforced via project_id resolution + _visible_project_ids() in services.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    Column, String, Boolean, Integer, ForeignKey, DateTime, Numeric, Text,
    Enum as SAEnum, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base

# Enum value lists — kept in lockstep with migration 0024_budgets.
BUDGET_STATUSES = ("Draft", "Active", "Locked", "Superseded", "Closed")
FTC_METHODS = ("Manual", "Budget_Remaining", "Committed_Only", "Percentage_Complete")
VARIANCE_STATUSES = ("Green", "Amber", "Red")

# Service-side terminal set — once a budget is here, lines/items are read-only
# in 2.4A. Future prompts may relax (super-admin override), out of scope now.
TERMINAL_BUDGET_STATUSES = frozenset({"Superseded", "Closed"})
# Statuses where line/item edits are blocked (Locked is reversible via unlock
# but still freezes lines while locked).
LINE_FROZEN_BUDGET_STATUSES = frozenset({"Locked", "Superseded", "Closed"})


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_appraisal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("appraisals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version_number = Column(Integer, nullable=False, default=1)
    version_label = Column(String(50), nullable=False, default="Original")
    is_current = Column(Boolean, nullable=False, default=True)
    status = Column(
        SAEnum(*BUDGET_STATUSES, name="budget_status", create_type=False),
        nullable=False, default="Draft",
    )
    created_from_appraisal_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    total_budget = Column(Numeric(14, 2), nullable=False, default=0)
    total_actuals = Column(Numeric(14, 2), nullable=False, default=0)
    total_committed_not_invoiced = Column(Numeric(14, 2), nullable=False, default=0)
    total_forecast_to_complete = Column(Numeric(14, 2), nullable=False, default=0)
    forecast_final_cost = Column(Numeric(14, 2), nullable=False, default=0)
    variance_vs_budget = Column(Numeric(14, 2), nullable=False, default=0)
    variance_pct = Column(Numeric(6, 3), nullable=False, default=0)
    summary_refreshed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    project = relationship("Project")
    source_appraisal = relationship("Appraisal")
    lines = relationship(
        "BudgetLine", back_populates="budget",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class BudgetLine(Base):
    __tablename__ = "budget_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
    )
    cost_code_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cost_codes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cost_code_subcategory_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cost_code_subcategories.id", ondelete="RESTRICT"),
        nullable=True,
    )
    line_description = Column(String(255), nullable=False)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="RESTRICT"),
        nullable=False,
    )

    original_budget = Column(Numeric(14, 2), nullable=False, default=0)
    approved_changes = Column(Numeric(14, 2), nullable=False, default=0)
    current_budget = Column(Numeric(14, 2), nullable=False, default=0)
    actuals_to_date = Column(Numeric(14, 2), nullable=False, default=0)
    actuals_this_period = Column(Numeric(14, 2), default=0)
    last_actual_posted_at = Column(DateTime(timezone=True), nullable=True)
    committed_value = Column(Numeric(14, 2), nullable=False, default=0)
    invoiced_against_commitment = Column(Numeric(14, 2), nullable=False, default=0)
    committed_not_invoiced = Column(Numeric(14, 2), nullable=False, default=0)
    forecast_to_complete = Column(Numeric(14, 2), nullable=False, default=0)
    ftc_method = Column(
        SAEnum(*FTC_METHODS, name="budget_line_ftc_method", create_type=False),
        nullable=False, default="Budget_Remaining",
    )
    forecast_final_cost = Column(Numeric(14, 2), nullable=False, default=0)
    variance_value = Column(Numeric(14, 2), nullable=False, default=0)
    variance_pct = Column(Numeric(6, 3), nullable=False, default=0)
    variance_status = Column(
        SAEnum(*VARIANCE_STATUSES, name="budget_line_variance_status",
               create_type=False),
        nullable=False, default="Green",
    )
    percentage_complete = Column(Numeric(5, 2), default=0)
    # Programme integration — FK constraint added in Prompt 3.2 (B7 locked).
    linked_programme_task_id = Column(UUID(as_uuid=True), nullable=True)
    is_locked = Column(Boolean, nullable=False, default=False)
    requires_attention = Column(Boolean, nullable=False, default=False)
    # Chat 33 §R1.1 (Prompt 2.6) — flag a budget line as a contingency
    # reserve. ContingencyDrawdown BCRs validate the source line has
    # `is_contingency = true`. Default false; backfilled false in
    # migration 0036.
    is_contingency = Column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    display_order = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    budget = relationship("Budget", back_populates="lines")
    cost_code = relationship("CostCode")
    cost_code_subcategory = relationship("CostCodeSubcategory")
    entity = relationship("Entity")
    items = relationship(
        "BudgetLineItem", back_populates="line",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="BudgetLineItem.display_order",
    )

    __table_args__ = (
        UniqueConstraint(
            "budget_id", "cost_code_id", "cost_code_subcategory_id",
            name="uq_budget_lines_budget_cost_subcat",
        ),
    )


class BudgetLineItem(Base):
    __tablename__ = "budget_line_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budget_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    description = Column(String(255), nullable=False)
    quantity = Column(Numeric(14, 4), nullable=True)
    unit = Column(String(20), nullable=True)
    rate = Column(Numeric(14, 4), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    notes = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    line = relationship("BudgetLine", back_populates="items")
