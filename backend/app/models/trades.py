"""Trade model — tenant-scoped managed vocabulary (Chat 41 §R2 / 2.7-BE-rev-A).

A `Trade` is a named category (e.g. "Groundworks", "Electrical") attached
optionally to a supplier. Operator-managed, grow-as-you-type: a typed
trade that doesn't yet exist is created on the fly (case-insensitive
uniqueness per tenant). Trades are archived (not hard-deleted) to preserve
referential meaning of historic `supplier.trade_id` values.

Schema lives in migration 0040_contact_book_rework; this module just
declares the SQLAlchemy mapping.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)

    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )

    # Audit columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False,
    )
