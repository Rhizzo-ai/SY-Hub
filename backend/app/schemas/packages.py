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
    # B105/B106 — Cost-code-first commercial line model (mirrors
    # POLineCreate). A line names `cost_code_id` (+ optional
    # `cost_code_subcategory_id`); the service resolves whether the
    # code already has a budget line (allocate) or mints one (the
    # unbudgeted path). `budget_line_id` remains accepted as a
    # validated back-compat alias. The legacy `unbudgeted*` cluster
    # stays as DEPRECATED accepted-but-ignored fields used only as
    # fallbacks for the cost code, with a one-shot deprecation
    # warning at the service layer.
    #
    # Package lines REQUIRE quantity + budgeted_unit_rate up front
    # (unlike PO drafts) because the package is the tender estimate
    # — there is no "fill it in later" stage for a package line; a
    # zero qty/rate would silently net to £0 via
    # _inherit_from_budget_line. The PO submit completeness gate
    # (§3.8) is PO-scoped and does NOT apply here.
    cost_code_id: Optional[uuid.UUID] = None
    cost_code_subcategory_id: Optional[uuid.UUID] = None
    budget_line_id: Optional[uuid.UUID] = None
    # DEPRECATED — accept-but-ignore (see services.packages).
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
    def _require_resolvable_cost_code(self):
        """B105/B106 — same resolve-or-derive rules as POLineCreate.

        Cost code source priority (applied at the service layer):
          1. `cost_code_id`.
          2. `budget_line_id` alone → server derives the code.
          3. Deprecated `unbudgeted_cost_code_id`.
          4. None of the above → 422.

        Package lines additionally require explicit `quantity` +
        `budgeted_unit_rate` whenever the line resolves to a freshly
        minted £0 unbudgeted line (otherwise inherit defaults to £0).
        The service enforces that downstream check; here we only
        enforce the cost-code resolvability.
        """
        cc = self.cost_code_id or self.unbudgeted_cost_code_id
        if cc is None and self.budget_line_id is None:
            raise ValueError("cost_code_id is required")
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
