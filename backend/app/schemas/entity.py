"""Pydantic schemas for the Entities API."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.entity import (
    ENTITY_TYPES,
    VAT_SCHEMES,
    VAT_RETURN_PERIODS,
    CIS_STATUSES,
    ENTITY_STATUSES,
)

EntityType = Literal[ENTITY_TYPES]  # type: ignore[valid-type]
VatScheme = Literal[VAT_SCHEMES]  # type: ignore[valid-type]
VatReturnPeriod = Literal[VAT_RETURN_PERIODS]  # type: ignore[valid-type]
CisStatus = Literal[CIS_STATUSES]  # type: ignore[valid-type]
EntityStatus = Literal[ENTITY_STATUSES]  # type: ignore[valid-type]


_CH_RE = re.compile(r"^[A-Z0-9]{8}$")
_VAT_DIGITS_RE = re.compile(r"^\d{9,12}$")
_YEAR_END_RE = re.compile(r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")
_BANK_ACC_RE = re.compile(r"^\d{8}$")
_CCY_RE = re.compile(r"^[A-Z]{3}$")


class EntityBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    legal_name: str = Field(..., min_length=1, max_length=255)
    entity_type: EntityType
    parent_entity_id: Optional[uuid.UUID] = None
    companies_house_number: Optional[str] = Field(default=None, max_length=10)
    vat_number: Optional[str] = Field(default=None, max_length=15)
    vat_scheme: VatScheme = "Standard_Quarterly"
    vat_return_period: VatReturnPeriod = "Mar_Jun_Sep_Dec"
    utr: Optional[str] = Field(default=None, max_length=13)
    cis_status: Optional[CisStatus] = "None"
    registered_address: str = Field(..., min_length=1)
    trading_address: Optional[str] = None
    default_currency: str = Field(default="GBP", min_length=3, max_length=3)
    incorporation_date: Optional[date] = None
    year_end: Optional[str] = Field(default=None, max_length=5)
    el_insurance_expires: Optional[date] = None
    pl_insurance_expires: Optional[date] = None
    pi_insurance_expires: Optional[date] = None
    all_risks_insurance_expires: Optional[date] = None
    bank_name: Optional[str] = Field(default=None, max_length=255)
    bank_account_name: Optional[str] = Field(default=None, max_length=255)
    # Accept full 8-digit account number; router extracts last 4 before storing.
    bank_account_number: Optional[str] = Field(default=None, max_length=8)
    status: EntityStatus = "Active"
    notes: Optional[str] = None

    @field_validator("companies_house_number")
    @classmethod
    def _ch(cls, v):
        if v is None or v == "":
            return None
        v = v.strip().upper()
        if not _CH_RE.match(v):
            raise ValueError(
                "companies_house_number must be 8 alphanumeric characters"
            )
        return v

    @field_validator("vat_number")
    @classmethod
    def _vat(cls, v):
        if v is None or v == "":
            return None
        digits = re.sub(r"\D", "", v)
        if not _VAT_DIGITS_RE.match(digits):
            raise ValueError("vat_number must contain 9-12 digits")
        return digits

    @field_validator("year_end")
    @classmethod
    def _year_end(cls, v):
        if v is None or v == "":
            return None
        if not _YEAR_END_RE.match(v):
            raise ValueError("year_end must be in MM-DD format, e.g. 03-31")
        return v

    @field_validator("default_currency")
    @classmethod
    def _ccy(cls, v):
        v = v.strip().upper()
        if not _CCY_RE.match(v):
            raise ValueError("default_currency must be a 3-letter ISO code")
        return v

    @field_validator("bank_account_number")
    @classmethod
    def _bank(cls, v):
        if v is None or v == "":
            return None
        digits = re.sub(r"\D", "", v)
        if not _BANK_ACC_RE.match(digits):
            raise ValueError("bank_account_number must be 8 digits")
        return digits


class EntityCreate(EntityBase):
    pass


class EntityUpdate(BaseModel):
    """Partial update — all fields optional, same validators."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    legal_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    entity_type: Optional[EntityType] = None
    parent_entity_id: Optional[uuid.UUID] = None
    unset_parent: bool = False  # set true to explicitly null out parent
    companies_house_number: Optional[str] = Field(default=None, max_length=10)
    vat_number: Optional[str] = Field(default=None, max_length=15)
    vat_scheme: Optional[VatScheme] = None
    vat_return_period: Optional[VatReturnPeriod] = None
    utr: Optional[str] = Field(default=None, max_length=13)
    cis_status: Optional[CisStatus] = None
    registered_address: Optional[str] = Field(default=None, min_length=1)
    trading_address: Optional[str] = None
    default_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    incorporation_date: Optional[date] = None
    year_end: Optional[str] = Field(default=None, max_length=5)
    el_insurance_expires: Optional[date] = None
    pl_insurance_expires: Optional[date] = None
    pi_insurance_expires: Optional[date] = None
    all_risks_insurance_expires: Optional[date] = None
    bank_name: Optional[str] = Field(default=None, max_length=255)
    bank_account_name: Optional[str] = Field(default=None, max_length=255)
    bank_account_number: Optional[str] = Field(default=None, max_length=8)
    status: Optional[EntityStatus] = None
    notes: Optional[str] = None

    # Re-use validators
    _ch = field_validator("companies_house_number")(EntityBase._ch.__func__)  # type: ignore[attr-defined]
    _vat = field_validator("vat_number")(EntityBase._vat.__func__)  # type: ignore[attr-defined]
    _year_end = field_validator("year_end")(EntityBase._year_end.__func__)  # type: ignore[attr-defined]
    _ccy = field_validator("default_currency")(EntityBase._ccy.__func__)  # type: ignore[attr-defined]
    _bank = field_validator("bank_account_number")(EntityBase._bank.__func__)  # type: ignore[attr-defined]


class EntitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    legal_name: str
    entity_type: str
    status: str
    companies_house_number: Optional[str] = None
    vat_number: Optional[str] = None
    year_end: Optional[str] = None


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    legal_name: str
    entity_type: str
    parent_entity_id: Optional[uuid.UUID] = None
    companies_house_number: Optional[str] = None
    vat_number: Optional[str] = None
    vat_scheme: str
    vat_return_period: str
    utr: Optional[str] = None
    cis_status: Optional[str] = None
    registered_address: str
    trading_address: Optional[str] = None
    xero_org_id: Optional[str] = None
    xero_org_name: Optional[str] = None
    default_currency: str
    incorporation_date: Optional[date] = None
    year_end: Optional[str] = None
    el_insurance_expires: Optional[date] = None
    pl_insurance_expires: Optional[date] = None
    pi_insurance_expires: Optional[date] = None
    all_risks_insurance_expires: Optional[date] = None
    bank_name: Optional[str] = None
    bank_account_name: Optional[str] = None
    bank_account_number_masked: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EntityDetail(EntityRead):
    """Detail view adds parent summary + children list."""

    parent: Optional[EntitySummary] = None
    children: list[EntitySummary] = Field(default_factory=list)


class EntityListResponse(BaseModel):
    items: list[EntityRead]
    total: int
    page: int
    page_size: int


class InsuranceAlert(BaseModel):
    entity_id: uuid.UUID
    entity_name: str
    policy: Literal["EL", "PL", "PI", "All_Risks"]
    expires_on: date
    days_until_expiry: int
    severity: Literal["expired", "critical", "warning", "upcoming"]
