"""Cost-codes router — Prompt 1.6.

Endpoints under /api/cost-codes (sections, codes, subcategories, entity
mapping). Project-level toggles live under /api/projects/{id}/cost-codes
in app/routers/projects.py-adjacent helpers (registered alongside the
cost-codes router for proximity).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    UserPermissions, get_current_user, require_permission,
)
from app.db import get_db
from app.deps import get_current_tenant_id
from app.models.cost_codes import (
    CostCode, CostCodeSection, CostCodeSubcategory,
    CostCodeEntityMapping, ProjectCostCode,
    P_AND_L_CATEGORIES, DEFAULT_ENTITY_VALUES, VAT_TREATMENTS,
    COST_CODE_STATUSES, SUBCAT_UNITS,
)
from app.models.entity import Entity
from app.models.projects import Project
from app.models.user import User
from app.services.audit import field_diff, record_audit
from app.services.cost_codes import (
    LOCKED_FIELDS_WHEN_IN_USE, SECTION_LOCKED_FIELDS_WHEN_IN_USE,
    SECTION_LOCKED_FIELDS_WHEN_HAS_CHILDREN,
    auto_populate_project_cost_codes, can_entity_use_cost_code,
    cost_code_block_reasons, detect_replaced_by_cycle,
    is_cost_code_in_use, is_section_in_use, reactivate_cost_code,
    section_block_reasons, section_has_children,
    project_type_enabled_predicate, validate_cost_code_format,
    validate_section_for_cost_code, validate_section_parent,
    validate_subcategory_format,
)


router = APIRouter(tags=["cost_codes"])


# ==========================================================================
# Schemas
# ==========================================================================

class SectionRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    display_order: int
    is_direct_cost: bool
    default_p_and_l_category: str
    # B88 Pack 1 — hierarchy fields. parent_section_id is None for tier-1
    # parent groups; set for tier-2 subgroups. is_subgroup is a convenience
    # for the UI so it doesn't have to null-check parent_section_id.
    parent_section_id: Optional[uuid.UUID] = None
    allows_subgroups: bool = False
    is_subgroup: bool = False
    active_code_count: int = 0
    # B88 Pack 2 — backend-enforced construction scope. Tier 2 callers
    # (Construction Budget screen) only see lines under sections where
    # this flag is true.
    included_in_construction_scope: bool = False


class SectionTreeRead(SectionRead):
    """Nested form returned by GET /cost-code-sections?tree=true.

    `subgroups` is populated only on tier-1 parents that have at least
    one child; never recurses beyond one level (we enforce two tiers).
    """
    subgroups: list[SectionRead] = Field(default_factory=list)


class SectionCreate(BaseModel):
    code: str = Field(max_length=30)
    name: str = Field(max_length=100)
    display_order: int
    is_direct_cost: bool = True
    default_p_and_l_category: str = "COS"
    parent_section_id: Optional[uuid.UUID] = None
    allows_subgroups: bool = False
    # B88 Pack 2 — operator can set construction scope on create.
    included_in_construction_scope: bool = False


class SectionUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=100)
    display_order: Optional[int] = None
    is_direct_cost: Optional[bool] = None
    default_p_and_l_category: Optional[str] = None
    # B88 Pack 1 — operator can re-parent / flip allows_subgroups, subject
    # to the SECTION_LOCKED_FIELDS_WHEN_HAS_CHILDREN guard in the route.
    parent_section_id: Optional[uuid.UUID] = None
    allows_subgroups: Optional[bool] = None
    # B88 Pack 2 — operator can retoggle construction-scope membership
    # under the same `cost_codes.edit` gate as the rest of the PATCH.
    included_in_construction_scope: Optional[bool] = None


class CostCodeRead(BaseModel):
    id: uuid.UUID
    code: str
    prefix: str
    sequence: int
    name: str
    description: Optional[str] = None
    section_id: uuid.UUID
    nrm_reference: Optional[str] = None
    buildertrend_category: Optional[str] = None
    applies_to_parent: bool
    applies_to_spv: bool
    applies_to_construction_co: bool
    default_entity: str
    entity_rule_notes: Optional[str] = None
    xero_nominal_code: Optional[str] = None
    xero_nominal_name: Optional[str] = None
    is_vattable: bool
    vat_treatment: str
    is_cis_applicable: bool
    is_retention_applicable: bool
    is_capitalisable: bool
    status: str
    retired_at: Optional[datetime] = None
    retired_reason: Optional[str] = None
    replaced_by_code_id: Optional[uuid.UUID] = None
    display_order: int
    notes: Optional[str] = None


class CostCodeCreate(BaseModel):
    code: str
    name: str = Field(max_length=255)
    description: Optional[str] = None
    section_id: uuid.UUID
    nrm_reference: Optional[str] = None
    buildertrend_category: Optional[str] = Field(default=None, max_length=100)
    applies_to_parent: bool = False
    applies_to_spv: bool = True
    applies_to_construction_co: bool = False
    default_entity: str = "SPV"
    entity_rule_notes: Optional[str] = None
    xero_nominal_code: Optional[str] = None
    xero_nominal_name: Optional[str] = None
    is_vattable: bool = True
    vat_treatment: str = "Standard"
    is_cis_applicable: bool = False
    is_retention_applicable: bool = False
    is_capitalisable: bool = True
    display_order: Optional[int] = None
    notes: Optional[str] = None


class CostCodeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    nrm_reference: Optional[str] = None
    buildertrend_category: Optional[str] = None
    applies_to_parent: Optional[bool] = None
    applies_to_spv: Optional[bool] = None
    applies_to_construction_co: Optional[bool] = None
    default_entity: Optional[str] = None
    entity_rule_notes: Optional[str] = None
    xero_nominal_code: Optional[str] = None
    xero_nominal_name: Optional[str] = None
    is_vattable: Optional[bool] = None
    vat_treatment: Optional[str] = None
    is_cis_applicable: Optional[bool] = None
    is_retention_applicable: Optional[bool] = None
    is_capitalisable: Optional[bool] = None
    display_order: Optional[int] = None
    notes: Optional[str] = None


class RetirePayload(BaseModel):
    retired_reason: str = Field(min_length=3)
    replaced_by_code_id: Optional[uuid.UUID] = None


class SubcategoryRead(BaseModel):
    id: uuid.UUID
    cost_code_id: uuid.UUID
    code: str
    name: str
    description: Optional[str] = None
    default_unit: Optional[str] = None
    display_order: int
    status: str


class SubcategoryCreate(BaseModel):
    code: str
    name: str = Field(max_length=255)
    description: Optional[str] = None
    default_unit: Optional[str] = None
    display_order: int = 1


class SubcategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_unit: Optional[str] = None
    display_order: Optional[int] = None
    status: Optional[str] = None


class EntityMappingRead(BaseModel):
    id: uuid.UUID
    cost_code_id: uuid.UUID
    entity_id: uuid.UUID
    is_allowed: bool
    xero_nominal_code_override: Optional[str] = None
    notes: Optional[str] = None


class EntityMappingCreate(BaseModel):
    cost_code_id: uuid.UUID
    entity_id: uuid.UUID
    is_allowed: bool = True
    xero_nominal_code_override: Optional[str] = None
    notes: Optional[str] = None


class EntityMappingUpdate(BaseModel):
    is_allowed: Optional[bool] = None
    xero_nominal_code_override: Optional[str] = None
    notes: Optional[str] = None


class ProjectCostCodeRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    cost_code_id: uuid.UUID
    code: str
    name: str
    prefix: str
    section_id: uuid.UUID
    is_enabled: bool
    cost_code_status: str
    project_override_name: Optional[str] = None
    notes: Optional[str] = None


class ProjectCostCodeUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    project_override_name: Optional[str] = None
    notes: Optional[str] = None


class BulkTogglePayload(BaseModel):
    section_code: str
    is_enabled: bool


# ==========================================================================
# Helpers
# ==========================================================================

def _section_to_read(db: Session, s: CostCodeSection) -> SectionRead:
    cnt = db.scalar(
        select(func.count()).select_from(CostCode).where(
            CostCode.section_id == s.id, CostCode.status == "Active"
        )
    ) or 0
    return SectionRead(
        id=s.id, code=s.code, name=s.name, display_order=s.display_order,
        is_direct_cost=s.is_direct_cost,
        default_p_and_l_category=s.default_p_and_l_category,
        parent_section_id=s.parent_section_id,
        allows_subgroups=s.allows_subgroups,
        is_subgroup=s.parent_section_id is not None,
        active_code_count=cnt,
        included_in_construction_scope=s.included_in_construction_scope,
    )


def _section_snapshot(s: CostCodeSection) -> dict:
    """Audit field-diff snapshot. Includes the new hierarchy columns
    so re-parenting + allows_subgroups flips appear in the audit log."""
    return {
        "code": s.code, "name": s.name, "display_order": s.display_order,
        "is_direct_cost": s.is_direct_cost,
        "default_p_and_l_category": s.default_p_and_l_category,
        "parent_section_id": (
            str(s.parent_section_id) if s.parent_section_id else None
        ),
        "allows_subgroups": s.allows_subgroups,
        "included_in_construction_scope": s.included_in_construction_scope,
    }


def _cc_to_read(c: CostCode) -> CostCodeRead:
    return CostCodeRead(
        id=c.id, code=c.code, prefix=c.prefix, sequence=c.sequence,
        name=c.name, description=c.description, section_id=c.section_id,
        nrm_reference=c.nrm_reference, buildertrend_category=c.buildertrend_category,
        applies_to_parent=c.applies_to_parent, applies_to_spv=c.applies_to_spv,
        applies_to_construction_co=c.applies_to_construction_co,
        default_entity=c.default_entity, entity_rule_notes=c.entity_rule_notes,
        xero_nominal_code=c.xero_nominal_code, xero_nominal_name=c.xero_nominal_name,
        is_vattable=c.is_vattable, vat_treatment=c.vat_treatment,
        is_cis_applicable=c.is_cis_applicable,
        is_retention_applicable=c.is_retention_applicable,
        is_capitalisable=c.is_capitalisable,
        status=c.status, retired_at=c.retired_at, retired_reason=c.retired_reason,
        replaced_by_code_id=c.replaced_by_code_id,
        display_order=c.display_order, notes=c.notes,
    )


def _cc_snapshot(c: CostCode) -> dict:
    return {
        "name": c.name, "description": c.description,
        "section_id": str(c.section_id),
        "nrm_reference": c.nrm_reference,
        "buildertrend_category": c.buildertrend_category,
        "applies_to_parent": c.applies_to_parent,
        "applies_to_spv": c.applies_to_spv,
        "applies_to_construction_co": c.applies_to_construction_co,
        "default_entity": c.default_entity,
        "xero_nominal_code": c.xero_nominal_code,
        "xero_nominal_name": c.xero_nominal_name,
        "is_vattable": c.is_vattable, "vat_treatment": c.vat_treatment,
        "is_cis_applicable": c.is_cis_applicable,
        "is_retention_applicable": c.is_retention_applicable,
        "is_capitalisable": c.is_capitalisable,
        "status": c.status, "display_order": c.display_order,
    }


# ==========================================================================
# Sections (B88 Pack 1 §3.1 — full CRUD + two-tier hierarchy)
# ==========================================================================

@router.get("/cost-code-sections", response_model=list[SectionTreeRead])
def list_sections(
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.view")),
    tree: bool = Query(
        default=False,
        description="If true, returns tier-1 parents only with their "
                    "subgroups nested under `subgroups`. If false (default), "
                    "returns a flat list of ALL sections in display order.",
    ),
):
    if tree:
        parents = db.scalars(
            select(CostCodeSection)
            .where(CostCodeSection.parent_section_id.is_(None))
            .order_by(CostCodeSection.display_order)
        ).all()
        out: list[SectionTreeRead] = []
        for p in parents:
            base = _section_to_read(db, p)
            children = db.scalars(
                select(CostCodeSection)
                .where(CostCodeSection.parent_section_id == p.id)
                .order_by(CostCodeSection.display_order)
            ).all()
            tree_row = SectionTreeRead(
                **base.model_dump(),
                subgroups=[_section_to_read(db, c) for c in children],
            )
            out.append(tree_row)
        return out

    rows = db.scalars(
        select(CostCodeSection).order_by(CostCodeSection.display_order)
    ).all()
    return [_section_to_read(db, s) for s in rows]


@router.post("/cost-code-sections", response_model=SectionRead, status_code=201)
def create_section(
    payload: SectionCreate,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.create")),
):
    # B88 Pack 1 §3.2 — parent rules.
    err = validate_section_parent(db, parent_id=payload.parent_section_id)
    if err is not None:
        raise HTTPException(422, err)
    # A subgroup cannot itself host subgroups (forbidden tier-3).
    if payload.parent_section_id is not None and payload.allows_subgroups:
        raise HTTPException(
            422, "A subgroup cannot have allows_subgroups=True (max 2 tiers).",
        )
    if payload.default_p_and_l_category not in P_AND_L_CATEGORIES:
        raise HTTPException(422, "Invalid default_p_and_l_category")

    s = CostCodeSection(
        code=payload.code, name=payload.name,
        display_order=payload.display_order,
        is_direct_cost=payload.is_direct_cost,
        default_p_and_l_category=payload.default_p_and_l_category,
        parent_section_id=payload.parent_section_id,
        allows_subgroups=payload.allows_subgroups,
        included_in_construction_scope=payload.included_in_construction_scope,
    )
    db.add(s)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, f"Section code '{payload.code}' already exists",
        )
    record_audit(
        db, action="Create", resource_type="cost_code_sections",
        resource_id=s.id, actor_user_id=current.id,
        field_changes=field_diff({}, _section_snapshot(s)),
        request=request,
    )
    db.commit()
    db.refresh(s)
    return _section_to_read(db, s)


@router.patch("/cost-code-sections/{section_id}", response_model=SectionRead)
def update_section(
    section_id: uuid.UUID,
    payload: SectionUpdate,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.edit")),
):
    s = db.scalar(select(CostCodeSection).where(CostCodeSection.id == section_id))
    if s is None:
        raise HTTPException(404, "Section not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _section_to_read(db, s)

    # Field locks tied to active cost-codes attached.
    in_use = is_section_in_use(db, section_id)
    if in_use:
        bad = sorted(set(changes.keys()) & SECTION_LOCKED_FIELDS_WHEN_IN_USE)
        if bad:
            raise HTTPException(409, f"Locked fields cannot change: {bad}")

    # Field locks tied to existing subgroup children (B88 §3.2).
    if section_has_children(db, section_id):
        bad = sorted(
            set(changes.keys()) & SECTION_LOCKED_FIELDS_WHEN_HAS_CHILDREN
        )
        if bad:
            raise HTTPException(
                409,
                f"Section has subgroup children; cannot change: {bad}. "
                "Move or delete the subgroups first.",
            )

    # If parent_section_id is being changed, re-validate the new parent.
    if "parent_section_id" in changes:
        err = validate_section_parent(
            db, parent_id=changes["parent_section_id"], self_id=section_id,
        )
        if err is not None:
            raise HTTPException(422, err)
        # A row with attached cost codes cannot become a subgroup if its
        # codes would then violate validate_section_for_cost_code (i.e.
        # they'd end up under a parent that hosts subgroups). In our
        # simple model: becoming a subgroup is always safe for the
        # codes attached (they end up under a subgroup, which is legal).
        # The check we DO need: if a row is becoming a child, it cannot
        # itself be a parent of subgroups — caught above.

    # If allows_subgroups is being turned ON, the row must NOT already
    # have cost codes attached (a parent-that-allows-subgroups cannot
    # also host raw codes — that breaks validate_section_for_cost_code
    # for those codes on next edit).
    if changes.get("allows_subgroups") is True and in_use:
        raise HTTPException(
            409,
            "Cannot enable allows_subgroups: this group already has cost "
            "codes attached. Move them under a subgroup first.",
        )

    before = _section_snapshot(s)
    for k, v in changes.items():
        setattr(s, k, v)
    after = _section_snapshot(s)
    diff = field_diff(before, after)
    if diff:
        record_audit(
            db, action="Update", resource_type="cost_code_sections",
            resource_id=s.id, actor_user_id=current.id,
            field_changes=diff, request=request,
        )
    db.commit()
    db.refresh(s)
    return _section_to_read(db, s)


@router.delete("/cost-code-sections/{section_id}", status_code=204)
def delete_section(
    section_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.delete")),
):
    s = db.scalar(select(CostCodeSection).where(CostCodeSection.id == section_id))
    if s is None:
        raise HTTPException(404, "Section not found")
    reasons = section_block_reasons(db, section_id)
    if reasons:
        # Graceful structured 409 — UI shows each blocker line by line.
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cannot delete: section is in use.",
                "blockers": reasons,
            },
        )
    snapshot = _section_snapshot(s)
    record_audit(
        db, action="Delete", resource_type="cost_code_sections",
        resource_id=s.id, actor_user_id=current.id,
        field_changes=field_diff(snapshot, {}),
        request=request,
    )
    db.delete(s)
    db.commit()
    return None


# ==========================================================================
# Cost codes
# ==========================================================================

@router.get("/cost-codes", response_model=list[CostCodeRead])
def list_cost_codes(
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.view")),
    section_id: Optional[uuid.UUID] = None,
    prefix: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
):
    query = select(CostCode)
    if section_id is not None:
        query = query.where(CostCode.section_id == section_id)
    if prefix:
        query = query.where(CostCode.prefix == prefix.upper())
    if status:
        if status.lower() == "all":
            pass  # no status filter — include both Active and Retired
        elif status in ("Active", "Retired"):
            query = query.where(CostCode.status == status)
        else:
            raise HTTPException(
                status_code=422,
                detail=f"invalid status filter: {status!r}",
            )
    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(
            func.lower(CostCode.code).like(like),
            func.lower(CostCode.name).like(like),
        ))
    query = query.order_by(CostCode.display_order, CostCode.code)
    rows = db.scalars(query).all()
    return [_cc_to_read(c) for c in rows]


@router.get("/cost-codes/{code_id}", response_model=CostCodeRead)
def get_cost_code(
    code_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.view")),
):
    c = db.scalar(select(CostCode).where(CostCode.id == code_id))
    if c is None:
        raise HTTPException(404, "Cost code not found")
    return _cc_to_read(c)


@router.post("/cost-codes", response_model=CostCodeRead, status_code=201)
def create_cost_code(
    payload: CostCodeCreate,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.create")),
):
    if not validate_cost_code_format(payload.code):
        raise HTTPException(400, "code must match ^[A-Z]{3}-\\d{2}$")
    if payload.default_entity not in DEFAULT_ENTITY_VALUES:
        raise HTTPException(422, "Invalid default_entity")
    if payload.vat_treatment not in VAT_TREATMENTS:
        raise HTTPException(422, "Invalid vat_treatment")
    sec = db.scalar(select(CostCodeSection).where(
        CostCodeSection.id == payload.section_id))
    if sec is None:
        raise HTTPException(404, "Section not found")
    # B88 Pack 1 §3.2 — a code's section_id may not point at a
    # parent-with-subgroups (would break the two-tier filing rule).
    err = validate_section_for_cost_code(db, section_id=payload.section_id)
    if err is not None:
        raise HTTPException(422, err)

    prefix = payload.code[:3]
    seq = int(payload.code[4:])
    c = CostCode(
        code=payload.code, prefix=prefix, sequence=seq,
        name=payload.name, description=payload.description,
        section_id=payload.section_id,
        nrm_reference=payload.nrm_reference,
        buildertrend_category=payload.buildertrend_category,
        applies_to_parent=payload.applies_to_parent,
        applies_to_spv=payload.applies_to_spv,
        applies_to_construction_co=payload.applies_to_construction_co,
        default_entity=payload.default_entity,
        entity_rule_notes=payload.entity_rule_notes,
        xero_nominal_code=payload.xero_nominal_code,
        xero_nominal_name=payload.xero_nominal_name,
        is_vattable=payload.is_vattable,
        vat_treatment=payload.vat_treatment,
        is_cis_applicable=payload.is_cis_applicable,
        is_retention_applicable=payload.is_retention_applicable,
        is_capitalisable=payload.is_capitalisable,
        display_order=payload.display_order or seq,
        notes=payload.notes,
    )
    db.add(c)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Cost code already exists (code or prefix+sequence)")
    record_audit(
        db, action="Create", resource_type="cost_codes",
        resource_id=c.id, actor_user_id=current.id,
        field_changes=field_diff({}, {"code": c.code, "name": c.name}),
        request=request,
    )
    db.commit()
    db.refresh(c)
    return _cc_to_read(c)


@router.patch("/cost-codes/{code_id}", response_model=CostCodeRead)
def update_cost_code(
    code_id: uuid.UUID,
    payload: CostCodeUpdate,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.edit")),
):
    c = db.scalar(select(CostCode).where(CostCode.id == code_id))
    if c is None:
        raise HTTPException(404, "Cost code not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _cc_to_read(c)
    if is_cost_code_in_use(db, code_id):
        bad = sorted(set(changes.keys()) & LOCKED_FIELDS_WHEN_IN_USE)
        if bad:
            raise HTTPException(
                409, f"Cost code is in use; locked fields cannot change: {bad}")
    if "default_entity" in changes and changes["default_entity"] not in DEFAULT_ENTITY_VALUES:
        raise HTTPException(422, "Invalid default_entity")
    if "vat_treatment" in changes and changes["vat_treatment"] not in VAT_TREATMENTS:
        raise HTTPException(422, "Invalid vat_treatment")

    before = _cc_snapshot(c)
    for k, v in changes.items():
        setattr(c, k, v)
    after = _cc_snapshot(c)
    diff = field_diff(before, after)
    if diff:
        record_audit(
            db, action="Update", resource_type="cost_codes",
            resource_id=c.id, actor_user_id=current.id,
            field_changes=diff, request=request,
        )
    db.commit()
    db.refresh(c)
    return _cc_to_read(c)


@router.post("/cost-codes/{code_id}/retire", response_model=CostCodeRead)
def retire_cost_code(
    code_id: uuid.UUID,
    payload: RetirePayload,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.edit")),
):
    c = db.scalar(select(CostCode).where(CostCode.id == code_id))
    if c is None:
        raise HTTPException(404, "Cost code not found")
    if c.status == "Retired":
        raise HTTPException(409, "Cost code already retired")
    if payload.replaced_by_code_id is not None:
        if payload.replaced_by_code_id == code_id:
            raise HTTPException(400, "replaced_by cannot be the same code")
        target = db.scalar(select(CostCode).where(
            CostCode.id == payload.replaced_by_code_id))
        if target is None:
            raise HTTPException(404, "replaced_by target not found")
        if target.status != "Active":
            raise HTTPException(409, "replaced_by target must be Active")
        if detect_replaced_by_cycle(
            db, candidate_id=code_id,
            proposed_replaced_by=payload.replaced_by_code_id,
        ):
            raise HTTPException(409, "replaced_by chain would form a cycle")

    before = {"status": c.status,
              "replaced_by_code_id": str(c.replaced_by_code_id) if c.replaced_by_code_id else None}
    c.status = "Retired"
    c.retired_at = datetime.now(timezone.utc)
    c.retired_reason = payload.retired_reason
    c.replaced_by_code_id = payload.replaced_by_code_id
    after = {"status": c.status,
             "replaced_by_code_id": str(c.replaced_by_code_id) if c.replaced_by_code_id else None}

    record_audit(
        db, action="Status_Change", resource_type="cost_codes",
        resource_id=c.id, actor_user_id=current.id,
        field_changes=field_diff(before, after),
        metadata={"kind": "retire", "retired_reason": payload.retired_reason},
        request=request,
    )
    db.commit()
    db.refresh(c)
    return _cc_to_read(c)


@router.post("/cost-codes/{code_id}/reactivate", response_model=CostCodeRead)
def reactivate_cost_code_endpoint(
    code_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.edit")),
):
    """B88 Pack 1 §3.4 — un-retire mirror of /retire.

    Flips status Retired→Active and clears retired_at, retired_reason,
    and replaced_by_code_id. Idempotent on already-Active codes (409 —
    same shape as retire's already-retired check).
    """
    c = db.scalar(select(CostCode).where(CostCode.id == code_id))
    if c is None:
        raise HTTPException(404, "Cost code not found")
    if c.status == "Active":
        raise HTTPException(409, "Cost code is already Active")

    payload = reactivate_cost_code(c)
    record_audit(
        db, action="Status_Change", resource_type="cost_codes",
        resource_id=c.id, actor_user_id=current.id,
        field_changes=field_diff(payload["before"], payload["after"]),
        metadata={"kind": "reactivate",
                  "reactivated_at": payload["reactivated_at"]},
        request=request,
    )
    db.commit()
    db.refresh(c)
    return _cc_to_read(c)


@router.delete("/cost-codes/{code_id}", status_code=204)
def delete_cost_code(
    code_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.delete")),
):
    """B88 Pack 1 §3.3 — hard delete with named-blocker 409.

    Only invoked for codes that "really were never used or were created
    in error" — the retire flow remains the right choice for any code
    that has ever posted anywhere. cost_code_block_reasons checks every
    inbound RESTRICT FK and returns named counts; if any are present the
    request fails with a structured 409 (`{message, blockers}`) so the
    UI can list them. CASCADE/SET-NULL inbound FKs (entity-mapping,
    AI-hint, retire-and-replace pointer) are intentionally not blockers.
    """
    c = db.scalar(select(CostCode).where(CostCode.id == code_id))
    if c is None:
        raise HTTPException(404, "Cost code not found")
    reasons = cost_code_block_reasons(db, code_id)
    if reasons:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cannot delete: cost code is in use.",
                "blockers": reasons,
            },
        )
    snapshot = _cc_snapshot(c)
    snapshot["code"] = c.code  # preserve the immutable identifier in audit
    record_audit(
        db, action="Delete", resource_type="cost_codes",
        resource_id=c.id, actor_user_id=current.id,
        field_changes=field_diff(snapshot, {}),
        request=request,
    )
    db.delete(c)
    db.commit()
    return None


# ==========================================================================
# Subcategories
# ==========================================================================

@router.get("/cost-codes/{code_id}/subcategories",
            response_model=list[SubcategoryRead])
def list_subcategories(
    code_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.view")),
):
    rows = db.scalars(
        select(CostCodeSubcategory).where(
            CostCodeSubcategory.cost_code_id == code_id
        ).order_by(CostCodeSubcategory.display_order)
    ).all()
    return [SubcategoryRead.model_validate(r, from_attributes=True) for r in rows]


@router.post("/cost-codes/{code_id}/subcategories",
             response_model=SubcategoryRead, status_code=201)
def create_subcategory(
    code_id: uuid.UUID,
    payload: SubcategoryCreate,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.admin")),
):
    parent = db.scalar(select(CostCode).where(CostCode.id == code_id))
    if parent is None:
        raise HTTPException(404, "Parent cost code not found")
    if not validate_subcategory_format(parent.code, payload.code):
        raise HTTPException(
            400, f"Subcategory code must match {parent.code}.NN")
    if payload.default_unit and payload.default_unit not in SUBCAT_UNITS:
        raise HTTPException(422, "Invalid default_unit")

    s = CostCodeSubcategory(
        cost_code_id=code_id, code=payload.code, name=payload.name,
        description=payload.description, default_unit=payload.default_unit,
        display_order=payload.display_order,
    )
    db.add(s)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Subcategory code already exists")
    record_audit(
        db, action="Create", resource_type="cost_code_subcategories",
        resource_id=s.id, actor_user_id=current.id,
        field_changes=field_diff({}, {"code": s.code, "name": s.name}),
        request=request,
    )
    db.commit()
    db.refresh(s)
    return SubcategoryRead.model_validate(s, from_attributes=True)


@router.patch("/cost-code-subcategories/{sub_id}",
              response_model=SubcategoryRead)
def update_subcategory(
    sub_id: uuid.UUID,
    payload: SubcategoryUpdate,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.admin")),
):
    s = db.scalar(select(CostCodeSubcategory).where(
        CostCodeSubcategory.id == sub_id))
    if s is None:
        raise HTTPException(404, "Subcategory not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("default_unit") and changes["default_unit"] not in SUBCAT_UNITS:
        raise HTTPException(422, "Invalid default_unit")
    if changes.get("status") and changes["status"] not in COST_CODE_STATUSES:
        raise HTTPException(422, "Invalid status")
    before = {k: getattr(s, k) for k in
              ("name", "description", "default_unit", "display_order", "status")}
    for k, v in changes.items():
        setattr(s, k, v)
    after = {k: getattr(s, k) for k in
             ("name", "description", "default_unit", "display_order", "status")}
    diff = field_diff(before, after)
    if diff:
        record_audit(
            db, action="Update", resource_type="cost_code_subcategories",
            resource_id=s.id, actor_user_id=current.id,
            field_changes=diff, request=request,
        )
    db.commit()
    db.refresh(s)
    return SubcategoryRead.model_validate(s, from_attributes=True)


# ==========================================================================
# Entity mapping
# ==========================================================================

@router.get("/cost-codes/{code_id}/entity-mapping",
            response_model=list[EntityMappingRead])
def list_entity_mapping(
    code_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.view")),
):
    rows = db.scalars(
        select(CostCodeEntityMapping).where(
            CostCodeEntityMapping.cost_code_id == code_id
        )
    ).all()
    return [EntityMappingRead.model_validate(r, from_attributes=True) for r in rows]


@router.post("/cost-code-entity-mapping",
             response_model=EntityMappingRead, status_code=201)
def create_entity_mapping(
    payload: EntityMappingCreate,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.admin")),
):
    if not db.scalar(select(CostCode).where(CostCode.id == payload.cost_code_id)):
        raise HTTPException(404, "Cost code not found")
    if not db.scalar(select(Entity).where(Entity.id == payload.entity_id)):
        raise HTTPException(404, "Entity not found")
    m = CostCodeEntityMapping(
        cost_code_id=payload.cost_code_id, entity_id=payload.entity_id,
        is_allowed=payload.is_allowed,
        xero_nominal_code_override=payload.xero_nominal_code_override,
        notes=payload.notes,
    )
    db.add(m)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Mapping already exists for this code+entity")
    record_audit(
        db, action="Create", resource_type="cost_code_entity_mapping",
        resource_id=m.id, actor_user_id=current.id, entity_id=m.entity_id,
        field_changes=field_diff({}, {
            "cost_code_id": str(m.cost_code_id),
            "entity_id": str(m.entity_id),
            "is_allowed": m.is_allowed,
        }),
        request=request,
    )
    db.commit()
    db.refresh(m)
    return EntityMappingRead.model_validate(m, from_attributes=True)


@router.patch("/cost-code-entity-mapping/{mapping_id}",
              response_model=EntityMappingRead)
def update_entity_mapping(
    mapping_id: uuid.UUID,
    payload: EntityMappingUpdate,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.admin")),
):
    m = db.scalar(select(CostCodeEntityMapping).where(
        CostCodeEntityMapping.id == mapping_id))
    if m is None:
        raise HTTPException(404, "Mapping not found")
    changes = payload.model_dump(exclude_unset=True)
    before = {k: getattr(m, k) for k in
              ("is_allowed", "xero_nominal_code_override", "notes")}
    for k, v in changes.items():
        setattr(m, k, v)
    after = {k: getattr(m, k) for k in
             ("is_allowed", "xero_nominal_code_override", "notes")}
    diff = field_diff(before, after)
    if diff:
        record_audit(
            db, action="Update", resource_type="cost_code_entity_mapping",
            resource_id=m.id, actor_user_id=current.id, entity_id=m.entity_id,
            field_changes=diff, request=request,
        )
    db.commit()
    db.refresh(m)
    return EntityMappingRead.model_validate(m, from_attributes=True)


@router.delete("/cost-code-entity-mapping/{mapping_id}", status_code=204)
def delete_entity_mapping(
    mapping_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.admin")),
):
    m = db.scalar(select(CostCodeEntityMapping).where(
        CostCodeEntityMapping.id == mapping_id))
    if m is None:
        raise HTTPException(404, "Mapping not found")
    record_audit(
        db, action="Delete", resource_type="cost_code_entity_mapping",
        resource_id=m.id, actor_user_id=current.id, entity_id=m.entity_id,
        field_changes=field_diff({
            "cost_code_id": str(m.cost_code_id),
            "entity_id": str(m.entity_id),
            "is_allowed": m.is_allowed,
        }, {}),
        request=request,
    )
    db.delete(m)
    db.commit()
    return None


# ==========================================================================
# Project cost codes (toggle + bulk)
# ==========================================================================

def _project_or_404(db: Session, project_id: uuid.UUID) -> Project:
    p = db.scalar(select(Project).where(Project.id == project_id))
    if p is None:
        raise HTTPException(404, "Project not found")
    return p


@router.get("/projects/{project_id}/cost-codes",
            response_model=list[ProjectCostCodeRead])
def list_project_cost_codes(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.view")),
):
    _project_or_404(db, project_id)
    rows = db.execute(
        select(
            ProjectCostCode.id, ProjectCostCode.project_id,
            ProjectCostCode.cost_code_id, CostCode.code, CostCode.name,
            CostCode.prefix, CostCode.section_id,
            ProjectCostCode.is_enabled, CostCode.status,
            ProjectCostCode.project_override_name, ProjectCostCode.notes,
        ).join(CostCode, CostCode.id == ProjectCostCode.cost_code_id)
        .where(ProjectCostCode.project_id == project_id)
        .order_by(CostCode.display_order, CostCode.code)
    ).all()
    return [ProjectCostCodeRead(
        id=r[0], project_id=r[1], cost_code_id=r[2], code=r[3], name=r[4],
        prefix=r[5], section_id=r[6], is_enabled=r[7],
        cost_code_status=r[8], project_override_name=r[9], notes=r[10],
    ) for r in rows]


@router.patch("/projects/{project_id}/cost-codes/{cost_code_id}",
              response_model=ProjectCostCodeRead)
def patch_project_cost_code(
    project_id: uuid.UUID,
    cost_code_id: uuid.UUID,
    payload: ProjectCostCodeUpdate,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("projects.edit")),
):
    p = _project_or_404(db, project_id)
    pcc = db.scalar(select(ProjectCostCode).where(
        ProjectCostCode.project_id == project_id,
        ProjectCostCode.cost_code_id == cost_code_id,
    ))
    if pcc is None:
        raise HTTPException(404, "Project cost code row not found")
    cc = db.scalar(select(CostCode).where(CostCode.id == cost_code_id))
    changes = payload.model_dump(exclude_unset=True)

    if changes.get("is_enabled") is True and cc and cc.status == "Retired":
        raise HTTPException(409, "Cannot enable a Retired cost code on a project")

    before = {k: getattr(pcc, k) for k in
              ("is_enabled", "project_override_name", "notes")}
    for k, v in changes.items():
        setattr(pcc, k, v)
    after = {k: getattr(pcc, k) for k in
             ("is_enabled", "project_override_name", "notes")}
    diff = field_diff(before, after)
    if diff:
        record_audit(
            db, action="Update", resource_type="project_cost_codes",
            resource_id=pcc.id, actor_user_id=current.id,
            entity_id=p.primary_entity_id, project_id=p.id,
            field_changes=diff, request=request,
        )
    db.commit()
    db.refresh(pcc)
    return ProjectCostCodeRead(
        id=pcc.id, project_id=pcc.project_id, cost_code_id=pcc.cost_code_id,
        code=cc.code, name=cc.name, prefix=cc.prefix,
        section_id=cc.section_id, is_enabled=pcc.is_enabled,
        cost_code_status=cc.status,
        project_override_name=pcc.project_override_name,
        notes=pcc.notes,
    )


@router.post("/projects/{project_id}/cost-codes/bulk-toggle")
def bulk_toggle_project_cost_codes(
    project_id: uuid.UUID,
    payload: BulkTogglePayload,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _=Depends(require_permission("projects.edit")),
):
    p = _project_or_404(db, project_id)
    sec = db.scalar(select(CostCodeSection).where(
        CostCodeSection.code == payload.section_code))
    if sec is None:
        raise HTTPException(404, "Section not found")

    # Update only rows for codes in this section.
    affected = db.execute(
        select(ProjectCostCode.id, ProjectCostCode.cost_code_id, CostCode.status)
        .join(CostCode, CostCode.id == ProjectCostCode.cost_code_id)
        .where(ProjectCostCode.project_id == project_id,
               CostCode.section_id == sec.id)
    ).all()

    updated = 0
    skipped_retired = 0
    for pcc_id, cc_id, status in affected:
        if payload.is_enabled and status == "Retired":
            skipped_retired += 1
            continue
        db.execute(
            ProjectCostCode.__table__.update()
            .where(ProjectCostCode.id == pcc_id)
            .values(is_enabled=payload.is_enabled,
                    updated_at=datetime.now(timezone.utc))
        )
        updated += 1

    record_audit(
        db, action="Update", resource_type="project_cost_codes",
        resource_id=p.id, actor_user_id=current.id,
        entity_id=p.primary_entity_id, project_id=p.id,
        field_changes=[],
        metadata={
            "kind": "bulk_toggle", "section_code": payload.section_code,
            "is_enabled": payload.is_enabled,
            "rows_updated": updated, "skipped_retired": skipped_retired,
        },
        request=request,
    )
    db.commit()
    return {
        "section_code": payload.section_code, "is_enabled": payload.is_enabled,
        "rows_updated": updated, "skipped_retired": skipped_retired,
    }


# ==========================================================================
# Diagnostic helper: entity-mapping resolution (handy from UI)
# ==========================================================================

@router.get("/cost-codes/{code_id}/can-use/{entity_id}")
def can_entity_use(
    code_id: uuid.UUID, entity_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(require_permission("cost_codes.view")),
):
    allowed, nominal = can_entity_use_cost_code(
        db, cost_code_id=code_id, entity_id=entity_id,
    )
    return {"allowed": allowed, "xero_nominal_code": nominal}
