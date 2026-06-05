"""Suppliers router — Chat 24 §R1 (Prompt 2.5 — Purchase Orders).

Mounted under /api/v1/suppliers (v1 prefix supplied at include time in
server.py).

Endpoints:
  GET    /suppliers                    suppliers.view
  POST   /suppliers                    suppliers.create
  GET    /suppliers/{id}               suppliers.view
  PATCH  /suppliers/{id}               suppliers.edit
  POST   /suppliers/{id}/archive       suppliers.archive
  POST   /suppliers/{id}/unarchive     suppliers.archive
  DELETE /suppliers/{id}               suppliers.delete  — 409 if linked

Tenant scoping:
  All endpoints scope by `current_user.tenant_id`. Suppliers are
  tenant-wide (NOT project-scoped) — Pattern α visible_project_ids does
  NOT apply to this resource.

Sensitive-field gating:
  Banking + vat_number + company_number fields are returned only if the
  caller has `suppliers.view_sensitive`. The same gate applies on write
  (PATCH silently ignores sensitive keys without the perm).
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth.deps import get_current_principal, Principal
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.services import suppliers as svc


router = APIRouter(prefix="/suppliers", tags=["suppliers"])


# ---------------------------------------------------------------------------
# Schemas (inline per house convention — see routers/projects.py)
# ---------------------------------------------------------------------------

class SupplierCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    trading_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    contact_email: Optional[str] = Field(None, max_length=200)
    contact_phone: Optional[str] = Field(None, max_length=50)
    address_line1: Optional[str] = Field(None, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    postcode: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=50)
    vat_number: Optional[str] = Field(None, max_length=50)
    vat_registered: Optional[bool] = Field(None)
    company_number: Optional[str] = Field(None, max_length=50)
    cis_status: Optional[str] = Field(None)
    bank_name: Optional[str] = Field(None, max_length=200)
    bank_account_no: Optional[str] = Field(None, max_length=50)
    bank_sort_code: Optional[str] = Field(None, max_length=20)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=365)
    notes: Optional[str] = Field(None)
    # Chat 32 §R4.1 (Prompt 2.7) — CIS / type label fields.
    # Chat 41 §R4.2 (Prompt 2.7-BE-rev-A) — supplier_type is now the
    # 4-value contact-type label; cis_subtype + default_vat_rate dropped.
    supplier_type: Optional[str] = Field(None, max_length=20)
    cis_registered: Optional[bool] = Field(None)
    utr: Optional[str] = Field(None, max_length=30)
    # Chat 41 §R4.2 — trade resolution (either id or name; see _resolve_trade).
    trade_id: Optional[str] = Field(None)
    trade: Optional[str] = Field(None, max_length=100)


class SupplierUpdateBody(BaseModel):
    """All fields optional — partial update semantics (PATCH)."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    trading_name: Optional[str] = Field(None, max_length=200)
    contact_name: Optional[str] = Field(None, max_length=200)
    contact_email: Optional[str] = Field(None, max_length=200)
    contact_phone: Optional[str] = Field(None, max_length=50)
    address_line1: Optional[str] = Field(None, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: Optional[str] = Field(None, max_length=100)
    postcode: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=50)
    vat_number: Optional[str] = Field(None, max_length=50)
    vat_registered: Optional[bool] = Field(None)
    company_number: Optional[str] = Field(None, max_length=50)
    cis_status: Optional[str] = Field(None)
    bank_name: Optional[str] = Field(None, max_length=200)
    bank_account_no: Optional[str] = Field(None, max_length=50)
    bank_sort_code: Optional[str] = Field(None, max_length=20)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=365)
    notes: Optional[str] = Field(None)
    # Chat 32 §R4.1 / Chat 41 §R4.2 — see SupplierCreateBody.
    supplier_type: Optional[str] = Field(None, max_length=20)
    cis_registered: Optional[bool] = Field(None)
    utr: Optional[str] = Field(None, max_length=30)
    trade_id: Optional[str] = Field(None)
    trade: Optional[str] = Field(None, max_length=100)


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
    request: Request,
    q: Optional[str] = Query(None, min_length=1, max_length=200),
    include_archived: bool = Query(False),
    supplier_type: Optional[str] = Query(
        None,
        description=(
            "Chat 41 §R4.2: filter to one of the 4 contact-type labels "
            "— 'Contractor', 'Supplier', 'Consultant', or 'Other'."
        ),
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "suppliers.view")
    include_sensitive = perms.has("suppliers.view_sensitive")

    try:
        rows, total = svc.list_suppliers(
            db, principal.tenant_id,
            q=q, include_archived=include_archived,
            supplier_type=supplier_type,
            limit=limit, offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "items": [svc.serialise(r, include_sensitive=include_sensitive) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", status_code=201)
def create_endpoint(
    body: SupplierCreateBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "suppliers.create")
    include_sensitive = perms.has("suppliers.view_sensitive")

    payload: dict[str, Any] = body.model_dump(exclude_unset=True)
    if not include_sensitive:
        # Strip sensitive keys silently — same behaviour as PATCH.
        for k in svc.SENSITIVE_RESPONSE_FIELDS:
            payload.pop(k, None)

    try:
        row = svc.create_supplier(
            db, principal.tenant_id, principal.user.id, payload,
            request=request,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise(row, include_sensitive=include_sensitive)


@router.get("/{supplier_id}")
def get_endpoint(
    supplier_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "suppliers.view")
    include_sensitive = perms.has("suppliers.view_sensitive")

    row = svc.get_supplier(db, principal.tenant_id, supplier_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return svc.serialise(row, include_sensitive=include_sensitive)


@router.patch("/{supplier_id}")
def patch_endpoint(
    supplier_id: uuid.UUID,
    body: SupplierUpdateBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "suppliers.edit")
    include_sensitive = perms.has("suppliers.view_sensitive")

    payload: dict[str, Any] = body.model_dump(exclude_unset=True)

    try:
        row = svc.update_supplier(
            db, principal.tenant_id, principal.user.id, supplier_id, payload,
            allow_sensitive=include_sensitive,
            request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise(row, include_sensitive=include_sensitive)


@router.post("/{supplier_id}/archive")
def archive_endpoint(
    supplier_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "suppliers.archive")
    include_sensitive = perms.has("suppliers.view_sensitive")

    try:
        row = svc.set_archived(
            db, principal.tenant_id, principal.user.id, supplier_id,
            archived=True, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier not found")

    db.commit()
    db.refresh(row)
    return svc.serialise(row, include_sensitive=include_sensitive)


@router.post("/{supplier_id}/unarchive")
def unarchive_endpoint(
    supplier_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "suppliers.archive")
    include_sensitive = perms.has("suppliers.view_sensitive")

    try:
        row = svc.set_archived(
            db, principal.tenant_id, principal.user.id, supplier_id,
            archived=False, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier not found")

    db.commit()
    db.refresh(row)
    return svc.serialise(row, include_sensitive=include_sensitive)


@router.delete("/{supplier_id}", status_code=204)
def delete_endpoint(
    supplier_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    """Hard-delete a supplier — Chat 41 §R-eyeball-2 (Prompt 2.7-FE-revision).

    Returns 204 on success.
    Returns 409 with a clear message when the supplier still has any
    linked records (purchase orders, actuals, subcontracts, CIS
    verifications, supplier documents) — operator must archive instead.
    """
    principal, perms = pair
    _check_perm(perms, "suppliers.delete")

    try:
        svc.delete_supplier(
            db, principal.tenant_id, principal.user.id, supplier_id,
            request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier not found")
    except svc.SupplierHasLinkedRecords as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete: supplier has linked records "
                f"({', '.join(exc.kinds)}) — archive instead."
            ),
        )

    db.commit()
    return None
