"""Supplier model — tenant-scoped supplier contact book.

Chat 24 §R1 (Prompt 2.5) — initial supplier directory.
Chat 32 §R1 (Prompt 2.7) — added supplier_type / CIS extension.
Chat 41 §R2 (Prompt 2.7-BE-rev-A) — Contact-Book rework:
  - `supplier_type` repurposed to a 4-value contact-type label
    (Contractor / Supplier / Consultant / Other). CIS / subcontract
    behavioural gates key off 'Contractor'.
  - `cis_subtype` and `default_vat_rate` dropped.
  - `vat_registered` was added in 0040 then dropped in 0041 per operator
    decision (Chat 41 §R-eyeball-Step2A). "Has a VAT number" is the
    de-facto registered signal; Xero owns VAT logic. Removed cleanly,
    no dead column.
  - `trade_id` FK to tenant-scoped `trades` table added; populated via
    grow-as-you-type. Joined relationship loaded eagerly to avoid N+1
    when serialising a page.

Sensitive fields (banking + vat/company numbers) are gated at the
serialisation layer via `suppliers.view_sensitive`; the DB does not
encrypt them — that's Track 7 work.

Schema lives in migrations 0029_suppliers_prefixes (base table),
0035_subcontractors (supplier_type / CIS columns) and
0040_contact_book_rework (contact-book rework); this module just
declares the SQLAlchemy mapping.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, text,
)
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.trades import Trade


CIS_STATUSES = ("gross", "net_20", "net_30", "not_registered")
SUPPLIER_CIS_STATUSES = CIS_STATUSES  # Public alias (avoid clash with entity-level CIS_STATUSES on import)

# Chat 41 §R2 (Prompt 2.7-BE-rev-A) — repurposed from a 2-value
# Supplier/Subcontractor split into a 4-value contact-type label.
# CIS / subcontract behavioural gates key off 'Contractor' (was
# 'Subcontractor' in 2.7).
SUPPLIER_TYPES = ("Contractor", "Supplier", "Consultant", "Other")
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

    # Chat 32 §R1 (Prompt 2.7) — CIS extension fields.
    # Chat 41 §R2 — `supplier_type` now a 4-value contact-type label.
    # supplier_type: PG enum 'supplier_type'. Defaults to 'Supplier'.
    # 'Contractor' is the CIS subcontractor type (gates record CIS
    # verifications + subcontract creation off this value).
    supplier_type: Mapped[str] = mapped_column(
        PG_ENUM("Contractor", "Supplier", "Consultant", "Other",
                name="supplier_type", create_type=False),
        nullable=False,
        server_default=text("'Supplier'::supplier_type"),
    )
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

    # Chat 41 §R2 — Trade (tenant-scoped managed vocabulary).
    # Optional. ON DELETE SET NULL preserves the supplier when a trade is
    # hard-deleted (we don't expose hard-delete; archived trades simply
    # stop appearing in pick lists).
    trade_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trades.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    # Eager-loaded one-directional relationship. lazy="joined" issues a
    # LEFT OUTER JOIN (trade_id is nullable) and avoids N+1 when
    # serialising a paginated supplier list (≤500 rows per page).
    # No `back_populates`: Trade has no `suppliers` collection in rev-A.
    trade: Mapped[Optional["Trade"]] = relationship(
        "Trade", lazy="joined",
    )

    # Banking (sensitive)
    bank_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bank_account_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    bank_sort_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Commercial defaults
    payment_terms_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default=text("30"),
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
