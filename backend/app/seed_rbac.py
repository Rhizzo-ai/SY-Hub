"""RBAC seed — permissions + roles + role-permission mapping + bootstrap admin.

Idempotent: safe to run on every startup. Adds only what's missing.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select, insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.auth.passwords import hash_password
from app.models.rbac import (
    Permission,
    Role,
    UserRole,
    role_permissions,
    ACTIONS,
    RESOURCES,
)
from app.models.tenant import Tenant
from app.models.user import User

log = logging.getLogger(__name__)


# ============================================================
# Permission catalogue — tuples of (code, resource, action, description, sensitive)
#
# Only meaningful resource × action combinations. Generates ~90 permissions.
# Source of truth for the codebase — do not hardcode elsewhere.
# ============================================================

def _perms_for(resource: str, *, include: Iterable[str] | None = None,
               sensitive: set[str] | None = None) -> list[tuple[str, str, str, str, bool]]:
    """Build (code, resource, action, description, is_sensitive) tuples."""
    include = list(include) if include else list(ACTIONS)
    sensitive = sensitive or set()
    out = []
    for action in include:
        code = f"{resource}.{action}"
        desc = f"{action.replace('_', ' ').capitalize()} {resource.replace('_', ' ')}"
        out.append((code, resource, action, desc, action in sensitive or action == "view_sensitive"))
    return out


# Cross-product permissions. Each resource picks which actions apply.
PERMISSION_CATALOGUE: list[tuple[str, str, str, str, bool]] = []
PERMISSION_CATALOGUE += _perms_for(
    "entities",
    include=["view", "view_sensitive", "create", "edit", "delete", "admin"],
    sensitive={"admin"},
)
PERMISSION_CATALOGUE += _perms_for(
    "projects",
    include=["view", "view_sensitive", "create", "edit", "delete", "approve", "admin"],
)
PERMISSION_CATALOGUE += _perms_for(
    "users",
    include=["view", "view_sensitive", "create", "edit", "delete", "admin"],
    sensitive={"admin"},
)
PERMISSION_CATALOGUE += _perms_for(
    "roles",
    include=["view", "edit", "admin"],
    sensitive={"admin"},
)
PERMISSION_CATALOGUE += _perms_for(
    "audit",
    include=["view", "view_sensitive", "export", "admin"],
    sensitive={"admin"},
)
PERMISSION_CATALOGUE += _perms_for(
    "cost_codes",
    include=["view", "create", "edit", "delete", "admin"],
)
PERMISSION_CATALOGUE += _perms_for(
    "appraisals",
    include=["view", "view_sensitive", "create", "edit", "delete", "approve", "reopen"],
)
PERMISSION_CATALOGUE += _perms_for(
    "budgets",
    include=["view", "view_sensitive", "create", "edit", "approve"],
)
PERMISSION_CATALOGUE += _perms_for(
    "actuals",
    include=["view", "view_sensitive", "create", "edit", "approve"],
)
PERMISSION_CATALOGUE += _perms_for(
    "commitments",
    include=["view", "view_sensitive", "create", "edit", "approve"],
)
PERMISSION_CATALOGUE += _perms_for(
    "budget_changes",
    include=["view", "create", "edit", "approve"],
)
PERMISSION_CATALOGUE += _perms_for(
    "cash_flow",
    include=["view", "view_sensitive", "edit"],
)
PERMISSION_CATALOGUE += _perms_for(
    "programmes",
    include=["view", "edit"],
)
PERMISSION_CATALOGUE += _perms_for(
    "programme_tasks",
    include=["view", "create", "edit"],
)
PERMISSION_CATALOGUE += _perms_for(
    "documents",
    include=["view", "create", "edit", "delete"],
)
PERMISSION_CATALOGUE += _perms_for(
    "document_registers",
    include=["view", "edit"],
)
PERMISSION_CATALOGUE += _perms_for(
    "certificates",
    include=["view", "create", "edit"],
)
PERMISSION_CATALOGUE += _perms_for(
    "xero_connections",
    include=["view", "admin"],
    sensitive={"admin"},
)
PERMISSION_CATALOGUE += _perms_for(
    "xero_bills",
    include=["view"],
)
PERMISSION_CATALOGUE += _perms_for(
    "xero_invoices",
    include=["view"],
)
PERMISSION_CATALOGUE += _perms_for(
    "xero_sync",
    include=["view", "admin"],
    sensitive={"admin"},
)
PERMISSION_CATALOGUE += _perms_for(
    "system_config",
    include=["view", "edit", "admin"],
    sensitive={"admin"},
)
PERMISSION_CATALOGUE += _perms_for(
    "notifications",
    include=["view", "edit"],
)
PERMISSION_CATALOGUE += _perms_for(
    "reports",
    include=["view", "export"],
)


# ============================================================
# Roles (10)
# ============================================================

ROLE_CATALOGUE = [
    ("super_admin", "Super Administrator",
     "Full system access including security and impersonation.", True, 1),
    ("director", "Director",
     "Full group access except super-admin-only actions.", True, 10),
    ("project_manager", "Project Manager",
     "Full operational control on assigned projects.", True, 20),
    ("finance", "Finance",
     "Financial records, Xero sync, reporting access.", True, 20),
    ("site_manager", "Site Manager",
     "Programme and document access on assigned projects.", True, 30),
    ("sales", "Sales",
     "Plot and buyer records, sales reporting.", True, 30),
    ("read_only", "Read Only",
     "Can view assigned records; no edit/approve.", True, 50),
    ("investor_read_only", "Investor",
     "Dashboard and report access only; no individual record detail.", True, 50),
    ("subcontractor_portal", "Subcontractor Portal",
     "External — scoped portal access.", True, 70),
    ("consultant_portal", "Consultant Portal",
     "External — scoped portal access.", True, 70),
]


# ============================================================
# Role → permissions mapping
# ============================================================

# Helper selectors
def _codes_for(resource: str) -> set[str]:
    return {code for (code, res, *_rest) in PERMISSION_CATALOGUE if res == resource}


ALL_PERMISSION_CODES: set[str] = {code for (code, *_) in PERMISSION_CATALOGUE}

ROLE_PERMISSIONS: dict[str, set[str]] = {}

# super_admin → everything
ROLE_PERMISSIONS["super_admin"] = set(ALL_PERMISSION_CODES)

# director → all except the explicit exclusions
ROLE_PERMISSIONS["director"] = set(ALL_PERMISSION_CODES) - {
    "users.admin", "roles.admin", "audit.admin",
}

# project_manager
ROLE_PERMISSIONS["project_manager"] = {
    "projects.view", "projects.view_sensitive", "projects.edit",
    "appraisals.view", "appraisals.create", "appraisals.edit", "appraisals.approve",
    "budgets.view", "budgets.view_sensitive", "budgets.edit",
    "actuals.view", "actuals.create", "actuals.edit",
    "commitments.view", "commitments.create", "commitments.edit",
    "budget_changes.view", "budget_changes.create", "budget_changes.approve",
    "cash_flow.view", "cash_flow.edit",
    "programmes.view", "programmes.edit",
    "programme_tasks.view", "programme_tasks.create", "programme_tasks.edit",
    "documents.view", "documents.create", "documents.edit",
    "document_registers.view", "document_registers.edit",
    "certificates.view",
    "reports.view", "reports.export",
    "entities.view",
}

# finance
ROLE_PERMISSIONS["finance"] = {
    "entities.view", "entities.view_sensitive", "entities.edit",
    "projects.view", "projects.view_sensitive",
    "appraisals.view",
    "budgets.view", "budgets.view_sensitive",
    "actuals.view", "actuals.view_sensitive", "actuals.create", "actuals.edit", "actuals.approve",
    "commitments.view", "commitments.view_sensitive",
    "budget_changes.view", "budget_changes.approve",
    "cash_flow.view", "cash_flow.view_sensitive", "cash_flow.edit",
    "xero_connections.view", "xero_connections.admin",
    "xero_bills.view", "xero_invoices.view", "xero_sync.admin", "xero_sync.view",
    "reports.view", "reports.export",
    "users.view",
    "audit.view",
}

# site_manager
ROLE_PERMISSIONS["site_manager"] = {
    "projects.view",
    "programmes.view",
    "programme_tasks.view", "programme_tasks.edit",
    "documents.view", "documents.create",
    "document_registers.view", "document_registers.edit",
    "certificates.view",
    "entities.view",
}

# sales
ROLE_PERMISSIONS["sales"] = {
    "projects.view",
    "reports.view",
    "entities.view",
}

# read_only
ROLE_PERMISSIONS["read_only"] = {
    "entities.view", "projects.view", "appraisals.view", "budgets.view",
    "programmes.view", "documents.view", "reports.view",
}

# investor_read_only
ROLE_PERMISSIONS["investor_read_only"] = {
    "projects.view", "reports.view",
}

# subcontractor_portal
ROLE_PERMISSIONS["subcontractor_portal"] = {
    "documents.view", "documents.create",
}

# consultant_portal
ROLE_PERMISSIONS["consultant_portal"] = {
    "documents.view", "documents.create",
}


# ============================================================
# Seed logic
# ============================================================

def _seed_permissions(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.scalars(select(Permission)).all()}
    for code, resource, action, description, is_sensitive in PERMISSION_CATALOGUE:
        if code in existing:
            continue
        p = Permission(
            code=code, resource=resource, action=action,
            description=description, is_sensitive=is_sensitive,
        )
        db.add(p)
        db.flush()
        existing[code] = p
    return existing


def _seed_roles(db: Session) -> dict[str, Role]:
    existing = {r.code: r for r in db.scalars(select(Role)).all()}
    for code, name, description, is_system, priority in ROLE_CATALOGUE:
        if code in existing:
            continue
        r = Role(
            code=code, name=name, description=description,
            is_system_role=is_system, priority=priority,
        )
        db.add(r)
        db.flush()
        existing[code] = r
    return existing


def _seed_role_permissions(
    db: Session, perms_by_code: dict[str, Permission], roles_by_code: dict[str, Role]
) -> None:
    # Load existing role_permissions pairs
    rows = db.execute(select(role_permissions.c.role_id, role_permissions.c.permission_id)).all()
    existing_pairs = {(rid, pid) for (rid, pid) in rows}

    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        role = roles_by_code[role_code]
        for perm_code in perm_codes:
            perm = perms_by_code.get(perm_code)
            if perm is None:
                log.warning("Role %s references unknown permission %s", role_code, perm_code)
                continue
            pair = (role.id, perm.id)
            if pair in existing_pairs:
                continue
            db.execute(insert(role_permissions).values(role_id=role.id, permission_id=perm.id))
            existing_pairs.add(pair)


def _seed_bootstrap_admin(db: Session, roles_by_code: dict[str, Role], tenant: Tenant) -> None:
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD in backend/.env "
            "before first boot (required to seed the super_admin user)."
        )
    email = email.strip().lower()

    existing = db.scalars(select(User).where(User.email == email, User.tenant_id == tenant.id)).first()
    now = datetime.now(timezone.utc)
    first_name = os.environ.get("BOOTSTRAP_ADMIN_FIRST_NAME", "Super")
    last_name = os.environ.get("BOOTSTRAP_ADMIN_LAST_NAME", "Admin")

    if existing is None:
        user = User(
            tenant_id=tenant.id,
            email=email,
            email_verified=True,
            email_verified_at=now,
            password_hash=hash_password(password),
            password_algorithm="argon2id",
            password_changed_at=now,
            password_history=[],
            first_name=first_name,
            last_name=last_name,
            display_name=f"{first_name} {last_name}",
            user_type="Internal",
            status="Active",
            admin_notes="Bootstrapped super_admin (Prompt 1.2).",
        )
        db.add(user)
        db.flush()
        log.info("Bootstrapped super_admin user: %s (%s)", email, user.id)
    else:
        user = existing
        # Do NOT overwrite password on restart — admin owns lifecycle from here.

    # Ensure super_admin user_role exists for this user
    sa_role = roles_by_code["super_admin"]
    has_role = db.scalars(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == sa_role.id,
            UserRole.status == "Active",
        )
    ).first()
    if has_role is None:
        ur = UserRole(
            user_id=user.id,
            role_id=sa_role.id,
            entity_scope="All",
            project_scope="All",
            view_overrides=[],
            assigned_by_user_id=user.id,  # self-assigned at bootstrap
            status="Active",
        )
        db.add(ur)
        log.info("Granted super_admin role to bootstrap user.")


def seed_rbac() -> None:
    db = SessionLocal()
    try:
        tenant_name = os.environ.get("DEFAULT_TENANT_NAME", "SY Homes")
        tenant = db.scalar(select(Tenant).where(Tenant.name == tenant_name))
        if tenant is None:
            raise RuntimeError("Tenant must exist before RBAC seed runs.")

        perms = _seed_permissions(db)
        roles = _seed_roles(db)
        _seed_role_permissions(db, perms, roles)
        _seed_bootstrap_admin(db, roles, tenant)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
