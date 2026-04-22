"""Users router — CRUD + role assignment + unlock + PII scrub."""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_tenant_id
from app.models.user import User, USER_TYPES, USER_STATUSES
from app.models.rbac import (
    Role, UserRole, user_role_entities, user_role_projects,
    ENTITY_SCOPES, PROJECT_SCOPES,
)
from app.auth import (
    hash_password,
    hash_token,
    get_current_user,
    require_permission,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


# ---------- Schemas ----------

class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    display_name: Optional[str] = None
    user_type: str
    status: str
    mfa_enabled: bool
    last_login_at: Optional[datetime] = None
    role_count: int = 0
    locked_until: Optional[datetime] = None
    failed_login_attempts: int = 0


class UserDetail(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    email_verified: bool
    first_name: str
    last_name: str
    display_name: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    user_type: str
    primary_entity_id: Optional[uuid.UUID] = None
    timezone: str
    locale: str
    mfa_enabled: bool
    mfa_method: Optional[str] = None
    last_login_at: Optional[datetime] = None
    failed_login_attempts: int
    locked_until: Optional[datetime] = None
    status: str
    suspended_reason: Optional[str] = None
    invited_by_user_id: Optional[uuid.UUID] = None
    invitation_sent_at: Optional[datetime] = None
    invitation_accepted_at: Optional[datetime] = None
    admin_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    roles: list[dict] = []


class UserListResponse(BaseModel):
    items: list[UserSummary]
    total: int
    page: int
    page_size: int


class UserCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    user_type: str = "Internal"
    primary_entity_id: Optional[uuid.UUID] = None
    timezone: str = "Europe/London"
    locale: str = "en-GB"
    admin_notes: Optional[str] = None


class InviteResponse(BaseModel):
    user: UserDetail
    invitation_token: str  # shown once to admin


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    job_title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    user_type: Optional[str] = None
    primary_entity_id: Optional[uuid.UUID] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None
    status: Optional[str] = None
    suspended_reason: Optional[str] = None
    admin_notes: Optional[str] = None


class RoleAssignmentCreate(BaseModel):
    role_id: uuid.UUID
    entity_scope: str = "All"
    project_scope: str = "All"
    entity_ids: list[uuid.UUID] = Field(default_factory=list)
    project_ids: list[uuid.UUID] = Field(default_factory=list)
    view_overrides: list[str] = Field(default_factory=list)
    expires_at: Optional[datetime] = None


class RoleAssignmentOut(BaseModel):
    id: uuid.UUID
    role_id: uuid.UUID
    role_code: str
    role_name: str
    entity_scope: str
    project_scope: str
    entity_ids: list[uuid.UUID] = []
    project_ids: list[uuid.UUID] = []
    view_overrides: list[str] = []
    assigned_by_user_id: uuid.UUID
    assigned_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    status: str


# ---------- Helpers ----------

def _serialise_role_assignment(db: Session, ur: UserRole) -> RoleAssignmentOut:
    role = db.get(Role, ur.role_id)
    ent_ids = [row[0] for row in db.execute(
        select(user_role_entities.c.entity_id).where(user_role_entities.c.user_role_id == ur.id)
    ).all()]
    proj_ids = [row[0] for row in db.execute(
        select(user_role_projects.c.project_id).where(user_role_projects.c.user_role_id == ur.id)
    ).all()]
    return RoleAssignmentOut(
        id=ur.id, role_id=ur.role_id,
        role_code=role.code if role else "?", role_name=role.name if role else "?",
        entity_scope=ur.entity_scope, project_scope=ur.project_scope,
        entity_ids=ent_ids, project_ids=proj_ids,
        view_overrides=ur.view_overrides or [],
        assigned_by_user_id=ur.assigned_by_user_id,
        assigned_at=ur.created_at,
        expires_at=ur.expires_at, revoked_at=ur.revoked_at,
        status=ur.status,
    )


def _user_detail(db: Session, u: User) -> UserDetail:
    urs = db.scalars(
        select(UserRole).where(UserRole.user_id == u.id)
        .order_by(UserRole.created_at.desc())
    ).all()
    return UserDetail(
        id=u.id, tenant_id=u.tenant_id, email=u.email,
        email_verified=u.email_verified,
        first_name=u.first_name, last_name=u.last_name,
        display_name=u.display_name or f"{u.first_name} {u.last_name}",
        job_title=u.job_title, phone=u.phone, avatar_url=u.avatar_url,
        user_type=u.user_type, primary_entity_id=u.primary_entity_id,
        timezone=u.timezone, locale=u.locale,
        mfa_enabled=u.mfa_enabled, mfa_method=u.mfa_method,
        last_login_at=u.last_login_at,
        failed_login_attempts=u.failed_login_attempts,
        locked_until=u.locked_until, status=u.status,
        suspended_reason=u.suspended_reason,
        invited_by_user_id=u.invited_by_user_id,
        invitation_sent_at=u.invitation_sent_at,
        invitation_accepted_at=u.invitation_accepted_at,
        admin_notes=u.admin_notes,
        created_at=u.created_at, updated_at=u.updated_at,
        roles=[_serialise_role_assignment(db, ur).model_dump() for ur in urs],
    )


# ---------- Routes ----------

@router.get("", response_model=UserListResponse)
def list_users(
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    _=Depends(require_permission("users.view")),
    q: Optional[str] = None,
    user_type: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    role_code: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str = "last_name",
    dir: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    conds = [User.tenant_id == tenant_id]
    if q:
        needle = f"%{q.strip()}%"
        conds.append(or_(
            User.email.ilike(needle),
            User.first_name.ilike(needle),
            User.last_name.ilike(needle),
            User.display_name.ilike(needle),
        ))
    if user_type:
        if user_type not in USER_TYPES:
            raise HTTPException(400, "Invalid user_type")
        conds.append(User.user_type == user_type)
    if status_filter:
        if status_filter not in USER_STATUSES:
            raise HTTPException(400, "Invalid status")
        conds.append(User.status == status_filter)
    else:
        conds.append(User.status != "Archived")

    query = select(User).where(and_(*conds))
    if role_code:
        role = db.scalars(select(Role).where(Role.code == role_code)).first()
        if role is None:
            raise HTTPException(400, "Unknown role_code")
        query = query.join(UserRole, UserRole.user_id == User.id).where(
            UserRole.role_id == role.id, UserRole.status == "Active"
        )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0

    sort_col = {
        "email": User.email, "last_name": User.last_name, "status": User.status,
        "user_type": User.user_type, "created_at": User.created_at,
        "last_login_at": User.last_login_at,
    }.get(sort, User.last_name)
    order = sort_col.desc() if dir == "desc" else sort_col.asc()

    rows = db.scalars(
        query.order_by(order, User.last_name.asc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()

    items: list[UserSummary] = []
    for u in rows:
        cnt = db.scalar(
            select(func.count()).select_from(UserRole)
            .where(UserRole.user_id == u.id, UserRole.status == "Active")
        ) or 0
        items.append(UserSummary(
            id=u.id, email=u.email,
            first_name=u.first_name, last_name=u.last_name,
            display_name=u.display_name or f"{u.first_name} {u.last_name}",
            user_type=u.user_type, status=u.status, mfa_enabled=u.mfa_enabled,
            last_login_at=u.last_login_at, role_count=cnt,
            locked_until=u.locked_until,
            failed_login_attempts=u.failed_login_attempts or 0,
        ))
    return UserListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=UserDetail)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    _=Depends(require_permission("users.view")),
):
    u = db.scalar(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    if u is None:
        raise HTTPException(404, "User not found")
    return _user_detail(db, u)


@router.post("", response_model=InviteResponse, status_code=201)
def invite_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current: User = Depends(get_current_user),
    _=Depends(require_permission("users.create")),
):
    if payload.user_type not in USER_TYPES:
        raise HTTPException(422, "Invalid user_type")
    email = payload.email.strip().lower()
    existing = db.scalars(
        select(User).where(User.email == email, User.tenant_id == tenant_id)
    ).first()
    if existing is not None:
        raise HTTPException(409, "Email already exists for this tenant")

    token_plain = secrets.token_urlsafe(32)
    # Store hashed invitation token (argon2). Bypasses user-password complexity
    # rules because a random 256-bit token has no meaningful "uppercase /
    # symbol" constraints — its entropy lives elsewhere.
    token_hash = hash_token(token_plain)

    u = User(
        tenant_id=tenant_id,
        email=email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        display_name=payload.display_name or f"{payload.first_name} {payload.last_name}",
        job_title=payload.job_title, phone=payload.phone,
        user_type=payload.user_type,
        primary_entity_id=payload.primary_entity_id,
        timezone=payload.timezone, locale=payload.locale,
        status="Pending_Invitation",
        admin_notes=payload.admin_notes,
        invitation_sent_at=datetime.now(timezone.utc),
        invitation_token_hash=token_hash,
        invitation_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_user_id=current.id,
    )
    try:
        db.add(u)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already exists for this tenant")
    db.refresh(u)
    return InviteResponse(user=_user_detail(db, u), invitation_token=token_plain)


ADMIN_EDITABLE_STATUSES = ("Active", "Suspended", "Pending_Invitation")


@router.put("/{user_id}", response_model=UserDetail)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current: User = Depends(get_current_user),
    _=Depends(require_permission("users.admin")),
):
    u = db.scalar(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    if u is None:
        raise HTTPException(404, "User not found")
    data = payload.model_dump(exclude_unset=True)

    # ---- Validation ----
    if "user_type" in data and data["user_type"] not in USER_TYPES:
        raise HTTPException(422, "Invalid user_type")

    if "status" in data:
        if data["status"] not in USER_STATUSES:
            raise HTTPException(422, "Invalid status")
        if data["status"] == "Archived":
            raise HTTPException(400, "Use /scrub_pii to archive a user")
        if data["status"] not in ADMIN_EDITABLE_STATUSES:
            raise HTTPException(422, "Status not admin-editable; allowed: " + ", ".join(ADMIN_EDITABLE_STATUSES))
        if u.id == current.id and u.status == "Active" and data["status"] != "Active":
            raise HTTPException(400, "You cannot deactivate your own account")

    # Email — unique per tenant, case-insensitive
    if "email" in data and data["email"] is not None:
        new_email = data["email"].strip().lower()
        if not new_email or "@" not in new_email or len(new_email) > 255:
            raise HTTPException(422, "Invalid email address")
        if new_email != (u.email or "").lower():
            collision = db.scalar(
                select(User).where(
                    User.tenant_id == tenant_id,
                    func.lower(User.email) == new_email,
                    User.id != u.id,
                )
            )
            if collision is not None:
                raise HTTPException(409, "Email already in use by another user in this tenant")
        data["email"] = new_email

    # ---- Apply changes + track diff ----
    changed: list[str] = []
    email_changed = False
    for k, v in data.items():
        if getattr(u, k, None) != v:
            changed.append(k)
            if k == "email":
                email_changed = True
            setattr(u, k, v)

    if not changed:
        return _user_detail(db, u)

    # Force re-verification if email changed. Full re-verification flow
    # lands with Prompt 1.3's email infrastructure; for now just flip the
    # flag so downstream code knows.
    if email_changed:
        u.email_verified = False
        u.email_verified_at = None

    # Interim audit stamp (replaced by audit_events in Prompt 1.4).
    stamp = (
        f"[Edited by {current.email} ({current.id}) at "
        f"{datetime.now(timezone.utc).isoformat()}: {', '.join(sorted(changed))}]"
    )
    u.admin_notes = f"{(u.admin_notes or '').rstrip()}\n{stamp}".strip()

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email already in use by another user in this tenant")
    db.refresh(u)
    logging.getLogger("syhomes.auth").info(
        "user_edited actor=%s actor_id=%s target=%s target_id=%s fields=%s",
        current.email, current.id, u.email, u.id, ",".join(sorted(changed)),
    )
    return _user_detail(db, u)


@router.post("/{user_id}/unlock", status_code=204)
def unlock_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current: User = Depends(get_current_user),
    _=Depends(require_permission("users.admin")),
):
    u = db.scalar(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    if u is None:
        raise HTTPException(404, "User not found")

    was_locked = (
        (u.locked_until is not None and u.locked_until > datetime.now(timezone.utc))
        or (u.failed_login_attempts or 0) > 0
        or (u.lockout_level or 0) > 0
    )
    if not was_locked:
        raise HTTPException(400, "User is not locked")

    u.failed_login_attempts = 0
    u.locked_until = None
    u.lockout_level = 0
    # Until Prompt 1.4's audit_events table lands, stamp the actor into
    # admin_notes so the action is still traceable in-place.
    stamp = (
        f"[Unlocked by {current.email} ({current.id}) at "
        f"{datetime.now(timezone.utc).isoformat()}]"
    )
    u.admin_notes = f"{(u.admin_notes or '').rstrip()}\n{stamp}".strip()
    db.commit()
    logging.getLogger("syhomes.auth").info(
        "user_unlocked actor=%s actor_id=%s target=%s target_id=%s",
        current.email, current.id, u.email, u.id,
    )


@router.post("/{user_id}/scrub_pii", status_code=204)
def scrub_user_pii(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current: User = Depends(get_current_user),
    _=Depends(require_permission("users.admin")),
):
    if user_id == current.id:
        raise HTTPException(400, "Cannot scrub your own PII")
    u = db.scalar(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    if u is None:
        raise HTTPException(404, "User not found")
    short_id = str(u.id)[:8]
    u.first_name = "[Deleted User"
    u.last_name = f"{short_id}]"
    u.display_name = f"[Deleted User {short_id}]"
    u.email = f"deleted+{short_id}@syhomes.invalid"
    u.phone = None
    u.avatar_url = None
    u.job_title = None
    u.admin_notes = (u.admin_notes or "") + f"\n[PII scrubbed at {datetime.now(timezone.utc).isoformat()}]"
    u.status = "Archived"
    u.archived_at = datetime.now(timezone.utc)
    u.password_hash = None
    u.password_history = []
    u.mfa_enabled = False
    u.mfa_secret_encrypted = None
    u.mfa_backup_codes_encrypted = None
    db.commit()


# ---------- Role assignment ----------

@router.post("/{user_id}/roles", response_model=RoleAssignmentOut, status_code=201)
def assign_role(
    user_id: uuid.UUID,
    payload: RoleAssignmentCreate,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current: User = Depends(get_current_user),
    _=Depends(require_permission("users.edit", "roles.view")),
):
    if payload.entity_scope not in ENTITY_SCOPES:
        raise HTTPException(422, "Invalid entity_scope")
    if payload.project_scope not in PROJECT_SCOPES:
        raise HTTPException(422, "Invalid project_scope")

    u = db.scalar(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    if u is None:
        raise HTTPException(404, "User not found")
    role = db.get(Role, payload.role_id)
    if role is None:
        raise HTTPException(404, "Role not found")

    # Prevent granting super_admin without users.admin
    from app.auth import compute_effective_permissions
    current_perms = compute_effective_permissions(db, current.id, tenant_id)
    if role.code == "super_admin" and not current_perms.has("users.admin"):
        raise HTTPException(403, "Only super_admin can grant super_admin")

    ur = UserRole(
        user_id=u.id, role_id=role.id,
        entity_scope=payload.entity_scope,
        project_scope=payload.project_scope,
        view_overrides=payload.view_overrides,
        assigned_by_user_id=current.id,
        expires_at=payload.expires_at,
        status="Active",
    )
    db.add(ur)
    db.flush()

    if payload.entity_scope == "Specific":
        if not payload.entity_ids:
            raise HTTPException(422, "entity_ids required when entity_scope=Specific")
        for eid in payload.entity_ids:
            db.execute(user_role_entities.insert().values(user_role_id=ur.id, entity_id=eid))
    if payload.project_scope == "Specific":
        if not payload.project_ids:
            raise HTTPException(422, "project_ids required when project_scope=Specific")
        for pid in payload.project_ids:
            db.execute(user_role_projects.insert().values(user_role_id=ur.id, project_id=pid))

    db.commit()
    db.refresh(ur)
    return _serialise_role_assignment(db, ur)


@router.delete("/{user_id}/roles/{user_role_id}", status_code=204)
def revoke_role(
    user_id: uuid.UUID,
    user_role_id: uuid.UUID,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current: User = Depends(get_current_user),
    _=Depends(require_permission("users.edit")),
):
    ur = db.get(UserRole, user_role_id)
    if ur is None or ur.user_id != user_id:
        raise HTTPException(404, "Assignment not found")
    if ur.status == "Revoked":
        return
    ur.status = "Revoked"
    ur.revoked_at = datetime.now(timezone.utc)
    ur.revoked_by_user_id = current.id
    ur.revoked_reason = reason
    db.commit()
