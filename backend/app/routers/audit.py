"""Audit log read API — Prompt 1.4, Section F/G.

Writes to `audit_log` happen inside business routers via
`app.services.audit.record_audit`. This module serves the READ side:
paginated list + detail + per-resource timelines + CSV/JSON export.

Scoping contract (per spec Section G):
  - `audit.admin`   → unscoped (reads all tenants-entities-projects)
  - `audit.view`    → scoped to the user's entity scope per their user_role
  - `audit.export`  → additive to view (does NOT grant more rows)

Rows with entity_id=NULL (user-level changes, system actions, login events)
are considered *tenant-level* and are visible to anyone with `audit.view`.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from app.auth import Principal
from app.auth.deps import get_current_principal, get_current_user, require_permission
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.deps import get_current_tenant_id
from app.models.audit import AuditLog
from app.models.user import User


router = APIRouter(prefix="/audit", tags=["audit"])
EXPORT_ROW_CAP = 10_000


# --------------------------------------------------------------------------
# Serialisation
# --------------------------------------------------------------------------

class AuditLogRow(BaseModel):
    id: uuid.UUID
    created_at: datetime
    action: str
    resource_type: str
    resource_id: uuid.UUID
    entity_id: Optional[uuid.UUID]
    project_id: Optional[uuid.UUID]
    actor_user_id: Optional[uuid.UUID]
    actor_name: Optional[str]
    actor_email: Optional[str]
    impersonator_user_id: Optional[uuid.UUID]
    impersonator_name: Optional[str]
    field_changes: list[dict]
    metadata: dict
    ip_address: Optional[str]
    user_agent: Optional[str]
    session_id: Optional[uuid.UUID]
    summary: str


class AuditLogList(BaseModel):
    items: list[AuditLogRow]
    total: int
    page: int
    page_size: int


def _actor_name(user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    fn = (user.first_name or "").strip()
    ln = (user.last_name or "").strip()
    full = " ".join(p for p in (fn, ln) if p)
    return full or user.email


def _summarise(row: AuditLog) -> str:
    meta = row.metadata_json or {}
    changes = row.field_changes or []
    if row.action == "Create":
        return f"Created {row.resource_type}"
    if row.action == "Delete":
        reason = meta.get("reason")
        suffix = f" ({reason})" if reason else ""
        return f"Deleted {row.resource_type}{suffix}"
    if row.action == "Update":
        if meta.get("mfa_action"):
            return f"MFA {meta['mfa_action']}"
        if changes:
            fields = ", ".join(c.get("field", "?") for c in changes[:5])
            more = f" +{len(changes) - 5} more" if len(changes) > 5 else ""
            return f"Updated {row.resource_type}: {fields}{more}"
        return f"Updated {row.resource_type}"
    if row.action == "Status_Change":
        reason = meta.get("reason")
        return f"Status change ({reason})" if reason else "Status change"
    if row.action == "Permission_Change":
        return f"Permission change on {row.resource_type}"
    if row.action == "Login":
        return "Successful login"
    if row.action == "Logout":
        return "User logout"
    return row.action.replace("_", " ")


def _serialise(row: AuditLog, actor: Optional[User], impersonator: Optional[User]) -> AuditLogRow:
    return AuditLogRow(
        id=row.id,
        created_at=row.created_at,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        entity_id=row.entity_id,
        project_id=row.project_id,
        actor_user_id=row.actor_user_id,
        actor_name=_actor_name(actor),
        actor_email=actor.email if actor else None,
        impersonator_user_id=row.impersonator_user_id,
        impersonator_name=_actor_name(impersonator),
        field_changes=list(row.field_changes or []),
        metadata=dict(row.metadata_json or {}),
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        session_id=row.session_id,
        summary=_summarise(row),
    )


# --------------------------------------------------------------------------
# Scope helpers
# --------------------------------------------------------------------------

def _apply_scope(q, user: User, tenant_id: uuid.UUID, db: Session):
    """Return the query limited to rows this user may see.

    - audit.admin → no scope applied.
    - audit.view  → entity_id IS NULL OR entity_id IN (user's effective scope).
    """
    perms: UserPermissions = compute_effective_permissions(db, user.id, tenant_id)
    if "audit.admin" in perms.all_permissions or perms.is_super_admin:
        return q
    allowed_entities = perms.effective_entity_ids("audit.view")
    if allowed_entities is None:
        # Unscoped audit.view (entity_scope='All' on the user_role).
        return q
    if not allowed_entities:
        # Scoped but empty — user can see only tenant-level rows.
        return q.where(AuditLog.entity_id.is_(None))
    return q.where(or_(
        AuditLog.entity_id.is_(None),
        AuditLog.entity_id.in_(list(allowed_entities)),
    ))


def _hydrate_actors(db: Session, rows: list[AuditLog]) -> dict[uuid.UUID, User]:
    ids: set[uuid.UUID] = set()
    for r in rows:
        if r.actor_user_id:
            ids.add(r.actor_user_id)
        if r.impersonator_user_id:
            ids.add(r.impersonator_user_id)
    if not ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(list(ids)))).all()
    return {u.id: u for u in users}


# --------------------------------------------------------------------------
# Query builder
# --------------------------------------------------------------------------

def _build_base_query(
    db: Session,
    user: User,
    tenant_id: uuid.UUID,
    *,
    resource_type: Optional[str],
    resource_id: Optional[uuid.UUID],
    actor_user_id: Optional[uuid.UUID],
    entity_id: Optional[uuid.UUID],
    project_id: Optional[uuid.UUID],
    action: Optional[list[str]],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
):
    q = select(AuditLog)
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)
    if resource_id:
        q = q.where(AuditLog.resource_id == resource_id)
    if actor_user_id:
        q = q.where(AuditLog.actor_user_id == actor_user_id)
    if entity_id:
        q = q.where(AuditLog.entity_id == entity_id)
    if project_id:
        q = q.where(AuditLog.project_id == project_id)
    if action:
        q = q.where(AuditLog.action.in_(action))
    if date_from:
        q = q.where(AuditLog.created_at >= date_from)
    if date_to:
        q = q.where(AuditLog.created_at <= date_to)
    return _apply_scope(q, user, tenant_id, db)


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@router.get("", response_model=AuditLogList)
def list_audit(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    resource_type: Optional[str] = None,
    resource_id: Optional[uuid.UUID] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    entity_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    action: Optional[list[str]] = Query(None),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    _=Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
):
    q = _build_base_query(
        db, current, tenant_id,
        resource_type=resource_type, resource_id=resource_id,
        actor_user_id=actor_user_id, entity_id=entity_id, project_id=project_id,
        action=action, date_from=date_from, date_to=date_to,
    )
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.order_by(AuditLog.created_at.desc())
         .offset((page - 1) * page_size)
         .limit(page_size)
    ).all()
    actors = _hydrate_actors(db, rows)
    items = [
        _serialise(r, actors.get(r.actor_user_id), actors.get(r.impersonator_user_id))
        for r in rows
    ]
    return AuditLogList(items=items, total=total, page=page, page_size=page_size)


@router.get("/export.csv", response_class=PlainTextResponse)
def export_csv(
    request: Request,
    resource_type: Optional[str] = None,
    resource_id: Optional[uuid.UUID] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    entity_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    action: Optional[list[str]] = Query(None),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    _=Depends(require_permission("audit.view", "audit.export")),
    db: Session = Depends(get_db),
):
    q = _build_base_query(
        db, current, tenant_id,
        resource_type=resource_type, resource_id=resource_id,
        actor_user_id=actor_user_id, entity_id=entity_id, project_id=project_id,
        action=action, date_from=date_from, date_to=date_to,
    )
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if total > EXPORT_ROW_CAP:
        raise HTTPException(
            status_code=400,
            detail=f"Export exceeds cap of {EXPORT_ROW_CAP} rows "
                   f"({total} rows matched). Narrow the filters.",
        )
    rows = db.scalars(q.order_by(AuditLog.created_at.desc()).limit(EXPORT_ROW_CAP)).all()
    actors = _hydrate_actors(db, rows)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "timestamp_utc", "action", "resource_type", "resource_id",
        "entity_id", "project_id", "actor_user_id", "actor_email",
        "impersonator_user_id", "ip_address", "user_agent",
        "field_changes_json", "metadata_json",
    ])
    for r in rows:
        actor = actors.get(r.actor_user_id) if r.actor_user_id else None
        w.writerow([
            r.created_at.astimezone(timezone.utc).isoformat(),
            r.action, r.resource_type, str(r.resource_id),
            str(r.entity_id) if r.entity_id else "",
            str(r.project_id) if r.project_id else "",
            str(r.actor_user_id) if r.actor_user_id else "",
            actor.email if actor else "",
            str(r.impersonator_user_id) if r.impersonator_user_id else "",
            r.ip_address or "", r.user_agent or "",
            json.dumps(list(r.field_changes or [])),
            json.dumps(dict(r.metadata_json or {})),
        ])
    return PlainTextResponse(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )


@router.get("/export.json")
def export_json(
    request: Request,
    resource_type: Optional[str] = None,
    resource_id: Optional[uuid.UUID] = None,
    actor_user_id: Optional[uuid.UUID] = None,
    entity_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    action: Optional[list[str]] = Query(None),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    _=Depends(require_permission("audit.view", "audit.export")),
    db: Session = Depends(get_db),
):
    q = _build_base_query(
        db, current, tenant_id,
        resource_type=resource_type, resource_id=resource_id,
        actor_user_id=actor_user_id, entity_id=entity_id, project_id=project_id,
        action=action, date_from=date_from, date_to=date_to,
    )
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    if total > EXPORT_ROW_CAP:
        raise HTTPException(
            status_code=400,
            detail=f"Export exceeds cap of {EXPORT_ROW_CAP} rows "
                   f"({total} rows matched). Narrow the filters.",
        )
    rows = db.scalars(q.order_by(AuditLog.created_at.desc()).limit(EXPORT_ROW_CAP)).all()
    actors = _hydrate_actors(db, rows)
    payload = [
        _serialise(r, actors.get(r.actor_user_id), actors.get(r.impersonator_user_id)).model_dump(mode="json")
        for r in rows
    ]
    return JSONResponse(
        content={"items": payload, "total": len(payload)},
        headers={"Content-Disposition": 'attachment; filename="audit-log.json"'},
    )


@router.get("/{audit_id}", response_model=AuditLogRow)
def get_audit_row(
    audit_id: uuid.UUID,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    _=Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
):
    row = db.get(AuditLog, audit_id)
    if not row:
        raise HTTPException(404, "audit row not found")
    # Scope check — re-run the scope filter so non-admin can't see rows
    # for entities they lack access to.
    q = _apply_scope(select(AuditLog.id).where(AuditLog.id == audit_id), current, tenant_id, db)
    if not db.scalar(q):
        raise HTTPException(404, "audit row not found")
    actor = db.get(User, row.actor_user_id) if row.actor_user_id else None
    imp = db.get(User, row.impersonator_user_id) if row.impersonator_user_id else None
    return _serialise(row, actor, imp)
