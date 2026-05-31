"""Payment notices + retention release router — Chat 35 §R4.2 (Prompt 2.8b).

Mounted under /api/v1 via `server.py`.

Endpoints:
  GET    /payment-notices?subcontract_valuation_id=         .view
  GET    /payment-notices/{id}                              .view
  POST   /payment-notices/payless                           .create
  POST   /subcontracts/{sc_id}/retention-release            .release
  GET    /subcontracts/{sc_id}/retention-releases           .view

Error mapping:
  - PaymentNoticeNotFoundError / RetentionReleaseNotFoundError → 404
  - PaymentNoticeStateError / RetentionReleaseStateError       → 409
  - ValueError                                                 → 422
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.user import User
from app.services import payment_notices as pn_svc
from app.services import retention_releases as rr_svc
from app.services.payment_notices import (
    PaymentNoticeNotFoundError, PaymentNoticeStateError,
)
from app.services.retention_releases import (
    RetentionReleaseNotFoundError, RetentionReleaseStateError,
)


router = APIRouter(tags=["payment_notices"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PayLessNoticeBody(BaseModel):
    subcontract_valuation_id: uuid.UUID
    withhold_amount: str
    reason: str = Field(..., min_length=1, max_length=2000)
    due_date: Optional[date] = None


class RetentionReleaseBody(BaseModel):
    release_type: str = Field(..., max_length=10)
    release_pct: Optional[str] = None
    released_on: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=2000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, (PaymentNoticeNotFoundError,
                        RetentionReleaseNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc) or "Not found")
    if isinstance(exc, (PaymentNoticeStateError,
                        RetentionReleaseStateError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Payment notices — reads + PayLess create
# ---------------------------------------------------------------------------

@router.get("/payment-notices")
def list_payment_notices_endpoint(
    subcontract_valuation_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("payment_notices.view")
    ),
    db: Session = Depends(get_db),
):
    try:
        rows = pn_svc.list_payment_notices(
            db, user=current, perms=perms,
            subcontract_valuation_id=subcontract_valuation_id,
            limit=limit, offset=offset,
        )
    except (PaymentNoticeNotFoundError, ValueError) as exc:
        raise _map(exc)
    return {"items": [pn_svc.serialise(r) for r in rows], "total": len(rows)}


@router.get("/payment-notices/{notice_id}")
def get_payment_notice_endpoint(
    notice_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("payment_notices.view")
    ),
    db: Session = Depends(get_db),
):
    try:
        n = pn_svc.get_payment_notice(db, notice_id, user=current, perms=perms)
    except PaymentNoticeNotFoundError as exc:
        raise _map(exc)
    return pn_svc.serialise(n)


@router.post("/payment-notices/payless", status_code=201)
def create_payless_notice_endpoint(
    body: PayLessNoticeBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("payment_notices.create")
    ),
    db: Session = Depends(get_db),
):
    try:
        n = pn_svc.create_payless_notice(
            db,
            valuation_id=body.subcontract_valuation_id,
            withhold_amount=body.withhold_amount,
            reason=body.reason,
            due_date=body.due_date,
            user=current, perms=perms, request=request,
        )
    except (PaymentNoticeNotFoundError, PaymentNoticeStateError,
            ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(n)
    return pn_svc.serialise(n)


# ---------------------------------------------------------------------------
# Retention release — lives here per Build Pack §R4.2 note
# ---------------------------------------------------------------------------

@router.post("/subcontracts/{sc_id}/retention-release", status_code=201)
def release_retention_endpoint(
    sc_id: uuid.UUID,
    body: RetentionReleaseBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("payment_notices.release")
    ),
    db: Session = Depends(get_db),
):
    try:
        r = rr_svc.release_retention(
            db,
            subcontract_id=sc_id,
            release_type=body.release_type,
            release_pct=body.release_pct,
            released_on=body.released_on,
            notes=body.notes,
            user=current, perms=perms, request=request,
        )
    except (RetentionReleaseNotFoundError, RetentionReleaseStateError,
            ValueError) as exc:
        raise _map(exc)
    db.commit()
    db.refresh(r)
    return rr_svc.serialise(r)


@router.get("/subcontracts/{sc_id}/retention-releases")
def list_retention_releases_endpoint(
    sc_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(
        require_permission("payment_notices.view")
    ),
    db: Session = Depends(get_db),
):
    try:
        rows = rr_svc.list_releases(
            db, subcontract_id=sc_id, user=current, perms=perms,
        )
    except RetentionReleaseNotFoundError as exc:
        raise _map(exc)
    return {"items": [rr_svc.serialise(r) for r in rows], "total": len(rows)}
