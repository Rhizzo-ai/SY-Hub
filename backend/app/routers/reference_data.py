"""Reference-data router — Prompt 2.1.

Mounts under /api/v1:
  - GET  /sdlt-rates                       list active bands, optionally by date
  - GET  /sdlt-rates/all                   list ALL bands (history) for admin UI
  - POST /sdlt-rates/calculate             diagnostic calc endpoint
  - POST /sdlt-rates/new-structure         version transition (admin)
  - GET  /appraisal-defaults               list current-tenant settings
  - PUT  /appraisal-defaults/{id}          update a single setting (admin)

Permissions:
  - GET endpoints: system_config.view
  - Write endpoints: system_config.admin
Permission gate is enforced server-side via `require_permission(...)`.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.reference_data import (
    APPRAISAL_SETTING_TYPES, AppraisalDefaultSetting,
    PROJECT_TYPES, SDLT_CATEGORIES, SdltRateBand,
)
from app.models.user import User
from app.services import reference_data as ref_svc
from app.services import sdlt as sdlt_svc


router = APIRouter(prefix="/reference-data", tags=["reference_data"])


# ----------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------

class SdltBandOut(BaseModel):
    id: str
    effective_from: str
    effective_to: Optional[str]
    category: str
    band_lower: str
    band_upper: Optional[str]
    rate_pct: str
    notes: Optional[str]


class SdltBandIn(BaseModel):
    band_lower: Decimal = Decimal("0")
    band_upper: Optional[Decimal] = None
    rate_pct: Decimal
    notes: Optional[str] = None


class SdltNewStructureIn(BaseModel):
    effective_from: date
    bands_by_category: dict[str, list[SdltBandIn]] = Field(
        ..., description="category → list of bands; only touched categories are rolled"
    )

    @validator("bands_by_category")
    def _categories_known(cls, v):
        for cat in v:
            if cat not in SDLT_CATEGORIES:
                raise ValueError(f"Unknown category: {cat!r}")
        if not v:
            raise ValueError("bands_by_category must not be empty")
        return v


class SdltCalcIn(BaseModel):
    consideration: Decimal
    category: str
    reference_date: Optional[date] = None


class AppraisalSettingOut(BaseModel):
    id: str
    setting_key: str
    setting_value: str
    setting_type: str
    applies_to_project_type: Optional[str]
    description: str
    updated_by_user_id: Optional[str]
    updated_at: str


class AppraisalSettingPutBody(BaseModel):
    value: Decimal
    description: Optional[str] = None


# ----------------------------------------------------------------------
# Serialisers
# ----------------------------------------------------------------------

def _sdlt_to_out(b: SdltRateBand) -> dict:
    return {
        "id": str(b.id),
        "effective_from": b.effective_from.isoformat(),
        "effective_to": b.effective_to.isoformat() if b.effective_to else None,
        "category": b.category,
        "band_lower": str(b.band_lower),
        "band_upper": str(b.band_upper) if b.band_upper is not None else None,
        "rate_pct": str(b.rate_pct),
        "notes": b.notes,
    }


def _setting_to_out(s: AppraisalDefaultSetting) -> dict:
    return {
        "id": str(s.id),
        "setting_key": s.setting_key,
        "setting_value": str(s.setting_value),
        "setting_type": s.setting_type,
        "applies_to_project_type": s.applies_to_project_type,
        "description": s.description,
        "updated_by_user_id":
            str(s.updated_by_user_id) if s.updated_by_user_id else None,
        "updated_at": s.updated_at.isoformat(),
    }


# ----------------------------------------------------------------------
# SDLT endpoints
# ----------------------------------------------------------------------

@router.get("/sdlt-rates")
def list_active_sdlt(
    as_of: Optional[date] = Query(None, description="defaults to today"),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.view")),
):
    """List SDLT bands active on `as_of` (today if omitted), grouped by category."""
    if category and category not in SDLT_CATEGORIES:
        raise HTTPException(400, f"Unknown category: {category}")
    cats = [category] if category else list(SDLT_CATEGORIES)
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for cat in cats:
        rows = sdlt_svc.get_active_bands(db, category=cat, reference_date=as_of)
        for r in rows:
            by_cat[cat].append(_sdlt_to_out(r))
    return {
        "as_of": (as_of or date.today()).isoformat(),
        "by_category": dict(by_cat),
    }


@router.get("/sdlt-rates/all")
def list_all_sdlt(
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.view")),
):
    """Full history — used by the admin UI date picker."""
    rows = db.scalars(
        select(SdltRateBand).order_by(
            SdltRateBand.category, SdltRateBand.effective_from.desc(),
            SdltRateBand.band_lower.asc(),
        )
    ).all()
    return {"items": [_sdlt_to_out(r) for r in rows], "count": len(rows)}


@router.post("/sdlt-rates/calculate")
def calc_sdlt(
    body: SdltCalcIn,
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.view")),
):
    if body.category not in SDLT_CATEGORIES:
        raise HTTPException(400, f"Unknown category: {body.category}")
    try:
        total = sdlt_svc.calculate(
            db,
            consideration=body.consideration,
            category=body.category,
            reference_date=body.reference_date,
        )
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "consideration": str(body.consideration),
        "category": body.category,
        "reference_date": (body.reference_date or date.today()).isoformat(),
        "sdlt": str(total),
    }


@router.post("/sdlt-rates/new-structure")
def new_sdlt_structure(
    body: SdltNewStructureIn,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.admin")),
):
    payload = {
        cat: [b.dict() for b in bands]
        for cat, bands in body.bands_by_category.items()
    }
    summary = ref_svc.create_sdlt_structure(
        db,
        effective_from=body.effective_from,
        bands_by_category=payload,
        actor_user_id=current.id,
        request=request,
    )
    db.commit()
    return summary


# ----------------------------------------------------------------------
# Appraisal defaults
# ----------------------------------------------------------------------

@router.get("/appraisal-defaults")
def list_settings(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.view")),
):
    """Current tenant's settings, grouped by applies_to_project_type
    (null → 'All types')."""
    rows = db.scalars(
        select(AppraisalDefaultSetting)
        .where(AppraisalDefaultSetting.tenant_id == current.tenant_id)
        .order_by(
            AppraisalDefaultSetting.applies_to_project_type.asc().nullsfirst(),
            AppraisalDefaultSetting.setting_key.asc(),
        )
    ).all()
    by_scope: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        key = r.applies_to_project_type or "All"
        by_scope[key].append(_setting_to_out(r))
    return {
        "tenant_id": str(current.tenant_id),
        "items": [_setting_to_out(r) for r in rows],
        "by_project_type": dict(by_scope),
        "count": len(rows),
    }


@router.put("/appraisal-defaults/{setting_id}")
def update_setting(
    setting_id: UUID,
    body: AppraisalSettingPutBody,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.admin")),
):
    try:
        row = ref_svc.update_appraisal_setting(
            db,
            setting_id=setting_id,
            new_value=body.value,
            new_description=body.description,
            actor_user_id=current.id,
            tenant_id=current.tenant_id,
            request=request,
        )
    except LookupError:
        raise HTTPException(404, "setting not found")
    db.commit()
    db.refresh(row)
    return _setting_to_out(row)
