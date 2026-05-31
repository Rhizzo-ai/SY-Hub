"""ORM models for Budget Change Requests (BCRs) — Chat 33 §R1 (Prompt 2.6).

Workflow that writes `budget_lines.approved_changes`. Three live types:
  - Transfer            (move £ between two lines, net-zero)
  - ContingencyDrawdown (move £ out of a contingency line, net-zero)
  - Adjustment          (increase/decrease a single line; non-net-zero)

Pattern note: although the rest of the budgets stack uses Pattern α
(no tenant_id columns; scope via project_id resolution), these tables
DO carry a denormalised `tenant_id` per Build Pack 2.6 §R1.2, matching
the `purchase_orders.tenant_id` precedent (Chat 24 R2). The service layer
still resolves visibility via the parent budget's project_id; the
column exists for list-time tenant filtering and audit forensics.

`source_variation_id` is a nullable stub — 2.8 will add the FK to
`subcontract_variations` and the BCR-generation path. No FK constraint
yet; documented in migration 0036 docstring.
"""
from __future__ import annotations

import uuid
from sqlalchemy import (
    Column, String, ForeignKey, DateTime, Numeric, Text, Index, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base


# State machine. Status_Change audit events surface the transition.
BUDGET_CHANGE_STATUSES = (
    "Draft", "Submitted", "Approved", "Applied",
    "Rejected", "Withdrawn",
)
TERMINAL_BCR_STATUSES = frozenset({"Applied", "Rejected", "Withdrawn"})

BUDGET_CHANGE_TYPES = ("Transfer", "ContingencyDrawdown", "Adjustment")


class BudgetChange(Base):
    """The Budget Change Request (BCR) header."""

    __tablename__ = "budget_changes"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
    )
    reference = Column(String(30), nullable=False)
    change_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="Draft")
    title = Column(String(200), nullable=False)
    reason = Column(Text, nullable=True)
    # Signed total budget delta (sum of detail-line deltas). 0 for
    # Transfer/ContingencyDrawdown; non-zero for Adjustment.
    net_impact = Column(Numeric(14, 2), nullable=False, default=0)
    # 2.8 stub — NO FK yet.
    source_variation_id = Column(UUID(as_uuid=True), nullable=True)

    # Workflow stamps.
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_at = Column(DateTime(timezone=True), nullable=True)
    applied_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    budget = relationship("Budget")
    lines = relationship(
        "BudgetChangeLine", back_populates="budget_change",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="BudgetChangeLine.created_at",
    )

    __table_args__ = (
        Index("ix_budget_changes_budget_status", "budget_id", "status"),
        Index("ix_budget_changes_tenant_id", "tenant_id"),
    )


class BudgetChangeLine(Base):
    """Per-budget-line £ delta applied by a BCR on apply."""

    __tablename__ = "budget_change_lines"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    budget_change_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budget_changes.id", ondelete="CASCADE"),
        nullable=False,
    )
    budget_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budget_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Signed £ applied to budget_line.approved_changes on apply.
    delta = Column(Numeric(14, 2), nullable=False)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    budget_change = relationship("BudgetChange", back_populates="lines")
    budget_line = relationship("BudgetLine")

    __table_args__ = (
        Index("ix_budget_change_lines_change_id", "budget_change_id"),
    )
