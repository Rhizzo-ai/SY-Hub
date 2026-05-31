"""Subcontract variations router — Chat 34 §R4 (Prompt 2.8a).

Endpoints (mounted under /api/v1):
  POST   /subcontract-variations                        .create  → 201
  GET    /subcontract-variations?subcontract_id=&status .view
  GET    /subcontract-variations/{id}                   .view
  POST   /subcontract-variations/{id}/cost              .cost
  POST   /subcontract-variations/{id}/approve           .approve
  POST   /subcontract-variations/{id}/issue             .issue
  POST   /subcontract-variations/{id}/reject            .approve
  POST   /subcontract-variations/{id}/withdraw          .create

Error mapping:
  - VariationNotFoundError / SubcontractNotFoundError → 404
  - VariationStateError / SubcontractStateError       → 409
  - ValueError                                        → 422
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.user import User
from app.services import subcontract_variations as svc
from app.services.subcontract_variations import (
    VariationNotFoundError, VariationStateError,
)
from app.services.subcontracts import (
    SubcontractNotFoundError, SubcontractStateError,
)


router = APIRouter(tags=["subcontract_variations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VariationRaiseBody(BaseModel):
    subcontract_id: uuid.UUID
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    estimated_value: Optional[str] = None


class VariationCostBody(BaseModel):
    agreed_value: str


class VariationApproveBody(BaseModel):
    cost_treatment: str = Field(..., max_length=20)
    # Required when cost_treatment='BudgetChange'.
    target_budget_line_id: Optional[uuid.UUID] = None


class VariationRejectBody(BaseModel):
    reason: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, (VariationNotFoundError, SubcontractNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc) or "Not found")
    if isinstance(exc, (VariationStateError, SubcontractStateError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/subcontract-variations", status_code=201)
def raise_variation(
    body: VariationRaiseBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_variations.create")
    ),
    db: Session = Depends(get_db),
):
    try:
        v = svc.raise_variation(
            db,
            subcontract_id=body.subcontract_id,
            title=body.title,
            description=body.description,
            estimated_value=body.estimated_value,
            user=current, perms=perms, request=request,
        )
    except (
        SubcontractNotFoundError, SubcontractStateError,
        VariationNotFoundError, VariationStateError, ValueError,
    ) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(v)
    return svc.serialise(v)


@router.get("/subcontract-variations")
def list_variations(
    subcontract_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_variations.view")
    ),
    db: Session = Depends(get_db),
):
    try:
        rows = svc.list_variations(
            db, user=current, perms=perms,
            subcontract_id=subcontract_id, status=status,
            limit=limit, offset=offset,
        )
    except (
        SubcontractNotFoundError, VariationNotFoundError, ValueError,
    ) as exc:
        raise _map(exc)
    return {"items": [svc.serialise(r) for r in rows], "total": len(rows)}


@router.get("/subcontract-variations/{v_id}")
def get_variation(
    v_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_variations.view")
    ),
    db: Session = Depends(get_db),
):
    try:
        v = svc.get_variation(db, v_id, user=current, perms=perms)
    except (VariationNotFoundError, SubcontractNotFoundError) as exc:
        raise _map(exc)
    return svc.serialise(v)


def _do_transition(svc_fn, *, db, v_id, current, perms, request, **kwargs):
    try:
        v = svc_fn(
            db, v_id, user=current, perms=perms, request=request, **kwargs,
        )
    except (
        VariationNotFoundError, VariationStateError,
        SubcontractNotFoundError, SubcontractStateError, ValueError,
    ) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(v)
    return svc.serialise(v)


@router.post("/subcontract-variations/{v_id}/cost")
def cost_variation(
    v_id: uuid.UUID, body: VariationCostBody, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_variations.cost")
    ),
    db: Session = Depends(get_db),
):
    return _do_transition(
        svc.cost_variation,
        db=db, v_id=v_id, current=current, perms=perms, request=request,
        agreed_value=body.agreed_value,
    )


@router.post("/subcontract-variations/{v_id}/approve")
def approve_variation(
    v_id: uuid.UUID, body: VariationApproveBody, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_variations.approve")
    ),
    db: Session = Depends(get_db),
):
    return _do_transition(
        svc.approve_variation,
        db=db, v_id=v_id, current=current, perms=perms, request=request,
        cost_treatment=body.cost_treatment,
        target_budget_line_id=body.target_budget_line_id,
    )


@router.post("/subcontract-variations/{v_id}/issue")
def issue_variation(
    v_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_variations.issue")
    ),
    db: Session = Depends(get_db),
):
    return _do_transition(
        svc.issue_variation,
        db=db, v_id=v_id, current=current, perms=perms, request=request,
    )


@router.post("/subcontract-variations/{v_id}/reject")
def reject_variation(
    v_id: uuid.UUID, body: VariationRejectBody, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_variations.approve")
    ),
    db: Session = Depends(get_db),
):
    return _do_transition(
        svc.reject_variation,
        db=db, v_id=v_id, current=current, perms=perms, request=request,
        reason=body.reason,
    )


@router.post("/subcontract-variations/{v_id}/withdraw")
def withdraw_variation(
    v_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontract_variations.create")
    ),
    db: Session = Depends(get_db),
):
    return _do_transition(
        svc.withdraw_variation,
        db=db, v_id=v_id, current=current, perms=perms, request=request,
    )
