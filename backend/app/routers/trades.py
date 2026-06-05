"""Trades router — Chat 41 §R4.1 (Prompt 2.7-BE-rev-A).

Mounted under /api/v1/trades (v1 prefix supplied at include time in
server.py, directly after suppliers_router).

Endpoints:
  GET    /trades                       trades.view
  POST   /trades                       trades.create   (idempotent grow-as-you-type)
  POST   /trades/{id}/archive          trades.create   (mutate gate reused)
  POST   /trades/{id}/unarchive        trades.create

Tenant scoping:
  All endpoints scope by `current_user.tenant_id`. Trades are
  tenant-wide. No GET-by-id (the FE only needs list + create in rev-A).
  No PATCH/rename in rev-A — that's a clean follow-up.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_principal, Principal
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.services import trades as svc


router = APIRouter(prefix="/trades", tags=["trades"])


# ---------------------------------------------------------------------------
# Schemas (inline per house convention — see routers/suppliers.py)
# ---------------------------------------------------------------------------

class TradeCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_perm(perms: UserPermissions, code: str) -> None:
    if not perms.has(code):
        raise HTTPException(status_code=403, detail=f"Missing permission: {code}")


def _perm_dep(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> tuple[Principal, UserPermissions]:
    perms = compute_effective_permissions(db, principal.user.id, principal.tenant_id)
    return principal, perms


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
def list_endpoint(
    q: Optional[str] = Query(None, min_length=1, max_length=100),
    include_archived: bool = Query(False),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "trades.view")
    rows, total = svc.list_trades(
        db, principal.tenant_id,
        q=q, include_archived=include_archived,
        limit=limit, offset=offset,
    )
    return {
        "items": [svc.serialise(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", status_code=201)
def create_endpoint(
    body: TradeCreateBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    """Idempotent grow-as-you-type create.

    Returns 201 with the trade (existing or newly-created). A typed name
    that matches an existing trade (case-insensitive within tenant)
    returns the existing row — no audit row, no duplicate.
    """
    principal, perms = pair
    _check_perm(perms, "trades.create")
    try:
        row = svc.get_or_create_trade(
            db, principal.tenant_id, principal.user.id, body.name,
            request=request,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise(row)


@router.post("/{trade_id}/archive")
def archive_endpoint(
    trade_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    # `trades.create` doubles as the mutate gate — no separate archive
    # permission in rev-A (documented in §R4.1 NOTE).
    _check_perm(perms, "trades.create")
    try:
        row = svc.set_archived(
            db, principal.tenant_id, principal.user.id, trade_id,
            archived=True, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Trade not found")

    db.commit()
    db.refresh(row)
    return svc.serialise(row)


@router.post("/{trade_id}/unarchive")
def unarchive_endpoint(
    trade_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "trades.create")
    try:
        row = svc.set_archived(
            db, principal.tenant_id, principal.user.id, trade_id,
            archived=False, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Trade not found")

    db.commit()
    db.refresh(row)
    return svc.serialise(row)
