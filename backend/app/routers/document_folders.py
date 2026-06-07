"""Document folder router — Chat 45 §R3.1 (Build Pack 2.7-DOCS-BE).

Mounted under /api/v1/document-folders (the v1 prefix is supplied at
include time in backend/server.py, matching supplier_documents).

Endpoints (per §R0.4):
  POST   /document-folders              documents.create     201
  GET    /document-folders?owner_type=&owner_id=
                                        _owner_view_perm(owner_type)
  GET    /document-folders/{id}         _owner_view_perm(owner_type)
  PATCH  /document-folders/{id}         documents.edit
  POST   /document-folders/{id}/move    documents.move
  POST   /document-folders/{id}/archive   documents.edit
  POST   /document-folders/{id}/unarchive documents.edit

Permission split per §R3.0:
  - Folder READS follow the owner-surface view permission (e.g.
    supplier_documents.view for supplier-owned folders) so finance —
    which holds supplier_documents.view but not documents.view — can
    load the folder tree without a silent 403.
  - Folder WRITES (create/rename/archive/unarchive) gate on the platform-
    wide documents.create / documents.edit actions.
  - MOVES gate on documents.move (granted to project_manager + finance
    via the §R4.3 union rule).

Cross-tenant / cross-owner / cross-supplier lookups return 404 (NOT 403)
per house leak-as-404 pattern.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_principal, Principal
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.services import document_folders as svc

log = logging.getLogger(__name__)

router = APIRouter(prefix="/document-folders", tags=["document_folders"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FolderCreateBody(BaseModel):
    owner_type: str = Field(..., min_length=1, max_length=40)
    owner_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: Optional[uuid.UUID] = None


class FolderRenameBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class FolderMoveBody(BaseModel):
    new_parent_id: Optional[uuid.UUID] = None


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


def _gate_owner_view(perms: UserPermissions, owner_type: str) -> None:
    """Resolve + enforce the owner-surface view permission per §R3.0."""
    try:
        view_code = svc.owner_view_perm(owner_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _check_perm(perms, view_code)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
def create_endpoint(
    body: FolderCreateBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "documents.create")

    payload: dict[str, Any] = body.model_dump(exclude_unset=True)
    payload["owner_id"] = str(body.owner_id)
    if body.parent_id is not None:
        payload["parent_id"] = str(body.parent_id)
    try:
        row = svc.create_folder(
            db, principal.tenant_id, principal.user.id, payload,
            request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise_folder(row, file_count=0)


@router.get("")
def list_tree_endpoint(
    owner_type: str = Query(...),
    owner_id: uuid.UUID = Query(...),
    include_archived: bool = Query(False),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _gate_owner_view(perms, owner_type)

    try:
        tree = svc.list_folder_tree(
            db, principal.tenant_id, owner_type, owner_id,
            include_archived=include_archived,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Owner not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"items": tree}


@router.get("/{folder_id}")
def get_endpoint(
    folder_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    row = svc.get_folder(db, principal.tenant_id, folder_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Gate on the OWNING surface's view perm (per §R3.0). Folder owner-type
    # is resolved AFTER the row load so the gate uses the row's real
    # owner_type — not a query param.
    _gate_owner_view(perms, row.owner_type)
    return svc.get_folder_detail(db, principal.tenant_id, folder_id)


@router.patch("/{folder_id}")
def rename_endpoint(
    folder_id: uuid.UUID,
    body: FolderRenameBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "documents.edit")

    try:
        row = svc.rename_folder(
            db, principal.tenant_id, principal.user.id,
            folder_id, body.name, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise_folder(row)


@router.post("/{folder_id}/move")
def move_endpoint(
    folder_id: uuid.UUID,
    body: FolderMoveBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "documents.move")

    try:
        row = svc.move_folder(
            db, principal.tenant_id, principal.user.id,
            folder_id, body.new_parent_id, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise_folder(row)


@router.post("/{folder_id}/archive")
def archive_endpoint(
    folder_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "documents.edit")

    try:
        row = svc.set_folder_archived(
            db, principal.tenant_id, principal.user.id, folder_id,
            archived=True, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise_folder(row)


@router.post("/{folder_id}/unarchive")
def unarchive_endpoint(
    folder_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_perm(perms, "documents.edit")

    try:
        row = svc.set_folder_archived(
            db, principal.tenant_id, principal.user.id, folder_id,
            archived=False, request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Folder not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise_folder(row)
