"""Effective-permissions computation + FastAPI require_permission dependency.

Computed per-request via a single JOIN (no caching in 1.2 per agreed
simplification; caching will land when sessions arrive in 1.3).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

from fastapi import Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.rbac import (
    Permission,
    Role,
    UserRole,
    role_permissions,
    user_role_entities,
    user_role_projects,
)


@dataclass
class UserPermissions:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    # All unscoped permissions (granted through any Active user_role).
    all_permissions: set[str] = field(default_factory=set)
    # Permissions granted with entity_scope='All'.
    all_entity_perms: set[str] = field(default_factory=set)
    # perm_code -> set(entity_id) for Specific-scoped grants.
    entity_scoped: dict[str, set[uuid.UUID]] = field(default_factory=dict)
    # perm_code -> set(project_id) for Specific-scoped grants.
    project_scoped: dict[str, set[uuid.UUID]] = field(default_factory=dict)
    # Code flags for all-projects grants.
    all_project_perms: set[str] = field(default_factory=set)
    # True if the user has the `users.admin` permission.
    is_super_admin: bool = False

    def has(self, code: str) -> bool:
        return code in self.all_permissions

    def has_on_entity(self, code: str, entity_id: uuid.UUID | None) -> bool:
        """True if this permission applies to the given entity (or is unscoped)."""
        if code not in self.all_permissions:
            return False
        if code in self.all_entity_perms:
            return True
        if entity_id is None:
            # No specific entity being checked — unscoped grant required.
            return False
        return entity_id in self.entity_scoped.get(code, set())

    def entity_ids_with(self, code: str) -> set[uuid.UUID] | None:
        """Return the entity-ids the user can exercise `code` on.

        `None` means unscoped (all entities). Empty set means none.
        """
        if code not in self.all_permissions:
            return set()
        if code in self.all_entity_perms:
            return None
        return set(self.entity_scoped.get(code, set()))


def compute_effective_permissions(
    db: Session,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> UserPermissions:
    """Compute a user's union-of-active-role-permissions minus view_overrides."""
    up = UserPermissions(user_id=user_id, tenant_id=tenant_id)
    now = datetime.now(timezone.utc)

    # Find all Active, non-expired, non-revoked user_roles for this user.
    urs = db.scalars(
        select(UserRole)
        .where(
            UserRole.user_id == user_id,
            UserRole.status == "Active",
            UserRole.revoked_at.is_(None),
        )
    ).all()

    active_urs: list[UserRole] = []
    for ur in urs:
        if ur.expires_at is not None and ur.expires_at <= now:
            continue
        active_urs.append(ur)

    if not active_urs:
        return up

    # Bulk-load permissions per role
    role_ids = [ur.role_id for ur in active_urs]
    rows = db.execute(
        select(role_permissions.c.role_id, Permission.code, Role.code.label("role_code"))
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .join(Role, Role.id == role_permissions.c.role_id)
        .where(role_permissions.c.role_id.in_(role_ids))
    ).all()
    role_to_perms: dict[uuid.UUID, list[str]] = {}
    role_codes: dict[uuid.UUID, str] = {}
    for role_id, perm_code, role_code in rows:
        role_to_perms.setdefault(role_id, []).append(perm_code)
        role_codes[role_id] = role_code

    # Preload entity scopes and project scopes for each user_role
    ur_entities_rows = db.execute(
        select(user_role_entities.c.user_role_id, user_role_entities.c.entity_id)
        .where(
            user_role_entities.c.user_role_id.in_([ur.id for ur in active_urs])
        )
    ).all()
    ur_to_entities: dict[uuid.UUID, set[uuid.UUID]] = {}
    for ur_id, ent_id in ur_entities_rows:
        ur_to_entities.setdefault(ur_id, set()).add(ent_id)

    ur_projects_rows = db.execute(
        select(user_role_projects.c.user_role_id, user_role_projects.c.project_id)
        .where(
            user_role_projects.c.user_role_id.in_([ur.id for ur in active_urs])
        )
    ).all()
    ur_to_projects: dict[uuid.UUID, set[uuid.UUID]] = {}
    for ur_id, p_id in ur_projects_rows:
        ur_to_projects.setdefault(ur_id, set()).add(p_id)

    for ur in active_urs:
        role_perms = set(role_to_perms.get(ur.role_id, []))
        overrides = set(ur.view_overrides or [])
        granted = role_perms - overrides
        if not granted:
            continue
        up.all_permissions |= granted

        if role_codes.get(ur.role_id) == "super_admin":
            up.is_super_admin = True

        if ur.entity_scope == "All":
            up.all_entity_perms |= granted
        else:
            scope_entities = ur_to_entities.get(ur.id, set())
            for code in granted:
                up.entity_scoped.setdefault(code, set()).update(scope_entities)

        if ur.project_scope == "All":
            up.all_project_perms |= granted
        elif ur.project_scope == "Specific":
            scope_projects = ur_to_projects.get(ur.id, set())
            for code in granted:
                up.project_scoped.setdefault(code, set()).update(scope_projects)
        # 'None' → no project rights; still keep unscoped perms for
        # non-project resources (entities, users, etc.).

    return up


# ---------- FastAPI dep factory ----------
# The real require_permission(*codes) factory is in app.auth.deps where the
# Principal / DB dep wiring lives. Import it from there:
#   from app.auth.deps import require_permission
