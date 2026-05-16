"""Pydantic request schemas for the Actuals API — Prompt 2.5A / Chat 19A.

Strict mode (extra='forbid') matches the budgets module convention.

Schemas are REQUEST-ONLY. Response bodies are built ad-hoc inside the router
via `_serialise_actual` etc., letting us conditionally omit fields and
attach computed values.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- Create / Update --------------------------------------------

class CreateActualRequest(BaseModel):
    """Create a Draft actual. gross_amount auto-computed = net + vat."""
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    budget_line_id: uuid.UUID
    entity_id: uuid.UUID
    source_type: str
    source_reference: Optional[str] = Field(default=None, max_length=10_000)
    external_id: Optional[str] = Field(default=None, max_length=255)

    transaction_date: date
    posting_date: Optional[date] = None
    description: str = Field(min_length=1, max_length=10_000)

    net_amount: Decimal
    vat_amount: Decimal = Decimal("0")
    vat_rate_pct: Decimal = Decimal("20")
    is_vat_recoverable: bool = True
    currency: str = Field(default="GBP", min_length=3, max_length=3)
    exchange_rate: Optional[Decimal] = None

    supplier_id: Optional[uuid.UUID] = None
    supplier_name_snapshot: str = Field(min_length=1, max_length=255)
    supplier_invoice_ref: Optional[str] = Field(default=None, max_length=100)

    is_cis_applicable: bool = False
    cis_deduction_rate_pct: Optional[Decimal] = None
    cis_labour_amount: Optional[Decimal] = None
    cis_materials_amount: Optional[Decimal] = None

    retention_rate_pct: Optional[Decimal] = None
    retention_amount: Optional[Decimal] = None

    linked_commitment_id: Optional[uuid.UUID] = None
    related_subcontract_id: Optional[uuid.UUID] = None

    @field_validator("net_amount", "vat_amount")
    @classmethod
    def _money_two_dp(cls, v: Decimal) -> Decimal:
        # quantize to 2dp; reject more than 2dp to keep DB-side numeric(14,2) clean.
        if v is None:
            return v
        if v.as_tuple().exponent < -2:
            raise ValueError("amount must have at most 2 decimal places")
        return v


class UpdateDraftActualRequest(BaseModel):
    """Edit a Draft actual. Posted+ rows can ONLY have specific endpoints called."""
    model_config = ConfigDict(extra="forbid")

    budget_line_id: Optional[uuid.UUID] = None
    entity_id: Optional[uuid.UUID] = None
    source_type: Optional[str] = None
    source_reference: Optional[str] = Field(default=None, max_length=10_000)
    external_id: Optional[str] = Field(default=None, max_length=255)

    transaction_date: Optional[date] = None
    description: Optional[str] = Field(default=None, min_length=1, max_length=10_000)

    net_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    vat_rate_pct: Optional[Decimal] = None
    is_vat_recoverable: Optional[bool] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    exchange_rate: Optional[Decimal] = None

    supplier_id: Optional[uuid.UUID] = None
    supplier_name_snapshot: Optional[str] = Field(default=None, max_length=255)
    supplier_invoice_ref: Optional[str] = Field(default=None, max_length=100)

    is_cis_applicable: Optional[bool] = None
    cis_deduction_rate_pct: Optional[Decimal] = None
    cis_labour_amount: Optional[Decimal] = None
    cis_materials_amount: Optional[Decimal] = None

    retention_rate_pct: Optional[Decimal] = None
    retention_amount: Optional[Decimal] = None

    linked_commitment_id: Optional[uuid.UUID] = None
    related_subcontract_id: Optional[uuid.UUID] = None


# ---------- Status transitions -----------------------------------------

class PostActualRequest(BaseModel):
    """Draft -> Posted. No body fields required; endpoint just records the actor."""
    model_config = ConfigDict(extra="forbid")
    notes: Optional[str] = Field(default=None, max_length=10_000)


class MarkPaidRequest(BaseModel):
    """Posted -> Paid. Requires payment_reference + paid_date."""
    model_config = ConfigDict(extra="forbid")
    paid_date: date
    payment_reference: str = Field(min_length=1, max_length=100)


class VoidActualRequest(BaseModel):
    """Any non-terminal -> Void. Requires a non-empty reason for audit."""
    model_config = ConfigDict(extra="forbid")
    void_reason: str = Field(min_length=3, max_length=10_000)


class DisputeActualRequest(BaseModel):
    """Posted -> Disputed."""
    model_config = ConfigDict(extra="forbid")
    dispute_reason: str = Field(min_length=3, max_length=10_000)


class UndisputeActualRequest(BaseModel):
    """Disputed -> Posted."""
    model_config = ConfigDict(extra="forbid")
    notes: Optional[str] = Field(default=None, max_length=10_000)


class ReleaseRetentionRequest(BaseModel):
    """Mark retention as released. Idempotent: noop if already released."""
    model_config = ConfigDict(extra="forbid")
    retention_release_date: date


# ---------- List filters -----------------------------------------------

class ActualsListFilters(BaseModel):
    """Query-string parsing helper. Mounted as Depends() in the router."""
    model_config = ConfigDict(extra="forbid")

    project_id: Optional[uuid.UUID] = None
    budget_line_id: Optional[uuid.UUID] = None
    entity_id: Optional[uuid.UUID] = None
    status: Optional[str] = None  # Comma-separated allowed: "Posted,Disputed"
    source_type: Optional[str] = None
    supplier_id: Optional[uuid.UUID] = None
    transaction_date_from: Optional[date] = None
    transaction_date_to: Optional[date] = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid = {"Draft", "Posted", "Paid", "Disputed", "Void"}
        parts = [s.strip() for s in v.split(",") if s.strip()]
        if not parts:
            return None
        bad = [p for p in parts if p not in valid]
        if bad:
            raise ValueError(f"invalid status value(s): {bad}; allowed: {sorted(valid)}")
        return ",".join(parts)


# ---------- AI capture ---------------------------------------------------

class PromoteCaptureToActualRequest(BaseModel):
    """Convert a Completed AICaptureJob into a Draft actual.

    Operator overrides whatever the AI suggested (entity/project/cost_code/etc.)
    The job's extracted_data is used as the seed for the new actual but every
    field may be overridden in this request.
    """
    model_config = ConfigDict(extra="forbid")

    project_id: uuid.UUID
    budget_line_id: uuid.UUID
    entity_id: uuid.UUID
    transaction_date: date
    description: str = Field(min_length=1, max_length=10_000)
    net_amount: Decimal
    vat_amount: Decimal = Decimal("0")
    vat_rate_pct: Decimal = Decimal("20")
    supplier_name_snapshot: str = Field(min_length=1, max_length=255)
    supplier_invoice_ref: Optional[str] = Field(default=None, max_length=100)
    is_cis_applicable: bool = False
    cis_deduction_rate_pct: Optional[Decimal] = None
    cis_labour_amount: Optional[Decimal] = None
    cis_materials_amount: Optional[Decimal] = None
    retention_rate_pct: Optional[Decimal] = None
    retention_amount: Optional[Decimal] = None


class DiscardCaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=10_000)


class RetryCaptureRequest(BaseModel):
    """Retry a Failed job. Resets attempts? No — leaves the counter for audit."""
    model_config = ConfigDict(extra="forbid")
