"""Entity model — Prompt 1.1.

Represents a legal entity within a tenant group: Parent, SPV, ConstructionCo,
JV vehicle, etc. Self-referential parent_entity_id.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import (
    Date,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin, uuid4


ENTITY_TYPES = ("Parent", "SPV", "ConstructionCo", "JV_Vehicle", "Other")
VAT_SCHEMES = (
    "Standard_Quarterly",
    "Standard_Monthly",
    "Cash_Accounting",
    "Flat_Rate",
    "Not_Registered",
)
VAT_RETURN_PERIODS = (
    "Jan_Apr_Jul_Oct",
    "Feb_May_Aug_Nov",
    "Mar_Jun_Sep_Dec",
    "Monthly",
)
CIS_STATUSES = ("Contractor", "Subcontractor", "Both", "None")
ENTITY_STATUSES = ("Active", "Dormant", "Struck_off")


entity_type_enum = SAEnum(
    *ENTITY_TYPES, name="entity_type", create_type=True
)
vat_scheme_enum = SAEnum(
    *VAT_SCHEMES, name="vat_scheme", create_type=True
)
vat_return_period_enum = SAEnum(
    *VAT_RETURN_PERIODS, name="vat_return_period", create_type=True
)
cis_status_enum = SAEnum(
    *CIS_STATUSES, name="cis_status", create_type=True
)
entity_status_enum = SAEnum(
    *ENTITY_STATUSES, name="entity_status", create_type=True
)


class Entity(Base, TimestampMixin):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(entity_type_enum, nullable=False)

    parent_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    companies_house_number: Mapped[Optional[str]] = mapped_column(String(10))
    vat_number: Mapped[Optional[str]] = mapped_column(String(15))
    vat_scheme: Mapped[str] = mapped_column(
        vat_scheme_enum,
        nullable=False,
        server_default=text("'Standard_Quarterly'::vat_scheme"),
    )
    vat_return_period: Mapped[str] = mapped_column(
        vat_return_period_enum,
        nullable=False,
        server_default=text("'Mar_Jun_Sep_Dec'::vat_return_period"),
    )

    utr: Mapped[Optional[str]] = mapped_column(String(13))
    cis_status: Mapped[Optional[str]] = mapped_column(
        cis_status_enum,
        server_default=text("'None'::cis_status"),
    )

    registered_address: Mapped[str] = mapped_column(Text, nullable=False)
    trading_address: Mapped[Optional[str]] = mapped_column(Text)

    xero_org_id: Mapped[Optional[str]] = mapped_column(String(100))
    xero_org_name: Mapped[Optional[str]] = mapped_column(String(255))

    default_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'GBP'")
    )

    incorporation_date: Mapped[Optional[date]] = mapped_column(Date)
    year_end: Mapped[Optional[str]] = mapped_column(String(5))

    el_insurance_expires: Mapped[Optional[date]] = mapped_column(Date)
    pl_insurance_expires: Mapped[Optional[date]] = mapped_column(Date)
    pi_insurance_expires: Mapped[Optional[date]] = mapped_column(Date)
    all_risks_insurance_expires: Mapped[Optional[date]] = mapped_column(Date)

    bank_name: Mapped[Optional[str]] = mapped_column(String(255))
    bank_account_name: Mapped[Optional[str]] = mapped_column(String(255))
    bank_account_number_masked: Mapped[Optional[str]] = mapped_column(String(10))

    status: Mapped[str] = mapped_column(
        entity_status_enum,
        nullable=False,
        server_default=text("'Active'::entity_status"),
    )

    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Added in Prompt 1.2 — tracks who created the entity
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    parent = relationship(
        "Entity",
        remote_side="Entity.id",
        foreign_keys=[parent_entity_id],
        lazy="joined",
        post_update=True,
    )

    __table_args__ = (
        Index(
            "uq_entities_companies_house_number",
            "tenant_id",
            "companies_house_number",
            unique=True,
            postgresql_where=text("companies_house_number IS NOT NULL"),
        ),
        Index(
            "uq_entities_vat_number",
            "tenant_id",
            "vat_number",
            unique=True,
            postgresql_where=text("vat_number IS NOT NULL"),
        ),
        Index(
            "ix_entities_type_status",
            "tenant_id",
            "entity_type",
            "status",
        ),
        Index(
            "ix_entities_xero_org_id",
            "xero_org_id",
            postgresql_where=text("xero_org_id IS NOT NULL"),
        ),
    )
