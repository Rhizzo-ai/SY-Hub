"""Purchase Order Receipts ORM — Chat 24 §R4 (Prompt 2.5).

Receipts capture physical delivery of PO lines. Money side
(committed_value / actuals) is NOT touched here; commitments are
governed by the R3 status-change trigger and bills land in a later
chat.

The DB trigger trg_pol_receipted_qty (migration 0033) keeps
purchase_order_lines.receipted_quantity in sync with the SUM of
quantity_received across all receipt lines for that PO line.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String,
    Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class PurchaseOrderReceipt(Base):
    __tablename__ = "purchase_order_receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    delivery_note_reference: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
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

    lines = relationship(
        "PurchaseOrderReceiptLine", back_populates="receipt",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    photos = relationship(
        "PurchaseOrderReceiptPhoto", back_populates="receipt",
        cascade="all, delete-orphan", passive_deletes=True,
    )


class PurchaseOrderReceiptLine(Base):
    __tablename__ = "purchase_order_receipt_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_order_receipts.id", ondelete="CASCADE"),
        nullable=False,
    )
    po_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_received: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    receipt = relationship("PurchaseOrderReceipt", back_populates="lines")

    __table_args__ = (
        CheckConstraint(
            "quantity_received > 0", name="ck_porl_quantity_positive",
        ),
    )


class PurchaseOrderReceiptPhoto(Base):
    __tablename__ = "purchase_order_receipt_photos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_order_receipts.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    receipt = relationship("PurchaseOrderReceipt", back_populates="photos")

    __table_args__ = (
        CheckConstraint(
            "file_size_bytes > 0", name="ck_porp_size_positive",
        ),
        UniqueConstraint(
            "receipt_id", "file_path", name="ux_porp_receipt_file_path",
        ),
    )
