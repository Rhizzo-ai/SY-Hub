"""Purchase Orders router — Chat 24 §R2 (Prompt 2.5).

Mounted under /api/v1/purchase-orders.

Endpoints:
  GET    /purchase-orders                               pos.view
  POST   /projects/{project_id}/purchase-orders         pos.create
  GET    /purchase-orders/{po_id}                       pos.view
  PATCH  /purchase-orders/{po_id}                       pos.edit | pos.edit_issued
  DELETE /purchase-orders/{po_id}                       pos.delete (draft only)
  POST   /purchase-orders/{po_id}/submit                pos.submit
  POST   /purchase-orders/{po_id}/issue                 pos.submit  (post-approval)
  POST   /purchase-orders/{po_id}/void                  pos.void
  POST   /purchase-orders/{po_id}/close                 pos.close

Pricing fields are gated by `pos.view_sensitive` at the serialisation
layer (set to null when ungranted).

Tenant scoping: Pattern α via `app.services.po_authz`.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.deps import Principal, get_current_principal
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.services import purchase_orders as svc
from app.services.po_authz import PoNotFound
from app.services.po_numbering import NumberingError
from app.services.po_transitions import TransitionError


router = APIRouter(tags=["purchase_orders"])


# ─────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────

class POLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    budget_line_id: uuid.UUID
    description: str = Field(..., min_length=1, max_length=5000)
    quantity: float = Field(..., gt=0)
    unit_rate: float = Field(..., ge=0)
    vat_rate: float = Field(20.00, ge=0, le=100)
    cost_code: Optional[str] = Field(None, max_length=20)
    unit: Optional[str] = Field(None, max_length=20)
    line_number: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = Field(None)


class POCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: uuid.UUID
    budget_id: uuid.UUID
    po_number_prefix_id: Optional[uuid.UUID] = None
    lines: List[POLineCreate] = Field(..., min_length=1)
    issue_date: Optional[date] = None
    required_by_date: Optional[date] = None
    delivery_address: Optional[str] = None
    delivery_notes: Optional[str] = None
    external_reference: Optional[str] = Field(None, max_length=100)
    approval_required: bool = False
    approval_reason: Optional[str] = None
    notes: Optional[str] = None


class POPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: Optional[uuid.UUID] = None
    budget_id: Optional[uuid.UUID] = None
    issue_date: Optional[date] = None
    required_by_date: Optional[date] = None
    delivery_address: Optional[str] = None
    delivery_notes: Optional[str] = None
    external_reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    approval_required: Optional[bool] = None
    approval_reason: Optional[str] = None


class POVoidBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=1, max_length=2000)


class POCloseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Optional[str] = Field(None, max_length=2000)


class POSubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_reason: Optional[str] = Field(None, max_length=2000)


class POApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: Optional[str] = Field(None, max_length=2000)


class PORejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str = Field(..., min_length=1, max_length=2000)


class POUnlockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=1, max_length=2000)


# ─────────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────────

def _perm_dep(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> tuple[Principal, UserPermissions]:
    perms = compute_effective_permissions(
        db, principal.user.id, principal.tenant_id,
    )
    return principal, perms


def _require(perms: UserPermissions, code: str) -> None:
    if not perms.has(code):
        raise HTTPException(
            status_code=403, detail=f"Missing permission: {code}",
        )


# ─────────────────────────────────────────────────────────────────────────
# List / Create
# ─────────────────────────────────────────────────────────────────────────

@router.get("/purchase-orders")
def list_endpoint(
    project_id: Optional[uuid.UUID] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
    status: Optional[List[str]] = Query(None, alias="status"),
    q: Optional[str] = Query(None, min_length=1, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")
    include_sensitive = perms.has("pos.view_sensitive")

    rows, total = svc.list_pos(
        db, user=principal.user, perms=perms,
        project_id=project_id, supplier_id=supplier_id,
        status_in=status, q=q,
        limit=limit, offset=offset,
    )
    return {
        "items": [
            svc.serialise(p, include_sensitive=include_sensitive) for p in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/projects/{project_id}/purchase-orders", status_code=201)
def create_endpoint(
    project_id: uuid.UUID,
    body: POCreate,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.create")
    include_sensitive = perms.has("pos.view_sensitive")

    payload = body.model_dump(mode="python", exclude_unset=True)
    try:
        po = svc.create_po(
            db, user=principal.user, perms=perms,
            project_id=project_id, payload=payload, request=request,
        )
    except PoNotFound:
        # Pattern α — invisible project surfaces as 404, not 403.
        raise HTTPException(status_code=404, detail="Project not found")
    except NumberingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(po)
    return svc.serialise(po, include_sensitive=include_sensitive)


# ─────────────────────────────────────────────────────────────────────────
# Get / Patch / Delete
# ─────────────────────────────────────────────────────────────────────────

@router.get("/purchase-orders/{po_id}")
def get_endpoint(
    po_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")
    include_sensitive = perms.has("pos.view_sensitive")
    try:
        po = svc.get_po(db, user=principal.user, perms=perms, po_id=po_id)
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return svc.serialise(po, include_sensitive=include_sensitive)


@router.patch("/purchase-orders/{po_id}")
def patch_endpoint(
    po_id: uuid.UUID,
    body: POPatch,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    # We don't pre-check pos.edit / pos.edit_issued here — the service
    # tier-guard does it and surfaces a more informative 403.
    _require(perms, "pos.view")
    include_sensitive = perms.has("pos.view_sensitive")

    payload = body.model_dump(mode="python", exclude_unset=True)
    try:
        po = svc.update_po(
            db, user=principal.user, perms=perms,
            po_id=po_id, payload=payload, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(po)
    return svc.serialise(po, include_sensitive=include_sensitive)


@router.delete("/purchase-orders/{po_id}", status_code=204)
def delete_endpoint(
    po_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.delete")
    try:
        svc.delete_po(
            db, user=principal.user, perms=perms,
            po_id=po_id, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()


# ─────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────

def _run_transition(
    db: Session, fn, *, principal: Principal, perms: UserPermissions,
    include_sensitive: bool, **kwargs,
):
    """Helper: run a transition fn, map errors, commit, serialise."""
    try:
        po = fn(db, user=principal.user, perms=perms, **kwargs)
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    return svc.serialise(po, include_sensitive=include_sensitive)


@router.post("/purchase-orders/{po_id}/submit")
def submit_endpoint(
    po_id: uuid.UUID,
    body: POSubmitBody | None = None,
    request: Request = None,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    # Build pack §3.3 — /submit is gated by pos.create (the creator
    # persona triggers submit). The /issue endpoint (post-approval)
    # is gated by pos.issue.
    _require(perms, "pos.create")
    include_sensitive = perms.has("pos.view_sensitive")
    from app.services import po_approvals as approvals_svc
    try:
        po, approval = approvals_svc.submit_po_with_budget_gate(
            db, user=principal.user, perms=perms, po_id=po_id,
            submission_reason=(body.submission_reason if body else None),
            request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    out = svc.serialise(po, include_sensitive=include_sensitive)
    out["approval"] = (
        approvals_svc.serialise_approval(approval) if approval else None
    )
    return out


@router.post("/purchase-orders/{po_id}/issue")
def issue_endpoint(
    po_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    # Build pack §3.3 — /issue (post-approval) gated by pos.issue.
    _require(perms, "pos.issue")
    return _run_transition(
        db, svc.issue_po,
        principal=principal, perms=perms,
        include_sensitive=perms.has("pos.view_sensitive"),
        po_id=po_id, request=request,
    )


@router.post("/purchase-orders/{po_id}/void")
def void_endpoint(
    po_id: uuid.UUID,
    body: POVoidBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.void")
    return _run_transition(
        db, svc.void_po,
        principal=principal, perms=perms,
        include_sensitive=perms.has("pos.view_sensitive"),
        po_id=po_id, reason=body.reason, request=request,
    )


@router.post("/purchase-orders/{po_id}/close")
def close_endpoint(
    po_id: uuid.UUID,
    body: POCloseBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.close")
    return _run_transition(
        db, svc.close_po,
        principal=principal, perms=perms,
        include_sensitive=perms.has("pos.view_sensitive"),
        po_id=po_id, reason=body.reason, request=request,
    )



# ─────────────────────────────────────────────────────────────────────────
# §R3 — Approval endpoints
# ─────────────────────────────────────────────────────────────────────────

@router.post("/purchase-orders/{po_id}/approve")
def approve_endpoint(
    po_id: uuid.UUID,
    body: POApproveBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.approve")
    include_sensitive = perms.has("pos.view_sensitive")
    from app.services import po_approvals as approvals_svc
    try:
        po, row = approvals_svc.approve_po(
            db, user=principal.user, perms=perms, po_id=po_id,
            notes=body.notes, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except approvals_svc.SelfApprovalForbidden:
        raise HTTPException(
            status_code=403,
            detail={
                "type": "po/self-approval-forbidden",
                "title": "Submitter cannot approve their own PO",
            },
        )
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    out = svc.serialise(po, include_sensitive=include_sensitive)
    out["approval"] = approvals_svc.serialise_approval(row)
    return out


@router.post("/purchase-orders/{po_id}/reject")
def reject_endpoint(
    po_id: uuid.UUID,
    body: PORejectBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.approve")
    include_sensitive = perms.has("pos.view_sensitive")
    from app.services import po_approvals as approvals_svc
    try:
        po, row = approvals_svc.reject_po(
            db, user=principal.user, perms=perms, po_id=po_id,
            notes=body.notes, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except approvals_svc.SelfApprovalForbidden:
        raise HTTPException(
            status_code=403,
            detail={
                "type": "po/self-approval-forbidden",
                "title": "Submitter cannot reject their own PO",
            },
        )
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    out = svc.serialise(po, include_sensitive=include_sensitive)
    out["approval"] = approvals_svc.serialise_approval(row)
    return out


@router.post("/purchase-orders/{po_id}/unlock")
def unlock_endpoint(
    po_id: uuid.UUID,
    body: POUnlockBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.edit")
    include_sensitive = perms.has("pos.view_sensitive")
    from app.services import po_approvals as approvals_svc
    try:
        po = approvals_svc.unlock_po(
            db, user=principal.user, perms=perms, po_id=po_id,
            reason=body.reason, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    return svc.serialise(po, include_sensitive=include_sensitive)


@router.get("/purchase-orders/{po_id}/approvals")
def list_po_approvals_endpoint(
    po_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")
    from app.services import po_approvals as approvals_svc
    try:
        po = svc.get_po(db, user=principal.user, perms=perms, po_id=po_id)
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    rows = approvals_svc.list_approvals_for_po(db, po)
    return {
        "items": [approvals_svc.serialise_approval(r) for r in rows],
        "total": len(rows),
    }


@router.get("/projects/{project_id}/approvals/pending")
def list_project_pending_approvals(
    project_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.approve")
    from app.services import po_approvals as approvals_svc
    items = approvals_svc.list_pending_approvals(
        db, user=principal.user, perms=perms, project_id=project_id,
    )
    return {"items": items, "total": len(items)}


@router.get("/approvals/pending")
def list_all_pending_approvals(
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.approve")
    from app.services import po_approvals as approvals_svc
    items = approvals_svc.list_pending_approvals(
        db, user=principal.user, perms=perms,
    )
    return {"items": items, "total": len(items)}
