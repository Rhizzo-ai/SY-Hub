"""Subcontractor CIS verification model — append-only HMRC verification log.

Chat 32 §R1 (Prompt 2.7). Schema lives in migration 0035_subcontractors;
this module just declares the SQLAlchemy mapping.

Append-only: no `updated_at`, no soft-delete, no UPDATE path on the API.
A correction is a NEW verification row. The denormalised
`suppliers.current_cis_status` cache is repointed to the new row by the
service on insert.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# App-level constants — these are enforced by service-layer validators
# and a DB CHECK constraint (see migration 0035).
CIS_MATCH_STATUSES = ("Gross", "Net", "Unmatched")


class SubcontractorCISVerification(Base):
    __tablename__ = "subcontractor_cis_verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
    )

    verification_number: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    match_status: Mapped[str] = mapped_column(String(20), nullable=False)
    tax_rate_pct: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True,
    )
    verified_on: Mapped[date] = mapped_column(Date, nullable=False)
    expires_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False,
    )
