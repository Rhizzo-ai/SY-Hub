"""Roles + Permissions router.

Read endpoints (roles.view) are the original published contract — their
response shapes are frozen (§R3.6, B83). Mutation endpoints (roles.admin)
landed in B83 (Chat 52): batch grant save with revocation precedence,
custom-role lifecycle, mandatory audit logging, super_admin lock-out.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete as sa_delete, func, insert as sa_insert, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.rbac import (
    Permission, Role, UserRole, role_permissions,
    role_permission_revocations,
)
from app.auth import require_permission
from app.services.audit import field_diff, record_audit


router = APIRouter(tags=["roles"])


class PermissionOut(BaseModel):
    id: uuid.UUID
    code: str
    resource: str
    action: str
    description: str
    is_sensitive: bool


class RoleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    is_system_role: bool
    priority: int
    permission_count: int
    user_count: int


class RoleDetail(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    is_system_role: bool
    priority: int
    permissions: list[PermissionOut]
    user_count: int


# ---------- B83 request models ----------

class PermissionBatchChange(BaseModel):
    role_id: uuid.UUID
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_add_remove_overlap(self):
        overlap = set(self.add) & set(self.remove)
        if overlap:
            raise ValueError(
                f"codes present in both add and remove: {', '.join(sorted(overlap))}"
            )
        return self


class PermissionsBatchIn(BaseModel):
    changes: list[PermissionBatchChange] = Field(..., min_length=1, max_length=50)

    @model_validator(mode="after")
    def _no_duplicate_roles(self):
        ids = [c.role_id for c in self.changes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate role_id entries across changes")
        return self


def _validate_role_name(v: str) -> str:
    v = (v or "").strip()
    if not (3 <= len(v) <= 100):
        raise ValueError("name must be 3-100 characters after trimming")
    return v


def _validate_role_description(v: str) -> str:
    v = (v or "").strip()
    if not (1 <= len(v) <= 500):
        raise ValueError("description must be 1-500 characters")
    return v


class RoleCreateIn(BaseModel):
    name: str
    description: str
    priority: Optional[int] = Field(default=None, ge=1, le=100)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _validate_role_name(v)

    @field_validator("description")
    @classmethod
    def _description(cls, v: str) -> str:
        return _validate_role_description(v)


class RolePatchIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=100)

    @field_validator("name")
    @classmethod
    def _name(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _validate_role_name(v)

    @field_validator("description")
    @classmethod
    def _description(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _validate_role_description(v)

    @model_validator(mode="after")
    def _at_least_one_field(self):
        if self.name is None and self.description is None and self.priority is None:
            raise ValueError("at least one of name, description, priority is required")
        return self


# ---------- B83 helpers ----------

# Custom-role default-grant exclusions (amended D5): destructive action
# verbs that a new role must NOT receive even when the permission row is
# not flagged is_sensitive (e.g. cost_codes.delete).
DEFAULT_GRANT_EXCLUDED_ACTIONS = ("delete", "admin", "void")


def _slugify_role_name(name: str) -> str:
    """Slugify per §R3.3: lowercase, whitespace runs → `_`, strip chars
    outside [a-z0-9_], collapse repeated `_`, trim edge `_`, max 50."""
    s = name.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    return s[:50]


def _role_detail(db: Session, r: Role) -> RoleDetail:
    perms = db.scalars(
        select(Permission).join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .where(role_permissions.c.role_id == r.id)
        .order_by(Permission.code.asc())
    ).all()
    user_cnt = db.scalar(
        select(func.count(func.distinct(UserRole.user_id))).where(
            UserRole.role_id == r.id, UserRole.status == "Active"
        )
    ) or 0
    return RoleDetail(
        id=r.id, code=r.code, name=r.name, description=r.description,
        is_system_role=r.is_system_role, priority=r.priority,
        permissions=[PermissionOut.model_validate(p, from_attributes=True) for p in perms],
        user_count=user_cnt,
    )


# ---------- Roles ----------

roles_router = APIRouter(prefix="/roles", tags=["roles"])


@roles_router.get("", response_model=list[RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    _=Depends(require_permission("roles.view")),
):
    roles = db.scalars(select(Role).order_by(Role.priority.asc(), Role.name.asc())).all()
    out: list[RoleOut] = []
    for r in roles:
        perm_cnt = db.scalar(
            select(func.count()).select_from(role_permissions).where(role_permissions.c.role_id == r.id)
        ) or 0
        user_cnt = db.scalar(
            select(func.count(func.distinct(UserRole.user_id))).where(
                UserRole.role_id == r.id, UserRole.status == "Active"
            )
        ) or 0
        out.append(RoleOut(
            id=r.id, code=r.code, name=r.name, description=r.description,
            is_system_role=r.is_system_role, priority=r.priority,
            permission_count=perm_cnt, user_count=user_cnt,
        ))
    return out


# ---------------------------------------------------------------------------
# B83 mutation endpoints — roles.admin only.
#
# Route declaration order (defensive convention, §R3.2): ALL static paths
# (`/permissions-batch`, the create `POST ""`) are declared BEFORE the
# dynamic `/{role_id}` routes so a future `{role_id}` route with a matching
# method can never shadow them silently.
# ---------------------------------------------------------------------------


@roles_router.post("/permissions-batch")
def permissions_batch(
    body: PermissionsBatchIn,
    request: Request,
    db: Session = Depends(get_db),
    perms=Depends(require_permission("roles.admin")),
):
    """Batch grant save (D9). Transactional — all-or-nothing across the
    ENTIRE request. Removes write revocation rows (D1 precedence); adds
    heal them. super_admin is fully locked (D3). One Permission_Change
    audit row per mutated role (D7)."""
    # ---- validation pass (no writes) ----
    roles_by_id: dict[uuid.UUID, Role] = {}
    for ch in body.changes:
        role = db.get(Role, ch.role_id)
        if role is None:
            raise HTTPException(404, f"Role not found: {ch.role_id}")
        if role.code == "super_admin":
            raise HTTPException(
                403, "super_admin grants are locked and cannot be modified"
            )
        roles_by_id[ch.role_id] = role

    all_codes: set[str] = set()
    for ch in body.changes:
        all_codes |= set(ch.add) | set(ch.remove)
    perms_by_code: dict[str, Permission] = {}
    if all_codes:
        rows = db.scalars(
            select(Permission).where(Permission.code.in_(all_codes))
        ).all()
        perms_by_code = {p.code: p for p in rows}
    unknown = sorted(all_codes - set(perms_by_code))
    if unknown:
        raise HTTPException(
            422, f"Unknown permission code(s): {', '.join(unknown)}"
        )

    actor_id = perms.user_id

    # ---- write pass — single transaction, all-or-nothing ----
    try:
        for ch in body.changes:
            role = roles_by_id[ch.role_id]
            granted_ids = {
                pid for (pid,) in db.execute(
                    select(role_permissions.c.permission_id).where(
                        role_permissions.c.role_id == role.id
                    )
                )
            }
            applied_adds: list[str] = []
            applied_removes: list[str] = []

            for code in ch.remove:
                perm = perms_by_code[code]
                if perm.id in granted_ids:
                    db.execute(
                        sa_delete(role_permissions).where(
                            role_permissions.c.role_id == role.id,
                            role_permissions.c.permission_id == perm.id,
                        )
                    )
                # Upsert the revocation row (delete + insert refreshes
                # revoked_at and re-stamps revoked_by_user_id). Removing an
                # ungranted code is idempotent and STILL writes the row —
                # the operator can pre-empt a future seed grant.
                db.execute(
                    sa_delete(role_permission_revocations).where(
                        role_permission_revocations.c.role_id == role.id,
                        role_permission_revocations.c.permission_id == perm.id,
                    )
                )
                db.execute(
                    sa_insert(role_permission_revocations).values(
                        role_id=role.id,
                        permission_id=perm.id,
                        revoked_by_user_id=actor_id,
                    )
                )
                applied_removes.append(code)

            for code in ch.add:
                perm = perms_by_code[code]
                if perm.id not in granted_ids:
                    db.execute(
                        sa_insert(role_permissions).values(
                            role_id=role.id, permission_id=perm.id
                        )
                    )
                # Re-granting heals the override (delete any revocation).
                db.execute(
                    sa_delete(role_permission_revocations).where(
                        role_permission_revocations.c.role_id == role.id,
                        role_permission_revocations.c.permission_id == perm.id,
                    )
                )
                applied_adds.append(code)

            db.flush()
            record_audit(
                db,
                action="Permission_Change",
                resource_type="role",
                resource_id=role.id,
                actor_user_id=actor_id,
                request=request,
                field_changes=[
                    {"field": "permissions_added", "old": None,
                     "new": sorted(applied_adds)},
                    {"field": "permissions_removed", "old": None,
                     "new": sorted(applied_removes)},
                ],
                metadata={
                    "role_code": role.code,
                    "added_count": len(applied_adds),
                    "removed_count": len(applied_removes),
                    "source": "b83_admin",
                },
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"updated": [_role_detail(db, roles_by_id[ch.role_id]) for ch in body.changes]}


@roles_router.post("", response_model=RoleDetail, status_code=201)
def create_role(
    body: RoleCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    perms=Depends(require_permission("roles.admin")),
):
    """Create a custom role (D5). Default grants = every permission where
    is_sensitive = false AND action NOT IN (delete, admin, void), inserted
    atomically at creation."""
    slug = _slugify_role_name(body.name)
    if not slug:
        raise HTTPException(
            422, "Role name produces an empty code after slugification"
        )
    collision = db.scalar(select(Role).where(Role.code == slug))
    if collision is not None:
        raise HTTPException(
            409,
            f"A role with code '{slug}' already exists — choose a different name",
        )

    actor_id = perms.user_id
    try:
        role = Role(
            code=slug,
            name=body.name,
            description=body.description,
            is_system_role=False,
            priority=body.priority if body.priority is not None else 40,
        )
        db.add(role)
        db.flush()

        # Amended D5 default grants — one bulk fetch, one bulk insert.
        default_perm_ids = db.scalars(
            select(Permission.id).where(
                Permission.is_sensitive.is_(False),
                Permission.action.not_in(DEFAULT_GRANT_EXCLUDED_ACTIONS),
            )
        ).all()
        if default_perm_ids:
            db.execute(
                sa_insert(role_permissions),
                [{"role_id": role.id, "permission_id": pid}
                 for pid in default_perm_ids],
            )
        db.flush()

        record_audit(
            db,
            action="Create",
            resource_type="role",
            resource_id=role.id,
            actor_user_id=actor_id,
            request=request,
            metadata={
                "role_code": slug,
                "default_grants": len(default_perm_ids),
                "source": "b83_admin",
            },
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return _role_detail(db, role)


@roles_router.get("/{role_id}", response_model=RoleDetail)
def get_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(require_permission("roles.view")),
):
    r = db.get(Role, role_id)
    if r is None:
        raise HTTPException(404, "Role not found")
    perms = db.scalars(
        select(Permission).join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .where(role_permissions.c.role_id == r.id)
        .order_by(Permission.code.asc())
    ).all()
    user_cnt = db.scalar(
        select(func.count(func.distinct(UserRole.user_id))).where(
            UserRole.role_id == r.id, UserRole.status == "Active"
        )
    ) or 0
    return RoleDetail(
        id=r.id, code=r.code, name=r.name, description=r.description,
        is_system_role=r.is_system_role, priority=r.priority,
        permissions=[PermissionOut.model_validate(p, from_attributes=True) for p in perms],
        user_count=user_cnt,
    )


@roles_router.patch("/{role_id}", response_model=RoleDetail)
def patch_role(
    role_id: uuid.UUID,
    body: RolePatchIn,
    request: Request,
    db: Session = Depends(get_db),
    perms=Depends(require_permission("roles.admin")),
):
    """Rename/edit a custom role (D6). System-role metadata is locked.
    `code` is immutable — renaming never re-slugs."""
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(404, "Role not found")
    if role.is_system_role:
        raise HTTPException(409, "System role metadata is locked")

    before = {
        "name": role.name,
        "description": role.description,
        "priority": role.priority,
    }
    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.priority is not None:
        role.priority = body.priority
    after = {
        "name": role.name,
        "description": role.description,
        "priority": role.priority,
    }

    actor_id = perms.user_id
    try:
        db.flush()
        record_audit(
            db,
            action="Update",
            resource_type="role",
            resource_id=role.id,
            actor_user_id=actor_id,
            request=request,
            field_changes=field_diff(before, after),
            metadata={"role_code": role.code, "source": "b83_admin"},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _role_detail(db, role)


@roles_router.delete("/{role_id}", status_code=204)
def delete_role(
    role_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    perms=Depends(require_permission("roles.admin")),
):
    """Delete a custom role (D6). System roles are undeletable. ANY
    user_roles row (any status) blocks deletion — mirrors the DB-level
    FK ondelete=RESTRICT exactly."""
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(404, "Role not found")
    if role.is_system_role:
        raise HTTPException(409, "System roles cannot be deleted")

    assigned_users = db.scalar(
        select(func.count(func.distinct(UserRole.user_id))).where(
            UserRole.role_id == role.id
        )
    ) or 0
    if assigned_users > 0:
        raise HTTPException(
            409,
            f"Role is assigned to {assigned_users} user(s); "
            f"remove the assignments first",
        )

    rid = role.id
    rcode = role.code
    actor_id = perms.user_id
    try:
        # role_permissions + role_permission_revocations cascade via FK.
        db.delete(role)
        db.flush()
        record_audit(
            db,
            action="Delete",
            resource_type="role",
            resource_id=rid,
            actor_user_id=actor_id,
            request=request,
            metadata={"role_code": rcode, "source": "b83_admin"},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return Response(status_code=204)


# ---------- Permissions ----------

perms_router = APIRouter(prefix="/permissions", tags=["permissions"])


@perms_router.get("", response_model=list[PermissionOut])
def list_permissions(
    db: Session = Depends(get_db),
    _=Depends(require_permission("roles.view")),
):
    perms = db.scalars(
        select(Permission).order_by(Permission.resource.asc(), Permission.action.asc())
    ).all()
    return [PermissionOut.model_validate(p, from_attributes=True) for p in perms]
