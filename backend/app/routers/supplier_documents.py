"""Supplier compliance documents router — Chat 32 §R4.3 (Prompt 2.7)
+ Chat 41 §R4 (Build Pack 2.7-BE-rev-B) — multipart upload + streamed
download.

Mounted under /api/v1/supplier-documents (v1 prefix supplied at include
time in server.py).

Endpoints:
  POST   /supplier-documents              supplier_documents.create   201
  GET    /supplier-documents?supplier_id= supplier_documents.view
  GET    /supplier-documents/{id}         supplier_documents.view
  PATCH  /supplier-documents/{id}         supplier_documents.edit
  POST   /supplier-documents/{id}/archive   supplier_documents.archive
  POST   /supplier-documents/{id}/unarchive supplier_documents.archive

rev-B file endpoints (no new permissions — reuse existing):
  POST   /supplier-documents/{id}/file    supplier_documents.edit
  GET    /supplier-documents/{id}/file    supplier_documents.view_sensitive

Cross-tenant lookups return 404 (not 403).

rev-B tightening (§R4.2 VERIFY): `file_ref` is REMOVED from the
create / update request bodies. It is system-owned (a structured
`StoredObjectRef` JSON pointer set by the upload endpoint). It remains
in the serialised response, gated by `supplier_documents.view_sensitive`.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import (
    APIRouter, Depends, File, HTTPException, Query, Request, UploadFile,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_principal, Principal
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.services import supplier_documents as svc
from app.services.sharepoint_client import (
    DocumentStore, SharePointError, get_document_store,
)


log = logging.getLogger(__name__)

router = APIRouter(prefix="/supplier-documents", tags=["supplier_documents"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

# rev-B §R4.2: `file_ref` is REMOVED from both create + update request
# bodies. Clients can no longer stuff a free-text string here — the
# field is system-owned and only set via the upload endpoint.

class SupplierDocumentCreateBody(BaseModel):
    supplier_id: uuid.UUID
    # Chat 45 §R3.2 (Build Pack 2.7-DOCS-BE) — doc_type + title relaxed
    # to optional. folder_id added (optional). Validation is done in
    # the service layer (folder ownership, doc_type vocabulary).
    doc_type: Optional[str] = Field(None, max_length=40)
    title: Optional[str] = Field(None, max_length=200)
    folder_id: Optional[uuid.UUID] = None
    issued_on: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD)")
    expires_on: Optional[str] = Field(None, description="ISO date (YYYY-MM-DD)")
    notes: Optional[str] = Field(None)


class SupplierDocumentUpdateBody(BaseModel):
    doc_type: Optional[str] = Field(None, max_length=40)
    title: Optional[str] = Field(None, max_length=200)
    folder_id: Optional[uuid.UUID] = None
    issued_on: Optional[str] = Field(None)
    expires_on: Optional[str] = Field(None)
    notes: Optional[str] = Field(None)


class SupplierDocumentMoveBody(BaseModel):
    """Chat 45 §R3.2 — re-file a document into a folder (or root)."""
    folder_id: Optional[uuid.UUID] = None


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


def _document_store_dep() -> DocumentStore:
    """FastAPI dependency for the configured document store.

    In stub mode (default + every automated test) this returns the
    shared in-process `StubDocumentStore`. In live mode it returns a
    `GraphDocumentStore` — Microsoft Graph SharePoint.
    """
    return get_document_store()


# rev-B: classify a ValueError raised by the service layer as either
# 413 (file too large) or 422 (other validation — content-type, empty,
# malformed). The Build Pack §R4.1 leaves the size-cap choice to the
# implementer; we pick 413 for clear semantics.
def _value_error_to_http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "exceeds maximum upload size" in msg:
        return HTTPException(status_code=413, detail=msg)
    return HTTPException(status_code=422, detail=msg)


# ---------------------------------------------------------------------------
# Metadata routes (existing — file_ref removed from bodies per §R4.2)
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


@router.post("/{document_id}/move")
def move_document_endpoint(
    document_id: uuid.UUID,
    body: SupplierDocumentMoveBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    """Chat 45 §R3.2 — re-file a supplier document into a folder.

    Permission: `documents.move`. Body: `{folder_id: uuid | null}`
    (null = unfiled/root). The folder MUST belong to the same supplier
    and be in the same tenant.
    """
    principal, perms = pair
    _check_perm(perms, "documents.move")
    include_sensitive = perms.has("supplier_documents.view_sensitive")

    try:
        row = svc.move_document_to_folder(
            db, principal.tenant_id, principal.user.id, document_id,
            body.folder_id, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Supplier document not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise(row, include_sensitive=include_sensitive)


# ---------------------------------------------------------------------------
# rev-B: file upload / download endpoints
# ---------------------------------------------------------------------------

@router.post("/{document_id}/file")
def upload_file_endpoint(
    document_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
    store: DocumentStore = Depends(_document_store_dep),
):
    """Upload (or replace) the binary file attached to a supplier document.

    Permission: `supplier_documents.edit`.
    Returns the serialised document (with sensitive fields, since the
    caller just supplied the bytes — matches the create endpoint pattern).

    Error mapping:
      ValueError("file exceeds maximum upload size ...") → 413
      ValueError (content-type / empty / other)          → 422
      LookupError                                        → 404
      SharePointError                                    → 502 "document storage unavailable"
    """
    principal, perms = pair
    _check_perm(perms, "supplier_documents.edit")

    try:
        row = svc.upload_document_file(
            db,
            principal.tenant_id,
            principal.user.id,
            document_id,
            file_stream=file.file,
            original_filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            store=store,
            request=request,
        )
    except LookupError:
        raise HTTPException(
            status_code=404, detail="Supplier document not found",
        )
    except ValueError as e:
        raise _value_error_to_http(e)
    except SharePointError:
        # Never leak Graph internals (URLs, tokens, body). One generic
        # message that maps cleanly through the FE.
        log.warning(
            "supplier_documents: storage failure on upload doc=%s",
            document_id,
        )
        raise HTTPException(
            status_code=502, detail="document storage unavailable",
        )

    db.commit()
    db.refresh(row)
    # Actor just wrote the file — surface all (sensitive) fields back.
    return svc.serialise(row, include_sensitive=True)


@router.get("/{document_id}/file")
def download_file_endpoint(
    document_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
    store: DocumentStore = Depends(_document_store_dep),
):
    """Stream the file attached to a supplier document.

    Permission: `supplier_documents.view_sensitive`.

    Error mapping:
      LookupError       → 404 (doc not in tenant, OR no file attached)
      SharePointError   → 502 "document storage unavailable"
    """
    principal, perms = pair
    # Download is the sensitive read — gate strictly on view_sensitive.
    _check_perm(perms, "supplier_documents.view_sensitive")

    try:
        content, filename, content_type = svc.download_document_file(
            db,
            principal.tenant_id,
            principal.user.id,
            document_id,
            store=store,
            request=request,
        )
    except LookupError:
        raise HTTPException(
            status_code=404, detail="Supplier document file not found",
        )
    except SharePointError:
        log.warning(
            "supplier_documents: storage failure on download doc=%s",
            document_id,
        )
        raise HTTPException(
            status_code=502, detail="document storage unavailable",
        )

    db.commit()

    # Build a safe Content-Disposition. The Graph URL never leaves this
    # module — the FE receives the bytes directly.
    safe_name = filename.replace('"', "")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}"',
        "Content-Length": str(len(content)),
    }
    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers=headers,
    )
