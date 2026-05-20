"""Project number prefixes router — Chat 24 §R1 (Prompt 2.5).

Mounted under /api/v1/projects/{project_id}/number-prefixes (v1 prefix
applied at include time in server.py).

Endpoints:
  GET   /projects/{project_id}/number-prefixes      pos.view
  POST  /projects/{project_id}/number-prefixes      pos.edit
  PATCH /projects/{project_id}/number-prefixes/{id} pos.edit

Permissions:
  The `pos.*` permission block is added in R2 (migration 0033). For R1
  we additionally accept the legacy alias `suppliers.create` on the
  write path so that tests can run without R2 in place. The exact
  catalogue lands in R2 — this is a temporary bridge documented in
  Future_Tasks (Track 2 §15).

Tenant scoping:
  Pattern α via _visible_project_ids. We delegate to the same helper
  that budgets/actuals use. The project must (a) belong to the user's
  tenant, and (b) be in the user's visible set (or the user holds an
  all-projects scope grant).
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_principal, Principal
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.models.projects import Project
from app.services import number_prefixes as svc
from app.services.budgets import _visible_project_ids


router = APIRouter(prefix="/projects", tags=["number_prefixes"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PrefixCreateBody(BaseModel):
    entity_type: str = Field(..., pattern="^(po|bill)$")
    middle_prefix: Optional[str] = Field(None, max_length=8)
    description: Optional[str] = Field(None, max_length=200)
    is_default: bool = Field(False)


class PrefixUpdateBody(BaseModel):
    middle_prefix: Optional[str] = Field(None, max_length=8)
    description: Optional[str] = Field(None, max_length=200)
    is_default: Optional[bool] = Field(None)
    is_archived: Optional[bool] = Field(None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# R1 bridge: pos.* permissions don't exist yet (R2/0033 adds them).
# For now accept suppliers.create / suppliers.edit as the gating signal
# for the prefix routes — this is the same persona (PM / Finance /
# Director). The R2 migration will swap these aliases for the real
# pos.view / pos.edit codes and update this gate.
_PREFIX_VIEW_PERMS = ("pos.view", "suppliers.view")
_PREFIX_EDIT_PERMS = ("pos.edit", "suppliers.edit")


def _check_any(perms: UserPermissions, codes: tuple[str, ...]) -> None:
    if not any(perms.has(c) for c in codes):
        raise HTTPException(
            status_code=403,
            detail=f"Missing any of permissions: {', '.join(codes)}",
        )


def _perm_dep(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> tuple[Principal, UserPermissions]:
    perms = compute_effective_permissions(db, principal.user.id, principal.tenant_id)
    return principal, perms


def _resolve_project(
    db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Project:
    """Pattern α: 404 if invisible, 403 if not in tenant.

    Returns the Project row for further use. Raises HTTPException
    appropriately.
    """
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.tenant_id == tenant_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    allowed = _visible_project_ids(db, user_id, tenant_id)
    if allowed is not None and project_id not in allowed:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/{project_id}/number-prefixes")
def list_endpoint(
    project_id: uuid.UUID,
    entity_type: Optional[str] = Query(None, pattern="^(po|bill)$"),
    include_archived: bool = Query(False),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_any(perms, _PREFIX_VIEW_PERMS)
    _resolve_project(db, principal.tenant_id, principal.user.id, project_id)

    rows = svc.list_prefixes(
        db, project_id,
        entity_type=entity_type, include_archived=include_archived,
    )
    return {
        "items": [svc.serialise(r) for r in rows],
        "count": len(rows),
    }


@router.post("/{project_id}/number-prefixes", status_code=201)
def create_endpoint(
    project_id: uuid.UUID,
    body: PrefixCreateBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_any(perms, _PREFIX_EDIT_PERMS)
    _resolve_project(db, principal.tenant_id, principal.user.id, project_id)

    payload: dict[str, Any] = body.model_dump(exclude_unset=True)
    try:
        row = svc.create_prefix(
            db, project_id, principal.user.id, payload, request=request,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise(row)


@router.patch("/{project_id}/number-prefixes/{prefix_id}")
def patch_endpoint(
    project_id: uuid.UUID,
    prefix_id: uuid.UUID,
    body: PrefixUpdateBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _check_any(perms, _PREFIX_EDIT_PERMS)
    _resolve_project(db, principal.tenant_id, principal.user.id, project_id)

    payload: dict[str, Any] = body.model_dump(exclude_unset=True)
    try:
        row = svc.update_prefix(
            db, project_id, principal.user.id, prefix_id, payload,
            request=request,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Number prefix not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(row)
    return svc.serialise(row)
