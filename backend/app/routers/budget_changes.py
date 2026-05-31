"""BCR router — Chat 33 §R4 (Prompt 2.6).

Mounted under /api/v1 (v1 prefix supplied at include time in server.py).

Endpoints:
  POST   /budget-changes                       budget_changes.create  → 201
  GET    /budget-changes?budget_id=&status=    budget_changes.view
  GET    /budget-changes/{id}                  budget_changes.view
  PATCH  /budget-changes/{id}                  budget_changes.edit    (Draft only)
  POST   /budget-changes/{id}/submit           budget_changes.submit
  POST   /budget-changes/{id}/approve          budget_changes.approve
  POST   /budget-changes/{id}/reject           budget_changes.approve
  POST   /budget-changes/{id}/withdraw         budget_changes.create
  POST   /budget-changes/{id}/apply            budget_changes.apply
  GET    /budgets/{budget_id}/change-log       budget_changes.view

Error mapping:
  - BudgetNotFoundError   → 404 (cross-tenant or missing)
  - BudgetStateError      → 409 (bad workflow transition / parent state)
  - BudgetSelfApprovalError → 403 (LD2 self-approval guard)
  - ValueError            → 422 (payload validation)
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.user import User
from app.services import budget_changes as svc
from app.services.budget_errors import (
    BudgetNotFoundError, BudgetSelfApprovalError, BudgetStateError,
)


router = APIRouter(tags=["budget_changes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BCRLineBody(BaseModel):
    budget_line_id: uuid.UUID
    delta: str  # decimal string


class BCRCreateBody(BaseModel):
    budget_id: uuid.UUID
    change_type: str = Field(..., max_length=20)
    title: str = Field(..., max_length=200)
    reason: Optional[str] = None
    source_variation_id: Optional[uuid.UUID] = None
    lines: list[BCRLineBody]


class BCRUpdateBody(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    reason: Optional[str] = None
    lines: Optional[list[BCRLineBody]] = None


class BCRRejectBody(BaseModel):
    reason: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, BudgetNotFoundError):
        return HTTPException(status_code=404, detail=str(exc) or "Not found")
    if isinstance(exc, BudgetSelfApprovalError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, BudgetStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/budget-changes", status_code=201)
def create_budget_change(
    body: BCRCreateBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.create")),
    db: Session = Depends(get_db),
):
    try:
        bcr = svc.create_bcr(
            db,
            budget_id=body.budget_id,
            change_type=body.change_type,
            title=body.title,
            reason=body.reason,
            lines=[ln.model_dump() for ln in body.lines],
            source_variation_id=body.source_variation_id,
            user=current, perms=perms,
            request=request,
        )
    except (BudgetNotFoundError, BudgetStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(bcr)
    return svc.serialise(bcr)


@router.get("/budget-changes")
def list_budget_changes(
    budget_id: uuid.UUID = Query(...),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = svc.list_bcrs(
            db, budget_id=budget_id, user=current, perms=perms,
            status=status, limit=limit, offset=offset,
        )
    except (BudgetNotFoundError, ValueError) as exc:
        raise _map(exc)
    return {"items": [svc.serialise(r) for r in rows], "total": len(rows)}


@router.get("/budget-changes/{bcr_id}")
def get_budget_change(
    bcr_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.view")),
    db: Session = Depends(get_db),
):
    try:
        bcr = svc.get_bcr(db, bcr_id=bcr_id, user=current, perms=perms)
    except BudgetNotFoundError as exc:
        raise _map(exc)
    return svc.serialise(bcr)


@router.patch("/budget-changes/{bcr_id}")
def update_budget_change(
    bcr_id: uuid.UUID,
    body: BCRUpdateBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.edit")),
    db: Session = Depends(get_db),
):
    try:
        bcr = svc.update_bcr(
            db, bcr_id=bcr_id, user=current, perms=perms,
            title=body.title, reason=body.reason,
            lines=([ln.model_dump() for ln in body.lines]
                   if body.lines is not None else None),
            request=request,
        )
    except (BudgetNotFoundError, BudgetStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(bcr)
    return svc.serialise(bcr)


def _do_transition(
    db: Session, request: Request, current: User, perms: UserPermissions,
    *, bcr_id: uuid.UUID, svc_fn, **kwargs,
) -> dict[str, Any]:
    try:
        bcr = svc_fn(
            db, bcr_id=bcr_id, user=current, perms=perms,
            request=request, **kwargs,
        )
    except (BudgetSelfApprovalError, BudgetStateError, BudgetNotFoundError,
            ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(bcr)
    return svc.serialise(bcr)


@router.post("/budget-changes/{bcr_id}/submit")
def submit_budget_change(
    bcr_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.submit")),
    db: Session = Depends(get_db),
):
    return _do_transition(
        db, request, current, perms,
        bcr_id=bcr_id, svc_fn=svc.submit_bcr,
    )


@router.post("/budget-changes/{bcr_id}/approve")
def approve_budget_change(
    bcr_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.approve")),
    db: Session = Depends(get_db),
):
    return _do_transition(
        db, request, current, perms,
        bcr_id=bcr_id, svc_fn=svc.approve_bcr,
    )


@router.post("/budget-changes/{bcr_id}/reject")
def reject_budget_change(
    bcr_id: uuid.UUID, body: BCRRejectBody, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.approve")),
    db: Session = Depends(get_db),
):
    return _do_transition(
        db, request, current, perms,
        bcr_id=bcr_id, svc_fn=svc.reject_bcr, reason=body.reason,
    )


@router.post("/budget-changes/{bcr_id}/withdraw")
def withdraw_budget_change(
    bcr_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.create")),
    db: Session = Depends(get_db),
):
    return _do_transition(
        db, request, current, perms,
        bcr_id=bcr_id, svc_fn=svc.withdraw_bcr,
    )


@router.post("/budget-changes/{bcr_id}/apply")
def apply_budget_change(
    bcr_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.apply")),
    db: Session = Depends(get_db),
):
    return _do_transition(
        db, request, current, perms,
        bcr_id=bcr_id, svc_fn=svc.apply_bcr,
    )


@router.get("/budgets/{budget_id}/change-log")
def budget_change_log(
    budget_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budget_changes.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = svc.change_log(
            db, budget_id=budget_id, user=current, perms=perms,
        )
    except BudgetNotFoundError as exc:
        raise _map(exc)
    return {"items": [svc.serialise(r) for r in rows], "total": len(rows)}
