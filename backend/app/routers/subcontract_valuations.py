"""Subcontract valuations router — Chat 35 §R4.1 (Prompt 2.8b).

Mounted under /api/v1 via `server.py`.

Endpoints:
  POST   /subcontract-valuations                          .create  → 201
  GET    /subcontract-valuations?subcontract_id=&status=  .view
  GET    /subcontract-valuations/{id}                     .view
  POST   /subcontract-valuations/{id}/submit              .create
  POST   /subcontract-valuations/{id}/certify             .certify
  POST   /subcontract-valuations/{id}/reject              .certify

Error mapping:
  - ValuationNotFoundError → 404 (cross-tenant or missing)
  - ValuationStateError    → 409 (bad workflow transition)
  - ValueError             → 422 (payload validation)
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.user import User
from app.services import subcontract_valuations as svc
from app.services.subcontract_valuations import (
    ValuationNotFoundError, ValuationStateError,
)


router = APIRouter(tags=["subcontract_valuations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ValuationCreateBody(BaseModel):
    subcontract_id: uuid.UUID
    gross_applied_to_date: str
    labour_portion: str = "0"
    materials_portion: str = "0"
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class ValuationCertifyBody(BaseModel):
    transaction_date: Optional[date] = None
    description: Optional[str] = Field(None, max_length=500)
    # Chat 39 §R2 A4: required. No silent LIMIT-1 guess on the project.
    # Caller MUST specify which budget line bears the subcontractor cost.
    budget_line_id: uuid.UUID


class ValuationRejectBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, ValuationNotFoundError):
        return HTTPException(status_code=404, detail=str(exc) or "Not found")
    if isinstance(exc, ValuationStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _serialise(v, *, perms: UserPermissions) -> dict[str, Any]:
    has_sensitive = perms.has("subcontract_valuations.view_sensitive")
    return svc.serialise(v, include_sensitive=has_sensitive)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/subcontract-valuations", status_code=201)
def create_valuation_endpoint(
    body: ValuationCreateBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_valuations.create")
    ),
    db: Session = Depends(get_db),
):
    try:
        v = svc.create_valuation(
            db,
            subcontract_id=body.subcontract_id,
            gross_applied_to_date=body.gross_applied_to_date,
            labour_portion=body.labour_portion,
            materials_portion=body.materials_portion,
            period_start=body.period_start,
            period_end=body.period_end,
            user=current, perms=perms, request=request,
        )
    except (ValuationNotFoundError, ValuationStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(v)
    return _serialise(v, perms=perms)


@router.get("/subcontract-valuations")
def list_valuations_endpoint(
    subcontract_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_valuations.view")
    ),
    db: Session = Depends(get_db),
):
    try:
        rows = svc.list_valuations(
            db, user=current, perms=perms,
            subcontract_id=subcontract_id, status=status,
            limit=limit, offset=offset,
        )
    except (ValuationNotFoundError, ValueError) as exc:
        raise _map(exc)
    items = [_serialise(r, perms=perms) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/subcontract-valuations/{val_id}")
def get_valuation_endpoint(
    val_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_valuations.view")
    ),
    db: Session = Depends(get_db),
):
    try:
        v = svc.get_valuation(db, val_id, user=current, perms=perms)
    except ValuationNotFoundError as exc:
        raise _map(exc)
    return _serialise(v, perms=perms)


@router.post("/subcontract-valuations/{val_id}/submit")
def submit_valuation_endpoint(
    val_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_valuations.create")
    ),
    db: Session = Depends(get_db),
):
    try:
        v = svc.submit_valuation(
            db, val_id, user=current, perms=perms, request=request,
        )
    except (ValuationNotFoundError, ValuationStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(v)
    return _serialise(v, perms=perms)


@router.post("/subcontract-valuations/{val_id}/certify")
def certify_valuation_endpoint(
    val_id: uuid.UUID,
    body: ValuationCertifyBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_valuations.certify")
    ),
    db: Session = Depends(get_db),
):
    try:
        v = svc.certify_valuation(
            db, val_id, user=current, perms=perms,
            transaction_date=body.transaction_date,
            description=body.description,
            budget_line_id=body.budget_line_id,
            request=request,
        )
    except (ValuationNotFoundError, ValuationStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(v)
    return _serialise(v, perms=perms)


@router.post("/subcontract-valuations/{val_id}/reject")
def reject_valuation_endpoint(
    val_id: uuid.UUID,
    body: ValuationRejectBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_valuations.certify")
    ),
    db: Session = Depends(get_db),
):
    try:
        v = svc.reject_valuation(
            db, val_id, user=current, perms=perms,
            reason=body.reason, request=request,
        )
    except (ValuationNotFoundError, ValuationStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(v)
    return _serialise(v, perms=perms)
