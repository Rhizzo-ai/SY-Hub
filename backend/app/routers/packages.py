"""Packages router — B88 Pack 3 (Chat 53, the tendering spine).

Mounted under /api/v1 via `server.py` (`v1_router.include_router(...)`).

External paths (verbatim — see Build Pack §4):

  POST   /projects/{project_id}/packages                packages.create
  GET    /projects/{project_id}/packages                packages.view
  GET    /packages                                      packages.view
  GET    /packages/{package_id}                         packages.view
  PATCH  /packages/{package_id}                         packages.edit
  DELETE /packages/{package_id}                         packages.delete
  POST   /packages/{package_id}/lines                   packages.edit
  PATCH  /packages/{package_id}/lines/{line_id}         packages.edit
  DELETE /packages/{package_id}/lines/{line_id}         packages.edit
  POST   /packages/{package_id}/send-to-tender          packages.edit
  POST   /packages/{package_id}/cancel                  packages.edit
  POST   /packages/{package_id}/bids                    packages.edit
  GET    /packages/{package_id}/bids                    packages.view
  POST   /bids/{bid_id}/enter                           packages.edit
  POST   /bids/{bid_id}/decline                         packages.edit
  POST   /bids/{bid_id}/withdraw                        packages.edit
  POST   /packages/{package_id}/award                   packages.award
  POST   /awards/{award_id}/cancel                      packages.award

Error mapping (mirrors routers/subcontracts.py):
  - PackageNotFoundError → 404
  - PackageStateError    → 409
  - ValueError           → 422
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.user import User
from app.schemas.packages import (
    AwardBody, CancelAwardBody, CancelBody, EnterBidBody, InviteBidderBody,
    PackageCreateBody, PackageLineCreateBody, PackageLineUpdateBody,
    PackageUpdateBody,
)
from app.services import packages as svc
from app.services.budget_errors import BudgetLineRaceError as _BLineRace
from app.services.packages import (
    PackageNotFoundError, PackageStateError,
)


router = APIRouter(tags=["packages"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, PackageNotFoundError):
        return HTTPException(status_code=404, detail=str(exc) or "Not found")
    if isinstance(exc, PackageStateError):
        return HTTPException(status_code=409, detail=str(exc))
    # B105/B106 §3.9 — concurrent mint race surfaces as 409, not 500.
    from app.services.budget_errors import BudgetLineRaceError as _BLR
    if isinstance(exc, _BLR):
        return HTTPException(
            status_code=409,
            detail={
                "type": "budget_line_race",
                "title": "A budget line for this cost code was just "
                         "created concurrently; retry the request.",
                "cost_code_id": exc.cost_code_id,
                "cost_code_subcategory_id": exc.cost_code_subcategory_id,
            },
        )
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _serialise_with_perms(
    p, *, perms: UserPermissions, db=None,
) -> dict[str, Any]:
    return svc.serialise_package(
        p, with_sensitive=perms.has("packages.view_sensitive"),
        db=db,
    )


# ---------------------------------------------------------------------------
# Package CRUD
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{project_id}/packages", status_code=201,
)
def create_package(
    project_id: uuid.UUID,
    body: PackageCreateBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.create")),
    db: Session = Depends(get_db),
):
    try:
        p = svc.create_package(
            db,
            project_id=project_id,
            budget_id=body.budget_id,
            title=body.title,
            kind=body.kind,
            description=body.description,
            user=current, perms=perms, request=request,
        )
    except (PackageNotFoundError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, p.id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.get("/projects/{project_id}/packages")
def list_packages_for_project(
    project_id: uuid.UUID,
    status: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = svc.list_packages(
            db, user=current, perms=perms,
            project_id=project_id, status=status, kind=kind,
            limit=limit, offset=offset,
        )
    except (PackageNotFoundError, ValueError) as exc:
        raise _map(exc)
    items = [_serialise_with_perms(r, perms=perms, db=db) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/packages")
def list_packages_global(
    status: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = svc.list_packages(
            db, user=current, perms=perms,
            project_id=None, status=status, kind=kind,
            limit=limit, offset=offset,
        )
    except (PackageNotFoundError, ValueError) as exc:
        raise _map(exc)
    items = [_serialise_with_perms(r, perms=perms, db=db) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/packages/{package_id}")
def get_package(
    package_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.view")),
    db: Session = Depends(get_db),
):
    try:
        p = svc.get_package(db, package_id, user=current, perms=perms)
    except PackageNotFoundError as exc:
        raise _map(exc)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.patch("/packages/{package_id}")
def patch_package(
    package_id: uuid.UUID,
    body: PackageUpdateBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    payload = body.model_dump(exclude_unset=True)
    try:
        p = svc.update_package(
            db, package_id, user=current, perms=perms,
            payload=payload, request=request,
        )
    except (PackageNotFoundError, PackageStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, p.id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.delete("/packages/{package_id}", status_code=204)
def delete_package(
    package_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.delete")),
    db: Session = Depends(get_db),
):
    try:
        svc.delete_package(
            db, package_id, user=current, perms=perms, request=request,
        )
    except (PackageNotFoundError, PackageStateError) as exc:
        raise _map(exc)
    db.commit()


# ---------------------------------------------------------------------------
# Package lines
# ---------------------------------------------------------------------------

@router.post("/packages/{package_id}/lines", status_code=201)
def add_line(
    package_id: uuid.UUID,
    body: PackageLineCreateBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc.add_package_line(
            db, package_id,
            cost_code_id=body.cost_code_id,
            cost_code_subcategory_id=body.cost_code_subcategory_id,
            budget_line_id=body.budget_line_id,
            unbudgeted=body.unbudgeted,
            unbudgeted_cost_code_id=body.unbudgeted_cost_code_id,
            unbudgeted_subcategory_id=body.unbudgeted_subcategory_id,
            unbudgeted_reason=body.unbudgeted_reason,
            description=body.description,
            quantity=body.quantity,
            unit=body.unit,
            budgeted_unit_rate=body.budgeted_unit_rate,
            notes=body.notes,
            user=current, perms=perms, request=request,
        )
    except (PackageNotFoundError, PackageStateError, ValueError,
            _BLineRace) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.patch("/packages/{package_id}/lines/{line_id}")
def patch_line(
    package_id: uuid.UUID, line_id: uuid.UUID,
    body: PackageLineUpdateBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    payload = body.model_dump(exclude_unset=True)
    try:
        svc.update_package_line(
            db, package_id, line_id, user=current, perms=perms,
            payload=payload, request=request,
        )
    except (PackageNotFoundError, PackageStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.delete("/packages/{package_id}/lines/{line_id}", status_code=204)
def delete_line(
    package_id: uuid.UUID, line_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc.remove_package_line(
            db, package_id, line_id, user=current, perms=perms,
            request=request,
        )
    except (PackageNotFoundError, PackageStateError) as exc:
        raise _map(exc)
    db.commit()


# ---------------------------------------------------------------------------
# Tender lifecycle
# ---------------------------------------------------------------------------

@router.post("/packages/{package_id}/send-to-tender")
def send_to_tender_endpoint(
    package_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc.send_to_tender(
            db, package_id, user=current, perms=perms, request=request,
        )
    except (PackageNotFoundError, PackageStateError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.post("/packages/{package_id}/cancel")
def cancel_package_endpoint(
    package_id: uuid.UUID,
    body: CancelBody | None = None,
    request: Request = None,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    reason = body.reason if body else None
    try:
        svc.cancel_package(
            db, package_id, user=current, perms=perms,
            reason=reason, request=request,
        )
    except (PackageNotFoundError, PackageStateError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


# ---------------------------------------------------------------------------
# Bids
# ---------------------------------------------------------------------------

@router.post("/packages/{package_id}/bids", status_code=201)
def invite_bidder_endpoint(
    package_id: uuid.UUID,
    body: InviteBidderBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    try:
        svc.invite_bidder(
            db, package_id, supplier_id=body.supplier_id,
            user=current, perms=perms, request=request,
        )
    except (PackageNotFoundError, PackageStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.get("/packages/{package_id}/bids")
def list_bids_endpoint(
    package_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.view")),
    db: Session = Depends(get_db),
):
    try:
        bids = svc.list_bids_for_package(
            db, package_id, user=current, perms=perms,
        )
    except PackageNotFoundError as exc:
        raise _map(exc)
    has_sensitive = perms.has("packages.view_sensitive")
    return {
        "items": [
            svc._ser_bid(b, include_sensitive=has_sensitive) for b in bids
        ],
        "total": len(bids),
    }


@router.post("/bids/{bid_id}/enter")
def enter_bid_endpoint(
    bid_id: uuid.UUID,
    body: EnterBidBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    lines_payload = [
        {
            "package_line_id": str(ln.package_line_id),
            "quoted_unit_rate": ln.quoted_unit_rate,
        }
        for ln in body.lines
    ]
    try:
        bid = svc.enter_bid(
            db, bid_id, lines=lines_payload,
            user=current, perms=perms, notes=body.notes, request=request,
        )
    except (PackageNotFoundError, PackageStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, bid.package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.post("/bids/{bid_id}/decline")
def decline_bid_endpoint(
    bid_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    try:
        bid = svc.decline_bid(
            db, bid_id, user=current, perms=perms, request=request,
        )
    except (PackageNotFoundError, PackageStateError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, bid.package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.post("/bids/{bid_id}/withdraw")
def withdraw_bid_endpoint(
    bid_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.edit")),
    db: Session = Depends(get_db),
):
    try:
        bid = svc.withdraw_bid(
            db, bid_id, user=current, perms=perms, request=request,
        )
    except (PackageNotFoundError, PackageStateError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, bid.package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


# ---------------------------------------------------------------------------
# Award engine
# ---------------------------------------------------------------------------

@router.post("/packages/{package_id}/award")
def award_endpoint(
    package_id: uuid.UUID,
    body: AwardBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.award")),
    db: Session = Depends(get_db),
):
    awards_payload = [
        {
            "supplier_id": str(s.supplier_id),
            "source_bid_id": (
                str(s.source_bid_id) if s.source_bid_id else None
            ),
            "lines": [
                {
                    "package_line_id": str(ln.package_line_id),
                    "quantity": ln.quantity,
                    "awarded_unit_rate": ln.awarded_unit_rate,
                }
                for ln in s.lines
            ],
            "required_by_date": s.required_by_date,
            "delivery_address": s.delivery_address,
            "retention_pct": s.retention_pct,
            "cis_applies": s.cis_applies,
            "scope_description": s.scope_description,
        }
        for s in body.awards
    ]
    try:
        svc.award_package(
            db, package_id, awards=awards_payload,
            user=current, perms=perms, request=request,
        )
    except (PackageNotFoundError, PackageStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)


@router.post("/awards/{award_id}/cancel")
def cancel_award_endpoint(
    award_id: uuid.UUID,
    body: CancelAwardBody,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("packages.award")),
    db: Session = Depends(get_db),
):
    try:
        award = svc.cancel_award(
            db, award_id, user=current, perms=perms,
            reason=body.reason, request=request,
        )
    except (PackageNotFoundError, PackageStateError, ValueError) as exc:
        raise _map(exc)
    db.commit()
    p = svc.get_package(db, award.package_id, user=current, perms=perms)
    return _serialise_with_perms(p, perms=perms, db=db)
