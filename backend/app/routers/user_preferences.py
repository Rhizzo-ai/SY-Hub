"""User preferences router — Chat 23 Build Pack A R1.4.

All routes mount under /api/v1/me/preferences/{surface_key} (v1 prefix
set at include time in server.py).

Endpoints (6):
  GET    /me/preferences/{surface_key}                Snapshot: current + views
  PUT    /me/preferences/{surface_key}                Autosave current state
  GET    /me/preferences/{surface_key}/views/{name}   Read a saved view
  POST   /me/preferences/{surface_key}/views          Create a saved view
  PUT    /me/preferences/{surface_key}/views/{name}   Overwrite a saved view
  DELETE /me/preferences/{surface_key}/views/{name}   Delete a saved view

Auth: all endpoints require an authenticated session. The implicit scope
is `WHERE user_id = current_user.id` — no permission check beyond
authentication, because preferences are owned by the user.

Audit: by design (Build Pack §R1.4) the autosave PUT is NOT audited
(high-volume column-resize-style events). Named view CUD IS audited:
Create on POST, Update on PUT, Delete on DELETE.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.models.user import User
from app.schemas.user_preferences import (
    CurrentPayloadIn, SavedViewIn, SavedViewUpdateIn,
    SurfaceSnapshotOut, UserPreferenceOut,
)
from app.services.audit import record_audit
from app.services.user_preferences import (
    UserPreferenceConflictError, UserPreferenceNotFoundError,
    create_view, delete_view, get_current, get_view, list_views,
    set_current, update_view,
)


router = APIRouter(prefix="/me/preferences", tags=["user-preferences"])


# ----------------------------------------------------------------------
# GET snapshot: current state + all named views
# ----------------------------------------------------------------------
@router.get("/{surface_key}", response_model=SurfaceSnapshotOut)
def get_snapshot(
    surface_key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SurfaceSnapshotOut:
    current = get_current(db, user_id=user.id, surface_key=surface_key)
    views = list_views(db, user_id=user.id, surface_key=surface_key)
    return SurfaceSnapshotOut(
        surface_key=surface_key,
        current=(current.payload if current is not None else {}),
        views=[UserPreferenceOut.model_validate(v) for v in views],
    )


# ----------------------------------------------------------------------
# PUT current (autosave) — NOT audited
# ----------------------------------------------------------------------
@router.put("/{surface_key}", response_model=UserPreferenceOut)
def put_current(
    surface_key: str,
    body: CurrentPayloadIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferenceOut:
    row = set_current(
        db, user_id=user.id, surface_key=surface_key,
        payload=body.payload,
    )
    db.commit()
    db.refresh(row)
    return UserPreferenceOut.model_validate(row)


# ----------------------------------------------------------------------
# Saved-view endpoints (Create/Read/Update/Delete) — audited
# ----------------------------------------------------------------------
@router.get(
    "/{surface_key}/views/{name}", response_model=UserPreferenceOut,
)
def get_named_view(
    surface_key: str, name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferenceOut:
    row = get_view(
        db, user_id=user.id, surface_key=surface_key, name=name,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="View not found")
    return UserPreferenceOut.model_validate(row)


@router.post(
    "/{surface_key}/views", response_model=UserPreferenceOut,
    status_code=201,
)
def post_named_view(
    surface_key: str,
    body: SavedViewIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferenceOut:
    try:
        row = create_view(
            db, user_id=user.id, surface_key=surface_key,
            name=body.name, payload=body.payload,
        )
    except UserPreferenceConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    record_audit(
        db, action="Create", resource_type="user_preference",
        resource_id=row.id, actor_user_id=user.id,
        metadata={
            "surface_key": surface_key, "name": body.name,
            "kind": "saved_view",
        },
        request=request,
    )
    db.commit()
    db.refresh(row)
    return UserPreferenceOut.model_validate(row)


@router.put(
    "/{surface_key}/views/{name}", response_model=UserPreferenceOut,
)
def put_named_view(
    surface_key: str, name: str,
    body: SavedViewUpdateIn,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferenceOut:
    try:
        row = update_view(
            db, user_id=user.id, surface_key=surface_key,
            name=name, payload=body.payload,
        )
    except UserPreferenceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    record_audit(
        db, action="Update", resource_type="user_preference",
        resource_id=row.id, actor_user_id=user.id,
        metadata={
            "surface_key": surface_key, "name": name,
            "kind": "saved_view",
        },
        request=request,
    )
    db.commit()
    db.refresh(row)
    return UserPreferenceOut.model_validate(row)


@router.delete(
    "/{surface_key}/views/{name}", status_code=204,
    response_class=Response,
)
def delete_named_view(
    surface_key: str, name: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    # Resolve to get the id BEFORE delete so the audit row has it.
    row = get_view(
        db, user_id=user.id, surface_key=surface_key, name=name,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="View not found")
    row_id = row.id

    deleted = delete_view(
        db, user_id=user.id, surface_key=surface_key, name=name,
    )
    if not deleted:
        # Race: someone deleted between get_view and delete_view. Treat
        # as 404 — the delete contract is "the view is gone after the
        # call returns 204" and another actor satisfied that already.
        raise HTTPException(status_code=404, detail="View not found")

    record_audit(
        db, action="Delete", resource_type="user_preference",
        resource_id=row_id, actor_user_id=user.id,
        metadata={
            "surface_key": surface_key, "name": name,
            "kind": "saved_view",
        },
        request=request,
    )
    db.commit()
    return Response(status_code=204)
