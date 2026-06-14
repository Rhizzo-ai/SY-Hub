"""ORM models for Subcontracts & Variations — Chat 34 §R1 (Prompt 2.8a).

Subcontracts wrap a subcontractor (LD2 — `suppliers.supplier_type='Subcontractor'`).
A subcontract may optionally link a Purchase Order on the same project +
subcontractor (LD1, service-guarded with warn-not-block sum
reconciliation).

State machine:
  Draft → Active → Completed   (+ Terminated terminal from any state)

Variations belong to one subcontract. State machine:
  Raised → Costed → Approved → Issued
  Raised|Costed → Rejected / Withdrawn (terminal)

`source_variation_id` on `budget_changes` (existing 2.6 stub column)
now carries an actual FK to `subcontract_variations.id`, populated when
a variation is approved with `cost_treatment='BudgetChange'` and the
service calls the EXISTING `services.budget_changes.create_bcr(...)`.
The generated BCR is a normal Draft BCR with its own approve/apply
lifecycle — it is NOT auto-applied (LD3).
"""
from __future__ import annotations

import uuid
from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index,
    Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base


# Subcontract state machine values. Status_Change audit events surface
# the transition.
SUBCONTRACT_STATUSES = ("Draft", "Active", "Completed", "Terminated")
TERMINAL_SUBCONTRACT_STATUSES = frozenset({"Completed", "Terminated"})

# Variation state machine values.
VARIATION_STATUSES = (
    "Raised", "Costed", "Approved", "Issued", "Rejected", "Withdrawn",
)
TERMINAL_VARIATION_STATUSES = frozenset(
    {"Issued", "Rejected", "Withdrawn"}
)

# Cost treatment options for an approved variation (LD3/LD4).
COST_TREATMENTS = ("WithinContractSum", "BudgetChange")


class Subcontract(Base):
    """The Subcontract header (LD1 + LD2)."""

    __tablename__ = "subcontracts"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subcontractor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # LD1 — nullable + service-guarded.
    purchase_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Pack 3.5 — bidirectional link to the originating package (NULL =
    # standalone subcontract; SET NULL on package delete so deleting a
    # package never cascade-destroys a real financial subcontract).
    package_id = Column(
        UUID(as_uuid=True),
        ForeignKey("packages.id", ondelete="SET NULL"),
        nullable=True,
    )

    reference = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    scope_description = Column(Text, nullable=True)

    status = Column(String(20), nullable=False, default="Draft")
    original_contract_sum = Column(Numeric(14, 2), nullable=False, default=0)
    current_contract_sum = Column(Numeric(14, 2), nullable=False, default=0)

    # Stored now, USED by 2.8b.
    retention_pct = Column(Numeric(5, 2), nullable=False, default=0)
    cis_applies = Column(Boolean, nullable=False, default=True)

    start_on = Column(Date, nullable=True)
    end_on = Column(Date, nullable=True)
    signed_at = Column(DateTime(timezone=True), nullable=True)
    signed_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    po_reconciliation_note = Column(Text, nullable=True)

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

    variations = relationship(
        "SubcontractVariation", back_populates="subcontract",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="SubcontractVariation.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('Draft','Active','Completed','Terminated')",
            name="ck_subcontracts_status",
        ),
        UniqueConstraint(
            "project_id", "reference",
            name="uq_subcontracts_project_reference",
        ),
        Index("ix_subcontracts_project_status", "project_id", "status"),
        Index("ix_subcontracts_tenant_id", "tenant_id"),
        Index("ix_subcontracts_subcontractor_id", "subcontractor_id"),
    )


class SubcontractVariation(Base):
    """Variation header — the raise/cost/approve/issue workflow."""

    __tablename__ = "subcontract_variations"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subcontract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subcontracts.id", ondelete="CASCADE"),
        nullable=False,
    )

    reference = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(String(20), nullable=False, default="Raised")
    estimated_value = Column(Numeric(14, 2), nullable=True)
    agreed_value = Column(Numeric(14, 2), nullable=True)
    cost_treatment = Column(String(20), nullable=True)

    # FK populated on approval when cost_treatment='BudgetChange'.
    generated_bcr_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budget_changes.id", ondelete="SET NULL"),
        nullable=True,
    )

    costed_at = Column(DateTime(timezone=True), nullable=True)
    costed_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    issued_at = Column(DateTime(timezone=True), nullable=True)
    issued_by = Column(
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

    subcontract = relationship("Subcontract", back_populates="variations")

    __table_args__ = (
        CheckConstraint(
            "status IN ('Raised','Costed','Approved','Issued',"
            "'Rejected','Withdrawn')",
            name="ck_subcontract_variations_status",
        ),
        CheckConstraint(
            "cost_treatment IS NULL OR cost_treatment IN "
            "('WithinContractSum','BudgetChange')",
            name="ck_subcontract_variations_cost_treatment",
        ),
        UniqueConstraint(
            "subcontract_id", "reference",
            name="uq_subcontract_variations_ref",
        ),
        Index(
            "ix_subcontract_variations_subcontract_status",
            "subcontract_id", "status",
        ),
        Index("ix_subcontract_variations_tenant_id", "tenant_id"),
    )
