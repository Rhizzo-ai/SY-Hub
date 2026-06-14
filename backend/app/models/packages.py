"""ORM models for B88 Pack 3 — Packages (the tendering spine).

Pattern α tenant scoping: `packages` carries denormalised `tenant_id`
(mirrors purchase_orders / subcontracts); child tables resolve tenant
via the parent.

State machines:
  package_status:     draft → out_to_tender → partially_awarded → awarded
                      draft/out_to_tender/partially_awarded → cancelled
  package_bid_status: invited → received → (declined | withdrawn)
  package_award_status: active → cancelled

All money columns are Numeric(14, 2); quantities/rates Numeric(14, 4).
Server-side service is the single writer of cached totals (total_net,
awarded_net, bid total_net, awarded_net per award).
"""
from __future__ import annotations

import uuid
from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, UUID
from sqlalchemy.orm import relationship

from app.db import Base


PACKAGE_KINDS = ("materials", "subcontract", "consultant")
PACKAGE_STATUSES = (
    "draft", "out_to_tender", "partially_awarded", "awarded", "cancelled",
)
PACKAGE_BID_STATUSES = ("invited", "received", "declined", "withdrawn")
PACKAGE_AWARD_STATUSES = ("active", "cancelled")

# PG enum bindings — `create_type=False` because the migration owns DDL.
_package_kind_enum = PGEnum(
    *PACKAGE_KINDS, name="package_kind", create_type=False,
)
_package_status_enum = PGEnum(
    *PACKAGE_STATUSES, name="package_status", create_type=False,
)
_package_bid_status_enum = PGEnum(
    *PACKAGE_BID_STATUSES, name="package_bid_status", create_type=False,
)
_package_award_status_enum = PGEnum(
    *PACKAGE_AWARD_STATUSES, name="package_award_status", create_type=False,
)

# Service-side terminal sets.
TERMINAL_PACKAGE_STATUSES = frozenset({"awarded", "cancelled"})
LINES_FROZEN_STATUSES = frozenset({
    "out_to_tender", "partially_awarded", "awarded", "cancelled",
})


class Package(Base):
    __tablename__ = "packages"

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
    budget_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reference = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    # Enum values enforced both by PG enum + named CHECK in migration 0047.
    kind = Column(_package_kind_enum, nullable=False)
    status = Column(_package_status_enum, nullable=False, default="draft")
    description = Column(Text, nullable=True)
    total_net = Column(Numeric(14, 2), nullable=False, default=0)
    awarded_net = Column(Numeric(14, 2), nullable=False, default=0)
    out_to_tender_at = Column(DateTime(timezone=True), nullable=True)
    out_to_tender_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    awarded_at = Column(DateTime(timezone=True), nullable=True)
    awarded_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cancelled_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    lines = relationship(
        "PackageLine", back_populates="package",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="PackageLine.line_number",
    )
    bids = relationship(
        "PackageBid", back_populates="package",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    awards = relationship(
        "PackageAward", back_populates="package",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "reference", name="uq_packages_project_reference",
        ),
        Index("ix_packages_tenant_id", "tenant_id"),
        Index("ix_packages_project_status", "project_id", "status"),
    )


class PackageLine(Base):
    __tablename__ = "package_lines"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    package_id = Column(
        UUID(as_uuid=True),
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    budget_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("budget_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cost_code = Column(String(20), nullable=False)
    line_number = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    quantity = Column(Numeric(14, 4), nullable=False, default=1)
    unit = Column(String(20), nullable=True)
    budgeted_unit_rate = Column(Numeric(14, 4), nullable=False)
    budgeted_net_amount = Column(Numeric(14, 2), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    package = relationship("Package", back_populates="lines")
    bid_lines = relationship(
        "PackageBidLine", back_populates="package_line",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    award_lines = relationship(
        "PackageAwardLine", back_populates="package_line",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "package_id", "budget_line_id",
            name="uq_package_lines_package_budget_line",
        ),
        UniqueConstraint(
            "package_id", "line_number",
            name="uq_package_lines_package_line_number",
        ),
        Index("ix_package_lines_package_id", "package_id"),
        Index("ix_package_lines_budget_line_id", "budget_line_id"),
    )


class PackageBid(Base):
    __tablename__ = "package_bids"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    package_id = Column(
        UUID(as_uuid=True),
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    supplier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status = Column(_package_bid_status_enum, nullable=False, default="invited")
    total_net = Column(Numeric(14, 2), nullable=False, default=0)
    received_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    package = relationship("Package", back_populates="bids")
    bid_lines = relationship(
        "PackageBidLine", back_populates="bid",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "package_id", "supplier_id",
            name="uq_package_bids_package_supplier",
        ),
        Index("ix_package_bids_package_id", "package_id"),
        Index("ix_package_bids_supplier_id", "supplier_id"),
    )


class PackageBidLine(Base):
    __tablename__ = "package_bid_lines"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    package_bid_id = Column(
        UUID(as_uuid=True),
        ForeignKey("package_bids.id", ondelete="CASCADE"),
        nullable=False,
    )
    package_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("package_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    quoted_unit_rate = Column(Numeric(14, 4), nullable=False)
    quoted_net_amount = Column(Numeric(14, 2), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    bid = relationship("PackageBid", back_populates="bid_lines")
    package_line = relationship("PackageLine", back_populates="bid_lines")

    __table_args__ = (
        UniqueConstraint(
            "package_bid_id", "package_line_id",
            name="uq_package_bid_lines_bid_line",
        ),
        Index("ix_package_bid_lines_bid_id", "package_bid_id"),
    )


class PackageAward(Base):
    __tablename__ = "package_awards"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    package_id = Column(
        UUID(as_uuid=True),
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    supplier_id = Column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_bid_id = Column(
        UUID(as_uuid=True),
        ForeignKey("package_bids.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(_package_award_status_enum, nullable=False, default="active")
    awarded_net = Column(Numeric(14, 2), nullable=False)
    created_purchase_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_subcontract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subcontracts.id", ondelete="SET NULL"),
        nullable=True,
    )
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    cancelled_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    package = relationship("Package", back_populates="awards")
    award_lines = relationship(
        "PackageAwardLine", back_populates="award",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "(status <> 'active') OR ("
            " (created_purchase_order_id IS NOT NULL"
            "  AND created_subcontract_id IS NULL)"
            " OR ("
            "  created_purchase_order_id IS NULL"
            "  AND created_subcontract_id IS NOT NULL)"
            ")",
            name="ck_package_awards_one_downstream",
        ),
        Index("ix_package_awards_package_id", "package_id"),
    )


class PackageAwardLine(Base):
    __tablename__ = "package_award_lines"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    package_award_id = Column(
        UUID(as_uuid=True),
        ForeignKey("package_awards.id", ondelete="CASCADE"),
        nullable=False,
    )
    package_line_id = Column(
        UUID(as_uuid=True),
        ForeignKey("package_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity = Column(Numeric(14, 4), nullable=False)
    awarded_unit_rate = Column(Numeric(14, 4), nullable=False)
    awarded_net = Column(Numeric(14, 2), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    award = relationship("PackageAward", back_populates="award_lines")
    package_line = relationship("PackageLine", back_populates="award_lines")

    __table_args__ = (
        UniqueConstraint(
            "package_award_id", "package_line_id",
            name="uq_package_award_lines_award_line",
        ),
        Index("ix_package_award_lines_award_id", "package_award_id"),
        Index("ix_package_award_lines_package_line_id", "package_line_id"),
    )
