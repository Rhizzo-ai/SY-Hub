"""Supplier compliance documents router — Chat 32 §R4.3 (Prompt 2.7).

Mounted under /api/v1/supplier-documents (v1 prefix supplied at include
time in server.py).

Endpoints:
  POST   /supplier-documents              supplier_documents.create   201
  GET    /supplier-documents?supplier_id= supplier_documents.view
  GET    /supplier-documents/{id}         supplier_documents.view
  PATCH  /supplier-documents/{id}         supplier_documents.edit
  POST   /supplier-documents/{id}/archive   supplier_documents.archive
  POST   /supplier-documents/{id}/unarchive supplier_documents.archive

Cross-tenant lookups return 404 (not 403).
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
from app.services import supplier_documents as svc


router = APIRouter(prefix="/supplier-documents", tags=["supplier_documents"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SupplierDocumentCreateBody(BaseModel):
    supplier_id: uuid.UUID
    doc_type: str = Field(..., max_length=40)
    title: str = Field(..., min_length=1, max_length=200)
    file_ref: Optional[str] = Field(None, max_length=500)
    issued_on: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD)")
    expires_on: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD)")
    notes: Optional[str] = Field(None)


class SupplierDocumentUpdateBody(BaseModel):
    doc_type: Optional[str] = Field(None, max_length=40)
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    file_ref: Optional[str] = Field(None, max_length=500)
    issued_on: Optional[str] = Field(None)
    expires_on: Optional[str] = Field(None)
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

@router.post("", status_code=201)
def create_endpoint(
    body: SupplierDocumentCreateBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "supplier_documents.create")

    payload: dict[str, Any] = body.model_dump(exclude_unset=True)
    payload["supplier_id"] = str(body.supplier_id)
    try:
        row = svc.create_document(
            db, principal.tenant_id, principal.user.id, payload,
            request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    # The actor just wrote the row; surface all fields back to the
    # creator regardless of view_sensitive. Subsequent reads honour
    # the gate.
    return svc.serialise(row, include_sensitive=True)


@router.get("")
def list_endpoint(
    supplier_id: uuid.UUID = Query(...),
    include_archived: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "supplier_documents.view")
    include_sensitive = perms.has("supplier_documents.view_sensitive")

    try:
        rows, total = svc.list_documents(
            db, principal.tenant_id, supplier_id,
            include_archived=include_archived,
            limit=limit, offset=offset,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {
        "items": [
            svc.serialise(r, include_sensitive=include_sensitive) for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{document_id}")
def get_endpoint(
    document_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "supplier_documents.view")
    include_sensitive = perms.has("supplier_documents.view_sensitive")

    row = svc.get_document(db, principal.tenant_id, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Supplier document not found")
    return svc.serialise(row, include_sensitive=include_sensitive)


@router.patch("/{document_id}")
def patch_endpoint(
    document_id: uuid.UUID,
    body: SupplierDocumentUpdateBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "supplier_documents.edit")
    include_sensitive = perms.has("supplier_documents.view_sensitive")

    payload: dict[str, Any] = body.model_dump(exclude_unset=True)
    try:
        row = svc.update_document(
            db, principal.tenant_id, principal.user.id, document_id, payload,
            request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier document not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise(row, include_sensitive=include_sensitive)


@router.post("/{document_id}/archive")
def archive_endpoint(
    document_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "supplier_documents.archive")
    include_sensitive = perms.has("supplier_documents.view_sensitive")

    try:
        row = svc.set_archived(
            db, principal.tenant_id, principal.user.id, document_id,
            archived=True, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier document not found")

    db.commit()
    db.refresh(row)
    return svc.serialise(row, include_sensitive=include_sensitive)


@router.post("/{document_id}/unarchive")
def unarchive_endpoint(
    document_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "supplier_documents.archive")
    include_sensitive = perms.has("supplier_documents.view_sensitive")

    try:
        row = svc.set_archived(
            db, principal.tenant_id, principal.user.id, document_id,
            archived=False, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier document not found")

    db.commit()
    db.refresh(row)
    return svc.serialise(row, include_sensitive=include_sensitive)
