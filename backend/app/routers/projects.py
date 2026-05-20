"""Projects + team members API — Prompt 1.5."""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Principal
from app.auth.deps import get_current_principal, get_current_user, require_permission
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.deps import get_current_tenant_id
from app.models.audit import AuditLog
from app.models.projects import (
    Project, ProjectTeamMember,
    PROJECT_TYPES, PROJECT_STAGES, PROJECT_STATUSES, TEAM_ROLES,
    LAND_OWNERSHIP, TENURES, LAND_TYPES, PLANNING_TYPES, PLANNING_STATUSES,
)
from app.models.rbac import UserRole, user_role_projects
from app.models.user import User
from app.services.audit import field_diff, record_audit
from app.services.project_financials import refresh_financials
from app.services.project_stage import (
    FORWARD_TRANSITIONS, derived_status, is_allowed_forward,
)
from app.services.projects import (
    derive_planning_expiry, has_project_dependents,
    next_project_code, reconcile_area, validate_code_override,
)


router = APIRouter(prefix="/projects", tags=["projects"])

log = logging.getLogger(__name__)


# ==========================================================================
# Schemas
# ==========================================================================

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    project_type: str
    primary_entity_id: uuid.UUID
    construction_entity_id: Optional[uuid.UUID] = None
    parent_project_id: Optional[uuid.UUID] = None
    land_ownership_method: str
    site_address: str
    site_postcode: str = Field(max_length=10)
    local_authority: Optional[str] = None
    site_area_ha: Optional[Decimal] = None
    site_area_acres: Optional[Decimal] = None
    tenure: str = "Freehold"
    lease_years_remaining: Optional[int] = None
    land_type: Optional[str] = None
    planning_ref: Optional[str] = None
    planning_type: Optional[str] = None
    planning_status: Optional[str] = None
    planning_approval_date: Optional[date] = None
    planning_expiry_date: Optional[date] = None
    implementation_required: bool = True
    s106_required: Optional[bool] = False
    cil_required: Optional[bool] = False
    vat_opt_to_tax: Optional[bool] = False
    vat_opt_to_tax_date: Optional[date] = None
    units_target: Optional[int] = None
    affordable_housing_pct: Optional[Decimal] = None
    target_start_date: Optional[date] = None
    target_pc_date: Optional[date] = None
    project_lead_user_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    project_code: Optional[str] = None  # override

    @field_validator("project_type")
    @classmethod
    def _ptype(cls, v): return _ensure_in(v, PROJECT_TYPES, "project_type")
    @field_validator("land_ownership_method")
    @classmethod
    def _low(cls, v): return _ensure_in(v, LAND_OWNERSHIP, "land_ownership_method")
    @field_validator("tenure")
    @classmethod
    def _ten(cls, v): return _ensure_in(v, TENURES, "tenure")


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    project_type: Optional[str] = None
    primary_entity_id: Optional[uuid.UUID] = None
    construction_entity_id: Optional[uuid.UUID] = None
    parent_project_id: Optional[uuid.UUID] = None
    land_ownership_method: Optional[str] = None
    site_address: Optional[str] = None
    site_postcode: Optional[str] = None
    local_authority: Optional[str] = None
    site_area_ha: Optional[Decimal] = None
    site_area_acres: Optional[Decimal] = None
    tenure: Optional[str] = None
    lease_years_remaining: Optional[int] = None
    land_type: Optional[str] = None
    planning_ref: Optional[str] = None
    planning_type: Optional[str] = None
    planning_status: Optional[str] = None
    planning_approval_date: Optional[date] = None
    planning_expiry_date: Optional[date] = None
    implementation_required: Optional[bool] = None
    s106_required: Optional[bool] = None
    cil_required: Optional[bool] = None
    vat_opt_to_tax: Optional[bool] = None
    vat_opt_to_tax_date: Optional[date] = None
    units_target: Optional[int] = None
    affordable_housing_pct: Optional[Decimal] = None
    target_start_date: Optional[date] = None
    target_pc_date: Optional[date] = None
    actual_start_date: Optional[date] = None
    actual_pc_date: Optional[date] = None
    project_lead_user_id: Optional[uuid.UUID] = None
    notes: Optional[str] = None
    dead_reason: Optional[str] = None


class StageAdvanceRequest(BaseModel):
    new_stage: str
    dead_reason: Optional[str] = None


class StageOverrideRequest(BaseModel):
    new_stage: str
    reason: str = Field(min_length=10)
    dead_reason: Optional[str] = None


class TeamMemberAdd(BaseModel):
    user_id: uuid.UUID
    role_on_project: str
    is_primary: bool = False
    notes: Optional[str] = None

    @field_validator("role_on_project")
    @classmethod
    def _rop(cls, v): return _ensure_in(v, TEAM_ROLES, "role_on_project")


def _ensure_in(v, allowed, fname):
    if v not in allowed:
        raise ValueError(f"{fname} must be one of {list(allowed)}")
    return v


# ==========================================================================
# Serialisers
# ==========================================================================

FIN_FIELDS = ("gdv_actual", "build_cost_actual", "all_in_cost_actual",
              "profit_actual", "margin_actual_pct", "financials_refreshed_at")


def _serialise(p: Project, perms: UserPermissions) -> dict:
    can_fin = "projects.view_sensitive" in perms.all_permissions or perms.is_super_admin
    d = {
        "id": p.id, "project_code": p.project_code, "name": p.name,
        "project_type": p.project_type,
        "primary_entity_id": p.primary_entity_id,
        "construction_entity_id": p.construction_entity_id,
        "parent_project_id": p.parent_project_id,
        "land_ownership_method": p.land_ownership_method,
        "site_address": p.site_address, "site_postcode": p.site_postcode,
        "local_authority": p.local_authority,
        "site_area_ha": p.site_area_ha, "site_area_acres": p.site_area_acres,
        "tenure": p.tenure, "lease_years_remaining": p.lease_years_remaining,
        "land_type": p.land_type,
        "planning_ref": p.planning_ref, "planning_type": p.planning_type,
        "planning_status": p.planning_status,
        "planning_approval_date": p.planning_approval_date,
        "planning_expiry_date": p.planning_expiry_date,
        "implementation_required": p.implementation_required,
        "s106_required": p.s106_required, "cil_required": p.cil_required,
        "vat_opt_to_tax": p.vat_opt_to_tax, "vat_opt_to_tax_date": p.vat_opt_to_tax_date,
        "units_target": p.units_target, "units_actual": p.units_actual,
        "affordable_housing_pct": p.affordable_housing_pct,
        "target_start_date": p.target_start_date, "target_pc_date": p.target_pc_date,
        "actual_start_date": p.actual_start_date, "actual_pc_date": p.actual_pc_date,
        "current_stage": p.current_stage, "stage_entered_at": p.stage_entered_at,
        "status": p.status, "dead_reason": p.dead_reason,
        "project_lead_user_id": p.project_lead_user_id,
        "notes": p.notes, "created_at": p.created_at, "updated_at": p.updated_at,
    }
    if can_fin:
        for f in FIN_FIELDS:
            d[f] = getattr(p, f)
    return d


# ==========================================================================
# Scope helpers
# ==========================================================================

def _visible_project_ids(db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID) -> Optional[set[uuid.UUID]]:
    """Union of projects visible across the user's active user_roles.

    Returns:
      None → unscoped (user has at least one role with project_scope='All'
              and the projects.view permission).
      set() → empty; user has no visible projects.
      set(ids) → explicit inclusion list.
    """
    now = datetime.now(timezone.utc)
    roles = db.scalars(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.status == "Active",
            or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
        )
    ).all()
    ids: set[uuid.UUID] = set()
    has_all = False
    for ur in roles:
        if ur.project_scope == "All":
            has_all = True
        elif ur.project_scope == "Specific":
            rows = db.execute(
                select(user_role_projects.c.project_id)
                .where(user_role_projects.c.user_role_id == ur.id)
            ).all()
            ids.update(r[0] for r in rows)
        # project_scope == "None": contributes nothing.
    if has_all:
        return None
    return ids


def _apply_scope(q, db: Session, user: User, tenant_id: uuid.UUID,
                 perms: UserPermissions):
    if perms.is_super_admin:
        return q
    allowed = _visible_project_ids(db, user.id, tenant_id)
    if allowed is None:
        return q
    if not allowed:
        # Force empty.
        return q.where(Project.id.in_([uuid.uuid4()]))
    return q.where(Project.id.in_(list(allowed)))


# ==========================================================================
# CRUD
# ==========================================================================

@router.get("")
def list_projects(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    project_type: Optional[list[str]] = Query(None),
    current_stage: Optional[list[str]] = Query(None),
    status_f: Optional[list[str]] = Query(None, alias="status"),
    primary_entity_id: Optional[uuid.UUID] = None,
    project_lead_user_id: Optional[uuid.UUID] = None,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.view")),
    db: Session = Depends(get_db),
):
    query = select(Project)
    if q:
        like = f"%{q}%"
        query = query.where(or_(
            Project.name.ilike(like), Project.project_code.ilike(like),
            Project.site_address.ilike(like), Project.site_postcode.ilike(like),
        ))
    if project_type:
        query = query.where(Project.project_type.in_(project_type))
    if current_stage:
        query = query.where(Project.current_stage.in_(current_stage))
    if status_f:
        query = query.where(Project.status.in_(status_f))
    if primary_entity_id:
        query = query.where(Project.primary_entity_id == primary_entity_id)
    if project_lead_user_id:
        query = query.where(Project.project_lead_user_id == project_lead_user_id)
    query = _apply_scope(query, db, current, tenant_id, perms)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(Project.created_at.desc())
             .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_serialise(r, perms) for r in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.post("", status_code=201)
def create_project(
    payload: ProjectCreate,
    request: Request,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.create")),
    db: Session = Depends(get_db),
):
    code = payload.project_code
    if code:
        if not validate_code_override(code):
            raise HTTPException(400, "project_code must match ^[A-Z0-9]{3}-\\d{3,}$")
    else:
        code = next_project_code(db, payload.name)

    ha, acres = reconcile_area(payload.site_area_ha, payload.site_area_acres)
    expiry = payload.planning_expiry_date or derive_planning_expiry(
        payload.planning_type, payload.planning_approval_date,
    )
    data = payload.model_dump(exclude_unset=True, exclude={"project_code"})
    data["site_area_ha"] = ha
    data["site_area_acres"] = acres
    data["planning_expiry_date"] = expiry

    p = Project(
        project_code=code,
        created_by_user_id=current.id,
        **data,
    )
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "project_code already in use")
    record_audit(
        db, action="Create", resource_type="projects", resource_id=p.id,
        actor_user_id=current.id, entity_id=p.primary_entity_id, project_id=p.id,
        field_changes=field_diff({}, {"project_code": p.project_code, "name": p.name,
                                      "project_type": p.project_type,
                                      "current_stage": p.current_stage,
                                      "status": p.status}),
        request=request,
    )

    # Auto-populate project_cost_codes per project_type (Prompt 1.6 §F).
    from app.services.cost_codes import auto_populate_project_cost_codes
    counts = auto_populate_project_cost_codes(db, p)
    record_audit(
        db, action="Create", resource_type="project_cost_codes",
        resource_id=p.id, actor_user_id=current.id,
        entity_id=p.primary_entity_id, project_id=p.id,
        field_changes=[],
        metadata={"kind": "bulk_auto_populate", **counts},
        request=request,
    )

    # Chat 24 §R1 (Prompt 2.5) — seed null-middle default prefixes for both
    # entity types (po + bill). Failure here is logged but does not block
    # the project create; the operator can manually add prefixes via
    # /api/v1/projects/{id}/number-prefixes if the seed fails.
    try:
        from app.services.number_prefixes import seed_default_prefixes
        seed_default_prefixes(db, p.id, current.id, request=request)
    except Exception:  # noqa: BLE001 — never block project create
        log.exception(
            "Chat 24 R1 prefix auto-seed failed for project %s — continuing",
            p.id,
        )

    db.commit()
    db.refresh(p)
    return _serialise(p, perms)


def _get_or_403(db: Session, project_id: uuid.UUID, user: User,
                tenant_id: uuid.UUID, perms: UserPermissions) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, tenant_id)
        if allowed is not None and p.id not in allowed:
            raise HTTPException(404, "Project not found")
    return p


@router.get("/{project_id}")
def get_project(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.view")),
    db: Session = Depends(get_db),
):
    p = _get_or_403(db, project_id, current, tenant_id, perms)
    return _serialise(p, perms)


@router.put("/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    request: Request,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.edit")),
    db: Session = Depends(get_db),
):
    # project_code is immutable — reject at the raw body level because
    # ProjectUpdate pydantic schema deliberately doesn't expose it.
    try:
        body = await request.json()
    except Exception:
        body = {}
    if isinstance(body, dict) and "project_code" in body:
        raise HTTPException(400, "project_code is immutable after creation")
    p = _get_or_403(db, project_id, current, tenant_id, perms)
    before = {k: getattr(p, k) for k in payload.model_dump(exclude_unset=True).keys()}
    data = payload.model_dump(exclude_unset=True)

    # Area reconciliation.
    if "site_area_ha" in data or "site_area_acres" in data:
        ha, acres = reconcile_area(
            data.get("site_area_ha") if "site_area_ha" in data else p.site_area_ha,
            data.get("site_area_acres") if "site_area_acres" in data else p.site_area_acres,
        )
        data["site_area_ha"] = ha
        data["site_area_acres"] = acres

    # Planning expiry auto-calc + manual-override detection.
    recalc_needed = (
        ("planning_approval_date" in data or "planning_type" in data)
        and "planning_expiry_date" not in data
    )
    manual_override = False
    if "planning_expiry_date" in data:
        formula = derive_planning_expiry(
            data.get("planning_type", p.planning_type),
            data.get("planning_approval_date", p.planning_approval_date),
        )
        if formula and data["planning_expiry_date"] and data["planning_expiry_date"] != formula:
            manual_override = True
    if recalc_needed:
        data["planning_expiry_date"] = derive_planning_expiry(
            data.get("planning_type", p.planning_type),
            data.get("planning_approval_date", p.planning_approval_date),
        )

    for k, v in data.items():
        setattr(p, k, v)

    after = {k: getattr(p, k) for k in before.keys()}
    changes = field_diff(before, after)
    meta: dict = {}
    if manual_override:
        meta["planning_expiry_manual_override"] = True
    if changes:
        record_audit(
            db, action="Update", resource_type="projects", resource_id=p.id,
            actor_user_id=current.id, entity_id=p.primary_entity_id, project_id=p.id,
            field_changes=changes, metadata=meta, request=request,
        )
    db.commit()
    db.refresh(p)
    return _serialise(p, perms)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.delete")),
    db: Session = Depends(get_db),
):
    p = _get_or_403(db, project_id, current, tenant_id, perms)
    if has_project_dependents(db, p.id):
        raise HTTPException(
            409,
            f"Cannot delete project {p.project_code} — dependent records exist. "
            f"Use status change instead (mark Dead with reason, or Complete).",
        )
    record_audit(
        db, action="Delete", resource_type="projects", resource_id=p.id,
        actor_user_id=current.id, entity_id=p.primary_entity_id,
        metadata={"project_code": p.project_code, "name": p.name},
        request=request,
    )
    db.delete(p)
    db.commit()


# ==========================================================================
# Stage transitions
# ==========================================================================

@router.post("/{project_id}/stage/advance")
def advance_stage(
    project_id: uuid.UUID,
    payload: StageAdvanceRequest,
    request: Request,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.edit")),
    db: Session = Depends(get_db),
):
    _ensure_in(payload.new_stage, PROJECT_STAGES, "new_stage")
    p = _get_or_403(db, project_id, current, tenant_id, perms)
    old = p.current_stage
    if not is_allowed_forward(old, payload.new_stage):
        raise HTTPException(
            409,
            "Forward-only transition violated. Use override path if this is deliberate.",
        )
    if payload.new_stage == "Dead" and not payload.dead_reason:
        raise HTTPException(400, "dead_reason required when transitioning to Dead")
    p.current_stage = payload.new_stage
    p.stage_entered_at = datetime.now(timezone.utc)
    if payload.new_stage == "Dead":
        p.status = "Dead"
        p.dead_reason = payload.dead_reason
    elif payload.new_stage == "Closed":
        p.status = "Complete"
    record_audit(
        db, action="Stage_Change", resource_type="projects", resource_id=p.id,
        actor_user_id=current.id, entity_id=p.primary_entity_id, project_id=p.id,
        metadata={"override": False, "old_stage": old, "new_stage": payload.new_stage},
        request=request,
    )
    db.commit()
    db.refresh(p)
    return _serialise(p, perms)


@router.post("/{project_id}/stage/override")
def override_stage(
    project_id: uuid.UUID,
    payload: StageOverrideRequest,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: Session = Depends(get_db),
):
    # Explicit super_admin gate (NOT inherited via projects.edit).
    perms = compute_effective_permissions(db, current.id, tenant_id)
    if not perms.is_super_admin:
        raise HTTPException(403, "Stage override requires super_admin")
    _ensure_in(payload.new_stage, PROJECT_STAGES, "new_stage")

    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    old = p.current_stage
    if payload.new_stage == old:
        raise HTTPException(400, "new_stage must differ from current stage")
    if payload.new_stage == "Dead" and not payload.dead_reason:
        raise HTTPException(400, "dead_reason required when overriding to Dead")
    p.current_stage = payload.new_stage
    p.stage_entered_at = datetime.now(timezone.utc)
    p.status = derived_status(payload.new_stage, p.status)
    if payload.new_stage == "Dead":
        p.dead_reason = payload.dead_reason

    director_notifications = [
        {
            "type": "Stage_Override",
            "project_id": str(p.id),
            "project_code": p.project_code,
            "old_stage": old, "new_stage": payload.new_stage,
            "reason": payload.reason,
            "actor_user_id": str(current.id),
        }
    ]
    record_audit(
        db, action="Stage_Change", resource_type="projects", resource_id=p.id,
        actor_user_id=current.id, entity_id=p.primary_entity_id, project_id=p.id,
        metadata={
            "override": True, "override_reason": payload.reason,
            "actor_role": "super_admin",
            "old_stage": old, "new_stage": payload.new_stage,
            "director_notifications": director_notifications,
        },
        request=request,
    )

    # Prompt 1.7 retro-wire: dispatch System_Announcement High to all
    # directors. Excludes the actor (acting super_admin) themselves.
    from app.models.rbac import Role, UserRole
    from app.services.notifications import safe_dispatch

    director_roles = db.scalars(
        select(Role).where(Role.code.in_(["director"]))
    ).all()
    director_role_ids = {r.id for r in director_roles}
    director_user_ids: set[uuid.UUID] = set()
    if director_role_ids:
        urs = db.scalars(
            select(UserRole).where(
                UserRole.role_id.in_(director_role_ids),
                UserRole.status == "Active",
            )
        ).all()
        director_user_ids = {ur.user_id for ur in urs} - {current.id}
    title = f"Stage override on {p.project_code}: {old} → {payload.new_stage}"
    body = (
        f"Super-admin override executed on **{p.project_code}**.\n\n"
        f"Old stage: {old}\nNew stage: {payload.new_stage}\n"
        f"Reason: {payload.reason}"
    )
    for uid in director_user_ids:
        safe_dispatch(
            db,
            recipient_user_id=uid,
            notification_type="System_Announcement",
            title=title,
            body=body,
            priority="High",
            related_resource_type="projects",
            related_resource_id=p.id,
            action_url=f"/projects/{p.id}",
            action_label="View project",
            actor_user_id=current.id,
            request=request,
        )

    db.commit()
    db.refresh(p)
    return _serialise(p, perms)


# ==========================================================================
# Team members
# ==========================================================================

@router.get("/{project_id}/team")
def list_team(
    project_id: uuid.UUID,
    history: bool = False,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.view")),
    db: Session = Depends(get_db),
):
    _get_or_403(db, project_id, current, tenant_id, perms)
    q = select(ProjectTeamMember).where(ProjectTeamMember.project_id == project_id)
    if not history:
        q = q.where(ProjectTeamMember.removed_at.is_(None))
    rows = db.scalars(q.order_by(ProjectTeamMember.assigned_at.desc())).all()
    return [
        {
            "id": t.id, "project_id": t.project_id, "user_id": t.user_id,
            "role_on_project": t.role_on_project, "is_primary": t.is_primary,
            "assigned_by_user_id": t.assigned_by_user_id,
            "assigned_at": t.assigned_at, "removed_at": t.removed_at,
            "notes": t.notes,
        }
        for t in rows
    ]


@router.post("/{project_id}/team", status_code=201)
def add_team_member(
    project_id: uuid.UUID,
    payload: TeamMemberAdd,
    request: Request,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.edit")),
    db: Session = Depends(get_db),
):
    p = _get_or_403(db, project_id, current, tenant_id, perms)
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    tm = ProjectTeamMember(
        project_id=p.id, user_id=payload.user_id,
        role_on_project=payload.role_on_project,
        is_primary=payload.is_primary,
        assigned_by_user_id=current.id, notes=payload.notes,
    )
    db.add(tm)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig)
        if "ux_team_one_active_primary_per_role" in msg:
            raise HTTPException(409, "Another primary member already exists for this role")
        raise HTTPException(409, "Integrity error")

    # Project_Lead + primary → sync projects.project_lead_user_id.
    if payload.role_on_project == "Project_Lead" and payload.is_primary:
        p.project_lead_user_id = payload.user_id

    record_audit(
        db, action="Create", resource_type="project_team_members",
        resource_id=tm.id, actor_user_id=current.id,
        entity_id=p.primary_entity_id, project_id=p.id,
        metadata={
            "user_id": str(payload.user_id),
            "role_on_project": payload.role_on_project,
            "is_primary": payload.is_primary,
        },
        request=request,
    )
    db.commit()
    db.refresh(tm)
    return {
        "id": tm.id, "project_id": tm.project_id, "user_id": tm.user_id,
        "role_on_project": tm.role_on_project, "is_primary": tm.is_primary,
        "assigned_at": tm.assigned_at, "notes": tm.notes,
    }


@router.delete("/{project_id}/team/{team_member_id}", status_code=204)
def remove_team_member(
    project_id: uuid.UUID,
    team_member_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.edit")),
    db: Session = Depends(get_db),
):
    p = _get_or_403(db, project_id, current, tenant_id, perms)
    tm = db.get(ProjectTeamMember, team_member_id)
    if tm is None or tm.project_id != project_id:
        raise HTTPException(404, "Team member not found")
    if tm.removed_at is not None:
        return
    tm.removed_at = datetime.now(timezone.utc)
    if tm.role_on_project == "Project_Lead" and tm.is_primary \
            and p.project_lead_user_id == tm.user_id:
        p.project_lead_user_id = None
    record_audit(
        db, action="Delete", resource_type="project_team_members",
        resource_id=tm.id, actor_user_id=current.id,
        entity_id=p.primary_entity_id, project_id=p.id,
        metadata={"reason": "team_remove"},
        request=request,
    )
    db.commit()


# ==========================================================================
# Financials refresh (stub)
# ==========================================================================

@router.post("/{project_id}/financials/refresh")
def refresh_project_financials(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    perms: UserPermissions = Depends(require_permission("projects.view_sensitive")),
    db: Session = Depends(get_db),
):
    p = _get_or_403(db, project_id, current, tenant_id, perms)
    result = refresh_financials(db, p)
    db.commit()
    return result
