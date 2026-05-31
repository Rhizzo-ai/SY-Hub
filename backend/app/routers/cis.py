"""CIS verifications router — Chat 32 §R4.2 (Prompt 2.7).

Mounted under /api/v1/cis (v1 prefix supplied at include time in
server.py).

Endpoints:
  POST /cis/verifications                 cis.verify    → 201
  GET  /cis/verifications?supplier_id=    cis.view      (sensitive fields
                                                          gated by
                                                          cis.view_sensitive)
  GET  /cis/verifications/current?supplier_id=  cis.view

No PATCH, no DELETE — verifications are append-only.

Cross-tenant supplier IDs return 404 (not 403) so the API does not leak
the existence of supplier IDs across tenants.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_principal, Principal
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.services import cis as svc


router = APIRouter(prefix="/cis", tags=["cis"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CISVerificationCreateBody(BaseModel):
    supplier_id: uuid.UUID
    verification_number: Optional[str] = Field(None, max_length=20)
    match_status: str = Field(..., max_length=20)
    tax_rate_pct: Optional[float] = Field(None, ge=0, le=100)
    verified_on: str = Field(..., description="ISO date (YYYY-MM-DD)")
    expires_on: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD)")
    notes: Optional[str] = Field(None)


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

@router.post("/verifications", status_code=201)
def create_verification(
    body: CISVerificationCreateBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "cis.verify")

    try:
        row = svc.record_verification(
            db,
            principal.tenant_id,
            body.supplier_id,
            verification_number=body.verification_number,
            match_status=body.match_status,
            tax_rate_pct=body.tax_rate_pct,
            verified_on=body.verified_on,
            expires_on=body.expires_on,
            notes=body.notes,
            actor_id=principal.user.id,
            request=request,
        )
    except LookupError:
        # Cross-tenant or unknown supplier → 404 (do not leak existence).
        raise HTTPException(status_code=404, detail="Supplier not found")
    except ValueError as e:
        msg = str(e)
        # Wrong supplier_type is a business-state conflict, not a payload
        # validation error → 409 per Build Pack §R4.2.
        if "only valid for subcontractors" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=422, detail=msg)

    db.commit()
    db.refresh(row)
    # cis.verify implies the actor sees what they just wrote — include
    # the verification_number in the 201 response regardless of
    # view_sensitive. Subsequent reads honour the gate.
    return svc.serialise(row, include_sensitive=True)


@router.get("/verifications")
def list_verifications(
    supplier_id: uuid.UUID = Query(...),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "cis.view")
    include_sensitive = perms.has("cis.view_sensitive")

    try:
        rows = svc.list_verifications(db, principal.tenant_id, supplier_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {
        "items": [
            svc.serialise(r, include_sensitive=include_sensitive) for r in rows
        ],
        "total": len(rows),
    }


@router.get("/verifications/current")
def get_current_verification(
    supplier_id: uuid.UUID = Query(...),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "cis.view")
    include_sensitive = perms.has("cis.view_sensitive")

    try:
        row = svc.get_current_verification(db, principal.tenant_id, supplier_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if row is None:
        return None
    return svc.serialise(row, include_sensitive=include_sensitive)
