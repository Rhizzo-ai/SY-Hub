"""ORM models — Chat 35 §R1 (Prompt 2.8b).

Subcontract valuations (cumulative JCT certification chain) + Payment /
PayLess notices + Retention releases.

State machine — `subcontract_valuations.status`:
  Draft → Submitted → Certified  (Certified is terminal; the actual
  posts at certify-time).
  Draft|Submitted → Rejected (terminal).

State machine — `payment_notices.notice_type`:
  Payment  — auto-created on certify (snapshot of certified figures).
  PayLess  — manually issued against a Certified valuation
             (JCT withhold-notice).

`retention_releases` types (each releasable ONCE per subcontract):
  PC   — Practical Completion release.
  DLP  — Defects Liability Period end release.
"""
from __future__ import annotations

import uuid
from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index,
    Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base


VALUATION_STATUSES = ("Draft", "Submitted", "Certified", "Rejected")
TERMINAL_VALUATION_STATUSES = frozenset({"Certified", "Rejected"})

NOTICE_TYPES = ("Payment", "PayLess")

RETENTION_RELEASE_TYPES = ("PC", "DLP")


class SubcontractValuation(Base):
    """Cumulative JCT valuation against a subcontract."""

    __tablename__ = "subcontract_valuations"

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
        ForeignKey("subcontracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reference = Column(String(30), nullable=False)
    valuation_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="Draft")

    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)

    gross_applied_to_date = Column(Numeric(14, 2), nullable=False, default=0)
    gross_this_cert = Column(Numeric(14, 2), nullable=False, default=0)
    labour_portion = Column(Numeric(14, 2), nullable=False, default=0)
    materials_portion = Column(Numeric(14, 2), nullable=False, default=0)

    # Snapshots stored at certification — never recomputed afterwards.
    previous_certified_net = Column(Numeric(14, 2), nullable=True)
    retention_rate_pct = Column(Numeric(5, 2), nullable=True)
    retention_this_cert = Column(Numeric(14, 2), nullable=True)
    cis_rate_pct = Column(Numeric(5, 2), nullable=True)
    cis_deduction_this_cert = Column(Numeric(14, 2), nullable=True)
    net_payable_this_cert = Column(Numeric(14, 2), nullable=True)

    over_claim_flag = Column(Boolean, nullable=False, default=False)
    over_claim_note = Column(Text, nullable=True)

    posted_actual_id = Column(
        UUID(as_uuid=True),
        ForeignKey("actuals.id", ondelete="SET NULL"),
        nullable=True,
    )

    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    certified_at = Column(DateTime(timezone=True), nullable=True)
    certified_by = Column(
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

    payment_notices = relationship(
        "PaymentNotice", back_populates="valuation",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="PaymentNotice.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('Draft','Submitted','Certified','Rejected')",
            name="ck_subcontract_valuations_status",
        ),
        UniqueConstraint(
            "subcontract_id", "reference",
            name="uq_subcontract_valuations_ref",
        ),
        UniqueConstraint(
            "subcontract_id", "valuation_number",
            name="uq_subcontract_valuations_number",
        ),
        Index(
            "ix_subcontract_valuations_subcontract_number",
            "subcontract_id", "valuation_number",
        ),
        Index("ix_subcontract_valuations_tenant_id", "tenant_id"),
    )


class PaymentNotice(Base):
    """Payment notice (auto on certify) OR PayLess notice (manual)."""

    __tablename__ = "payment_notices"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subcontract_valuation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subcontract_valuations.id", ondelete="CASCADE"),
        nullable=False,
    )
    reference = Column(String(30), nullable=False)
    notice_type = Column(String(20), nullable=False, default="Payment")

    gross_certified = Column(Numeric(14, 2), nullable=False, default=0)
    retention = Column(Numeric(14, 2), nullable=False, default=0)
    cis_deducted = Column(Numeric(14, 2), nullable=False, default=0)
    net_due = Column(Numeric(14, 2), nullable=False, default=0)
    due_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)

    issued_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    issued_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    valuation = relationship(
        "SubcontractValuation", back_populates="payment_notices",
    )

    __table_args__ = (
        CheckConstraint(
            "notice_type IN ('Payment','PayLess')",
            name="ck_payment_notices_type",
        ),
        Index("ix_payment_notices_valuation_id", "subcontract_valuation_id"),
        Index("ix_payment_notices_tenant_id", "tenant_id"),
    )


class RetentionRelease(Base):
    """PC or DLP retention release event."""

    __tablename__ = "retention_releases"

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
        ForeignKey("subcontracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    release_type = Column(String(10), nullable=False)
    release_pct = Column(Numeric(5, 2), nullable=False, default=50)
    amount_released = Column(Numeric(14, 2), nullable=False, default=0)
    released_on = Column(Date, nullable=False)
    released_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    posted_actual_id = Column(
        UUID(as_uuid=True),
        ForeignKey("actuals.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes = Column(Text, nullable=True)
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

    __table_args__ = (
        CheckConstraint(
            "release_type IN ('PC','DLP')",
            name="ck_retention_releases_type",
        ),
        UniqueConstraint(
            "subcontract_id", "release_type",
            name="uq_retention_releases_subcontract_type",
        ),
        Index("ix_retention_releases_subcontract_id", "subcontract_id"),
        Index("ix_retention_releases_tenant_id", "tenant_id"),
    )
