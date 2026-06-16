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

from pydantic import BaseModel, Field, model_validator


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
    # B102 — Unbudgeted-Order Handling. `budget_line_id` is optional at
    # the schema level; XOR'd against `unbudgeted=true` by the after-
    # validator. An unbudgeted package line MUST also carry an explicit
    # quantity + budgeted_unit_rate — the £0 auto-line we'd otherwise
    # inherit from would net the package line to zero (see
    # _inherit_from_budget_line for a £0 source).
    budget_line_id: Optional[uuid.UUID] = None
    unbudgeted: bool = False
    unbudgeted_cost_code_id: Optional[uuid.UUID] = None
    unbudgeted_subcategory_id: Optional[uuid.UUID] = None
    unbudgeted_reason: Optional[str] = Field(None, max_length=2000)
    description: Optional[str] = None
    quantity: Optional[str] = None
    unit: Optional[str] = Field(None, max_length=20)
    budgeted_unit_rate: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _xor_budget_line(self):
        """B102 XOR — exactly one of {budget_line_id, unbudgeted=true};
        unbudgeted leg also demands explicit qty + rate so the line
        doesn't silently net to £0 via _inherit_from_budget_line."""
        if self.unbudgeted:
            if self.budget_line_id is not None:
                raise ValueError(
                    "a line cannot be both unbudgeted and carry a budget_line_id"
                )
            if self.unbudgeted_cost_code_id is None:
                raise ValueError(
                    "unbudgeted_cost_code_id is required for an unbudgeted line"
                )
            if not (self.unbudgeted_reason and self.unbudgeted_reason.strip()):
                raise ValueError(
                    "unbudgeted_reason is required for an unbudgeted line"
                )
            if self.quantity is None or self.budgeted_unit_rate is None:
                raise ValueError(
                    "unbudgeted package lines require explicit quantity "
                    "and budgeted_unit_rate"
                )
        else:
            if self.budget_line_id is None:
                raise ValueError(
                    "budget_line_id is required unless unbudgeted=true"
                )
        return self


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
