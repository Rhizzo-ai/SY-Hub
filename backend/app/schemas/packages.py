"""Pydantic schemas for B88 Pack 3 — Packages.

Request bodies for the packages router. Response bodies are JSON dicts
built by `services.packages.serialise_*`; we don't constrain those
with pydantic models because they vary with `view_sensitive` gating
(redacted vs full).

All Decimal-coercible fields are accepted as `str` for max client
fidelity (the service Decimal-quantizes per column scale).
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, Field


class PackageCreateBody(BaseModel):
    budget_id: uuid.UUID
    title: str = Field(..., max_length=200)
    kind: str = Field(..., max_length=20)  # 'labour' | 'materials'
    description: Optional[str] = None


class PackageUpdateBody(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None

    model_config = {"extra": "forbid"}


class PackageLineCreateBody(BaseModel):
    budget_line_id: uuid.UUID
    description: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = Field(None, max_length=20)
    budgeted_unit_rate: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "forbid"}


class PackageLineUpdateBody(BaseModel):
    description: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = Field(None, max_length=20)
    budgeted_unit_rate: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "forbid"}


class CancelBody(BaseModel):
    reason: Optional[str] = None

    model_config = {"extra": "forbid"}


class InviteBidderBody(BaseModel):
    supplier_id: uuid.UUID

    model_config = {"extra": "forbid"}


class BidLineInput(BaseModel):
    package_line_id: uuid.UUID
    quoted_unit_rate: str

    model_config = {"extra": "forbid"}


class EnterBidBody(BaseModel):
    lines: List[BidLineInput]
    notes: Optional[str] = None

    model_config = {"extra": "forbid"}


class AwardLineInput(BaseModel):
    package_line_id: uuid.UUID
    quantity: str
    awarded_unit_rate: str

    model_config = {"extra": "forbid"}


class AwardSpec(BaseModel):
    supplier_id: uuid.UUID
    source_bid_id: Optional[uuid.UUID] = None
    lines: List[AwardLineInput]
    # Optional downstream-create hints.
    required_by_date: Optional[str] = None
    delivery_address: Optional[str] = None
    retention_pct: Optional[str] = None
    cis_applies: Optional[bool] = None
    scope_description: Optional[str] = None

    model_config = {"extra": "forbid"}


class AwardBody(BaseModel):
    awards: List[AwardSpec]

    model_config = {"extra": "forbid"}


class CancelAwardBody(BaseModel):
    reason: str

    model_config = {"extra": "forbid"}
