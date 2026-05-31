"""Supplier model — tenant-scoped supplier directory.

Chat 24 §R1 (Prompt 2.5 — Purchase Orders, Suppliers & PO/Bill Numbering).
Suppliers are visible across all projects within a tenant; one row per
supplier per tenant. Portal-access fields (`portal_enabled`,
`portal_invite_token`, `portal_invite_sent_at`, `portal_last_login_at`)
are stubbed for Track 7 — they are inert in 2.5.

Sensitive fields (banking + vat/company numbers) are gated at the
serialisation layer via `suppliers.view_sensitive`; the DB does not
encrypt them — that's Track 7 work.

Schema lives in migration 0029_suppliers_prefixes; this module just
declares the SQLAlchemy mapping.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, text,
)
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


CIS_STATUSES = ("gross", "net_20", "net_30", "not_registered")
SUPPLIER_CIS_STATUSES = CIS_STATUSES  # Public alias (avoid clash with entity-level CIS_STATUSES on import)

# Chat 32 §R1 (Prompt 2.7) — supplier vs subcontractor discriminator.
SUPPLIER_TYPES = ("Supplier", "Subcontractor")
# Chat 32 §R1 (Prompt 2.7) — CIS subtype is app-constrained (not a DB enum).
CIS_SUBTYPES = ("Labour_Only", "Labour_And_Plant", "Supply_And_Fix")
# Chat 32 §R3 (Prompt 2.7) — denormalised cache of current verification.
CURRENT_CIS_STATUSES = ("Gross", "Net", "Unmatched", "Unverified")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trading_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Contact
    contact_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Address
    address_line1: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    address_line2: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postcode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, server_default="United Kingdom",
    )

    # Tax / registration
    vat_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    company_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    cis_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Chat 32 §R1 (Prompt 2.7) — subcontractor + CIS extension.
    # supplier_type: PG enum 'supplier_type'. Defaults to 'Supplier' so
    # existing rows backfill cleanly. A subcontractor IS a supplier row
    # with supplier_type='Subcontractor' (single-table inheritance pattern,
    # not a separate table).
    supplier_type: Mapped[str] = mapped_column(
        PG_ENUM("Supplier", "Subcontractor",
                name="supplier_type", create_type=False),
        nullable=False,
        server_default=text("'Supplier'::supplier_type"),
    )
    # cis_subtype is app-constrained (CIS_SUBTYPES); only meaningful when
    # supplier_type='Subcontractor'. NULL for plain suppliers.
    cis_subtype: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    cis_registered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    # utr: UK Unique Taxpayer Reference (10 digits). Sensitive PII; the
    # audit pipeline already redacts the field name via SENSITIVE_FIELDS.
    utr: Mapped[Optional[str]] = mapped_column(String(13), nullable=True)
    # current_cis_status: denormalised cache of the latest verification's
    # match status. Maintained ONLY by services/cis.record_verification();
    # never settable via the supplier create/update payload.
    current_cis_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Banking (sensitive)
    bank_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bank_account_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    bank_sort_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Commercial defaults
    payment_terms_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default=text("30"),
    )
    default_vat_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True, server_default=text("20.00"),
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Portal stubs (Track 7) — inert in 2.5
    portal_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    portal_invite_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    portal_invite_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    portal_last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Lifecycle
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    archived_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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
