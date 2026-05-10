"""Pydantic schemas for the Budgets API (Prompt 2.4A).

Strict mode: every model rejects unknown keys via `extra='forbid'`. This is
deliberate — silently dropping unknown fields would mask client bugs.

Schemas are **request-only**. Response bodies are built ad-hoc inside the
router via `_serialise_*` helpers; this matches the appraisals router
convention and lets us cleanly omit `view_sensitive` keys when the caller
lacks the permission (omit, not nullify).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- Budget header ----------------------------------------------

class CreateBudgetFromAppraisalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_appraisal_id: uuid.UUID
    notes: Optional[str] = Field(default=None, max_length=10_000)


class CreateNewVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_label: str = Field(min_length=1, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=10_000)


# ---------- Lines -------------------------------------------------------

class UpdateBudgetLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_description: Optional[str] = Field(default=None, max_length=255)
    ftc_method: Optional[str] = None
    forecast_to_complete: Optional[Decimal] = None
    percentage_complete: Optional[Decimal] = None
    notes: Optional[str] = None
    original_budget: Optional[Decimal] = None


# ---------- Items -------------------------------------------------------

class CreateBudgetLineItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=255)
    amount: Decimal
    quantity: Optional[Decimal] = None
    unit: Optional[str] = Field(default=None, max_length=20)
    rate: Optional[Decimal] = None
    notes: Optional[str] = None


class UpdateBudgetLineItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: Optional[str] = Field(default=None, max_length=255)
    quantity: Optional[Decimal] = None
    unit: Optional[str] = Field(default=None, max_length=20)
    rate: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    notes: Optional[str] = None
    display_order: Optional[int] = None


# ---------- Bulk reorder (Prompt 2.4A.1) --------------------------------

class ReorderBudgetLinesRequest(BaseModel):
    """Body for POST /budget-lines/reorder.

    Must contain every line on the budget exactly once, in the new desired
    order. The service performs a single-transaction atomic rewrite of
    display_order on each line. See services.budget_lines.bulk_reorder_lines.
    """
    model_config = ConfigDict(extra="forbid")
    budget_id: uuid.UUID
    ordered_line_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
