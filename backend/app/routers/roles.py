"""Roles + Permissions read-mostly router."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.rbac import (
    Permission, Role, UserRole, role_permissions,
)
from app.auth import require_permission


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
