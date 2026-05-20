"""Purchase Order ORM models — Chat 24 §R2 (Prompt 2.5).

Pattern α tenant scoping — purchase_orders carries `tenant_id` AND
`project_id`. The `tenant_id` is denormalised so list-time tenant
filters can index without a project join; the project is the
ultimate authority for tenant-membership and visibility checks.

Approval / receipts are not modelled here — see R3 (0032) and R4
(0033 / future migration) for those columns + tables.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Computed, Date, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


PO_STATUSES = (
    "draft",
    "pending_approval",
    "approved",
    "issued",
    "partially_receipted",
    "receipted",
    "closed",
    "voided",
)

# Service-side helpers.
TERMINAL_PO_STATUSES = frozenset({"closed", "voided"})
ISSUED_OR_BEYOND_STATUSES = frozenset({
    "issued", "partially_receipted", "receipted", "closed",
})
HEADER_ANNOTATION_FIELDS = frozenset({
    "notes", "delivery_notes", "external_reference",
})


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    po_number: Mapped[str] = mapped_column(String(50), nullable=False)
    po_number_prefix_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_number_prefixes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    po_sequence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'draft'"),
    )

    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    required_by_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    delivery_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivery_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    subtotal_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0"),
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0"),
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0"),
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'GBP'"),
    )

    # Lifecycle stamps (most populated by R3/R4 — declared here so R2
    # state-machine code can null/clear them on void/close).
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    submitted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    approval_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issued_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    issued_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    closed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    closed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    voided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    voided_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    voided_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )

    lines = relationship(
        "PurchaseOrderLine", back_populates="purchase_order",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="PurchaseOrderLine.line_number",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "po_number", name="ux_po_tenant_number"),
        CheckConstraint("currency = 'GBP'", name="ck_po_currency_gbp"),
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    budget_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cost_code: Mapped[str] = mapped_column(String(20), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("1"),
    )
    unit: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("20.00"),
    )
    vat_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0"),
    )
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    receipted_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default=text("0"),
    )
    # The DB column is a GENERATED column; we mark it as read-only by
    # declaring `Computed(... persisted=True)`. SQLAlchemy excludes it
    # from INSERT/UPDATE statements and re-reads it on flush + refresh.
    is_fully_receipted: Mapped[bool] = mapped_column(
        Boolean,
        Computed("(receipted_quantity >= quantity)", persisted=True),
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )

    purchase_order = relationship("PurchaseOrder", back_populates="lines")
