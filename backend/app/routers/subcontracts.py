"""Subcontracts router — Chat 34 §R4 (Prompt 2.8a).

Mounted under /api/v1 via `server.py`.

Endpoints:
  POST   /subcontracts                          subcontracts.create  → 201
  GET    /subcontracts?project_id=&status=      subcontracts.view
  GET    /subcontracts/{id}                     subcontracts.view
  PATCH  /subcontracts/{id}                     subcontracts.edit
  POST   /subcontracts/{id}/activate            subcontracts.approve
  POST   /subcontracts/{id}/complete            subcontracts.edit
  POST   /subcontracts/{id}/terminate           subcontracts.approve

Error mapping:
  - SubcontractNotFoundError → 404 (cross-tenant or missing)
  - SubcontractStateError    → 409 (bad workflow transition)
  - ValueError               → 422 (payload validation)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.user import User
from app.services import subcontracts as svc
from app.services.subcontracts import (
    SubcontractNotFoundError, SubcontractStateError,
)


router = APIRouter(tags=["subcontracts"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SubcontractCreateBody(BaseModel):
    project_id: uuid.UUID
    subcontractor_id: uuid.UUID
    title: str = Field(..., max_length=200)
    scope_description: Optional[str] = None
    purchase_order_id: Optional[uuid.UUID] = None
    # Pack 3.5 — optional package link (NULL = standalone subcontract).
    package_id: Optional[uuid.UUID] = None
    original_contract_sum: str = "0"
    retention_pct: str = "0"
    cis_applies: bool = True
    start_on: Optional[date] = None
    end_on: Optional[date] = None


class SubcontractUpdateBody(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    scope_description: Optional[str] = None
    original_contract_sum: Optional[str] = None
    retention_pct: Optional[str] = None
    cis_applies: Optional[bool] = None
    start_on: Optional[date] = None
    end_on: Optional[date] = None
    signed_at: Optional[datetime] = None
    signed_by: Optional[uuid.UUID] = None
    purchase_order_id: Optional[uuid.UUID] = None

    # Allow explicit `null` to clear scope_description / signed_*.
    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, SubcontractNotFoundError):
        return HTTPException(status_code=404, detail=str(exc) or "Not found")
    if isinstance(exc, SubcontractStateError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _serialise_with_perms(
    s, *, perms: UserPermissions,
) -> dict[str, Any]:
    has_sensitive = perms.has("subcontracts.view_sensitive")
    return svc.serialise(s, with_sensitive=has_sensitive)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/subcontracts", status_code=201)
def create_subcontract(
    body: SubcontractCreateBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontracts.create")
    ),
    db: Session = Depends(get_db),
):
    try:
        s = svc.create_subcontract(
            db,
            project_id=body.project_id,
            subcontractor_id=body.subcontractor_id,
            title=body.title,
            scope_description=body.scope_description,
            purchase_order_id=body.purchase_order_id,
            package_id=body.package_id,  # Pack 3.5
            original_contract_sum=body.original_contract_sum,
            retention_pct=body.retention_pct,
            cis_applies=body.cis_applies,
            start_on=body.start_on,
            end_on=body.end_on,
            user=current, perms=perms, request=request,
        )
    except (SubcontractNotFoundError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(s)
    return _serialise_with_perms(s, perms=perms)


@router.get("/subcontracts")
def list_subcontracts(
    project_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("subcontracts.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = svc.list_subcontracts(
            db, user=current, perms=perms,
            project_id=project_id, status=status,
            limit=limit, offset=offset,
        )
    except (SubcontractNotFoundError, ValueError) as exc:
        raise _map(exc)
    items = [_serialise_with_perms(r, perms=perms) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/subcontracts/{sc_id}")
def get_subcontract(
    sc_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("subcontracts.view")),
    db: Session = Depends(get_db),
):
    try:
        s = svc.get_subcontract(db, sc_id, user=current, perms=perms)
    except SubcontractNotFoundError as exc:
        raise _map(exc)
    return _serialise_with_perms(s, perms=perms)


@router.patch("/subcontracts/{sc_id}")
def update_subcontract(
    sc_id: uuid.UUID,
    body: SubcontractUpdateBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("subcontracts.edit")),
    db: Session = Depends(get_db),
):
    # Only include fields the client explicitly sent so PATCH semantics hold.
    payload = body.model_dump(exclude_unset=True)
    try:
        s = svc.update_subcontract(
            db, sc_id, user=current, perms=perms,
            payload=payload, request=request,
        )
    except (SubcontractNotFoundError, SubcontractStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(s)
    return _serialise_with_perms(s, perms=perms)


def _do_transition(svc_fn, *, db, sc_id, current, perms, request, **kwargs):
    try:
        s = svc_fn(
            db, sc_id, user=current, perms=perms, request=request, **kwargs,
        )
    except (SubcontractNotFoundError, SubcontractStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(s)
    return _serialise_with_perms(s, perms=perms)


@router.post("/subcontracts/{sc_id}/activate")
def activate_subcontract(
    sc_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontracts.approve")
    ),
    db: Session = Depends(get_db),
):
    return _do_transition(
        svc.activate_subcontract,
        db=db, sc_id=sc_id, current=current, perms=perms, request=request,
    )


@router.post("/subcontracts/{sc_id}/complete")
def complete_subcontract(
    sc_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("subcontracts.edit")),
    db: Session = Depends(get_db),
):
    return _do_transition(
        svc.complete_subcontract,
        db=db, sc_id=sc_id, current=current, perms=perms, request=request,
    )


@router.post("/subcontracts/{sc_id}/terminate")
def terminate_subcontract(
    sc_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("subcontracts.approve")
    ),
    db: Session = Depends(get_db),
):
    return _do_transition(
        svc.terminate_subcontract,
        db=db, sc_id=sc_id, current=current, perms=perms, request=request,
    )
