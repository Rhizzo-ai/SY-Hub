"""PurchaseOrderApproval model — Chat 24 §R3 (Prompt 2.5)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, String, Text, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


PO_APPROVAL_RESOLUTIONS = ("approved", "rejected")


class PurchaseOrderApproval(Base):
    __tablename__ = "purchase_order_approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=text("now()"),
    )
    submission_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Mirrors the schema's `budget_snapshot jsonb NOT NULL`. We capture
    # this at submission time so the approver sees the snapshot of the
    # budget that triggered the over-budget gate, even if the underlying
    # budget moves before resolution.
    budget_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    resolution: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    purchase_order = relationship("PurchaseOrder")

    __table_args__ = (
        CheckConstraint(
            "(resolution IS NULL AND resolved_by IS NULL "
            "AND resolved_at IS NULL) OR "
            "(resolution IS NOT NULL AND resolved_by IS NOT NULL "
            "AND resolved_at IS NOT NULL)",
            name="ck_poa_resolution_consistency",
        ),
        CheckConstraint(
            "resolution != 'rejected' OR "
            "(resolution_notes IS NOT NULL AND length(trim(resolution_notes)) > 0)",
            name="ck_poa_reject_requires_notes",
        ),
    )
