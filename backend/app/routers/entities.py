"""Entities CRUD router — Prompt 1.1 + 1.2 retrofit.

Changes in 1.2:
  - Every route is protected by `require_permission(...)`.
  - `get_current_tenant_id` now resolves from the authenticated user's session,
    not from a name lookup. The name-based dep stays for backwards compat but
    is no longer used on entity endpoints.
  - Banking + Xero sensitive fields are stripped from the response unless the
    caller has `entities.view_sensitive`.
  - POST stamps created_by_user_id with the current user.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    UserPermissions,
    compute_effective_permissions,
    get_current_principal,
    get_current_user,
    require_permission,
    Principal,
)
from app.db import get_db
from app.models import Entity, ENTITY_STATUSES, ENTITY_TYPES
from app.models.user import User
from app.schemas.entity import (
    EntityCreate, EntityDetail, EntityListResponse,
    EntityRead, EntitySummary, EntityUpdate,
)

from app.services.audit import record_audit, field_diff

router = APIRouter(prefix="/entities", tags=["entities"])


def _entity_snapshot(ent: Entity) -> dict:
    """Columns we care about for field_diff — drop anything internal."""
    return {
        "name": ent.name, "legal_name": ent.legal_name, "entity_type": ent.entity_type,
        "parent_entity_id": str(ent.parent_entity_id) if ent.parent_entity_id else None,
        "registered_address": ent.registered_address, "trading_address": ent.trading_address,
        "companies_house_number": ent.companies_house_number, "vat_number": ent.vat_number,
        "vat_scheme": ent.vat_scheme, "vat_return_period": ent.vat_return_period,
        "cis_status": ent.cis_status, "year_end": ent.year_end.isoformat() if ent.year_end else None,
        "default_currency": ent.default_currency, "status": ent.status,
        "el_insurance_expires": ent.el_insurance_expires.isoformat() if ent.el_insurance_expires else None,
        "pl_insurance_expires": ent.pl_insurance_expires.isoformat() if ent.pl_insurance_expires else None,
        "pi_insurance_expires": ent.pi_insurance_expires.isoformat() if ent.pi_insurance_expires else None,
        "bank_name": ent.bank_name, "bank_account_name": ent.bank_account_name,
        "bank_account_number_masked": ent.bank_account_number_masked,
        "xero_org_id": ent.xero_org_id,
    }


SORTABLE_FIELDS = {
    "name": Entity.name, "legal_name": Entity.legal_name,
    "entity_type": Entity.entity_type, "status": Entity.status,
    "companies_house_number": Entity.companies_house_number,
    "vat_number": Entity.vat_number, "year_end": Entity.year_end,
    "created_at": Entity.created_at, "updated_at": Entity.updated_at,
}


SENSITIVE_FIELDS = (
    "bank_name", "bank_account_name", "bank_account_number_masked",
    "xero_org_id", "xero_org_name",
)


def _strip_sensitive(model: EntityRead | EntityDetail, perms: UserPermissions) -> None:
    if perms.has("entities.view_sensitive"):
        return
    for f in SENSITIVE_FIELDS:
        if hasattr(model, f):
            setattr(model, f, None)


def _tenant_filter(tenant_id: uuid.UUID):
    return Entity.tenant_id == tenant_id


def _get_or_404(db: Session, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Entity:
    ent = db.scalar(
        select(Entity).where(Entity.id == entity_id, _tenant_filter(tenant_id))
    )
    if ent is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent


def _would_create_cycle(db, tenant_id, entity_id, new_parent_id):
    if new_parent_id == entity_id:
        return True
    current = new_parent_id
    visited: set[uuid.UUID] = set()
    while current is not None and current not in visited:
        visited.add(current)
        row = db.execute(
            select(Entity.parent_entity_id).where(
                Entity.id == current, _tenant_filter(tenant_id)
            )
        ).first()
        if row is None:
            return False
        parent_id = row[0]
        if parent_id == entity_id:
            return True
        current = parent_id
    return False


def _detail_payload(db, tenant_id, ent) -> EntityDetail:
    parent: Optional[EntitySummary] = None
    if ent.parent_entity_id is not None:
        p = db.get(Entity, ent.parent_entity_id)
        if p is not None and p.tenant_id == tenant_id:
            parent = EntitySummary.model_validate(p)
    children_rows = db.scalars(
        select(Entity)
        .where(Entity.parent_entity_id == ent.id, _tenant_filter(tenant_id))
        .order_by(Entity.name.asc())
    ).all()
    children = [EntitySummary.model_validate(c) for c in children_rows]
    detail = EntityDetail.model_validate(ent)
    detail.parent = parent
    detail.children = children
    return detail


def _filter_by_scope(perms: UserPermissions, code: str, query):
    """Apply entity-scope filtering: if user has `code` only on specific entities,
    restrict the query to those ids."""
    ent_ids = perms.entity_ids_with(code)
    if ent_ids is None:
        return query  # unscoped
    if not ent_ids:
        return query.where(Entity.id.in_([]))
    return query.where(Entity.id.in_(ent_ids))


# ---------- Routes ----------

@router.get("", response_model=EntityListResponse)
def list_entities(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    perms: UserPermissions = Depends(require_permission("entities.view")),
    q: Optional[str] = None,
    entity_type: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    include_struck_off: bool = False,
    parent_entity_id: Optional[uuid.UUID] = None,
    sort: str = "name",
    dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    tenant_id = principal.tenant_id
    conditions = [_tenant_filter(tenant_id)]
    if q:
        needle = f"%{q.strip()}%"
        conditions.append(or_(Entity.name.ilike(needle), Entity.legal_name.ilike(needle)))
    if entity_type:
        if entity_type not in ENTITY_TYPES:
            raise HTTPException(400, "Invalid entity_type")
        conditions.append(Entity.entity_type == entity_type)
    if status_filter:
        if status_filter not in ENTITY_STATUSES:
            raise HTTPException(400, "Invalid status")
        conditions.append(Entity.status == status_filter)
    elif not include_struck_off:
        conditions.append(Entity.status != "Struck_off")
    if parent_entity_id is not None:
        conditions.append(Entity.parent_entity_id == parent_entity_id)

    base_q = select(Entity).where(and_(*conditions))
    scoped_q = _filter_by_scope(perms, "entities.view", base_q)

    total = db.scalar(
        select(func.count()).select_from(scoped_q.subquery())
    ) or 0

    sort_col = SORTABLE_FIELDS.get(sort, Entity.name)
    order = sort_col.desc() if dir == "desc" else sort_col.asc()

    rows = db.scalars(
        scoped_q.order_by(order, Entity.name.asc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()

    items = [EntityRead.model_validate(r) for r in rows]
    for it in items:
        _strip_sensitive(it, perms)
    return EntityListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{entity_id}", response_model=EntityDetail)
def get_entity(
    entity_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    perms: UserPermissions = Depends(require_permission("entities.view")),
):
    tenant_id = principal.tenant_id
    ent = _get_or_404(db, tenant_id, entity_id)
    # Scope check
    if not perms.has_on_entity("entities.view", ent.id):
        raise HTTPException(403, "Insufficient scope for this entity")
    detail = _detail_payload(db, tenant_id, ent)
    _strip_sensitive(detail, perms)
    return detail


@router.post("", response_model=EntityDetail, status_code=201)
def create_entity(
    payload: EntityCreate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("entities.create")),
):
    tenant_id = principal.tenant_id
    data = payload.model_dump()
    bank_full = data.pop("bank_account_number", None)
    if bank_full:
        data["bank_account_number_masked"] = f"****{bank_full[-4:]}"

    parent_id = data.get("parent_entity_id")
    if parent_id is not None:
        parent = db.scalar(
            select(Entity).where(Entity.id == parent_id, _tenant_filter(tenant_id))
        )
        if parent is None:
            raise HTTPException(400, "parent_entity_id not found")

    ent = Entity(tenant_id=tenant_id, created_by_user_id=current.id, **data)
    db.add(ent)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig)
        if "uq_entities_companies_house_number" in msg:
            raise HTTPException(409, "companies_house_number already exists for this tenant")
        if "uq_entities_vat_number" in msg:
            raise HTTPException(409, "vat_number already exists for this tenant")
        raise HTTPException(409, "Integrity error")

    # Audit after flush (we need ent.id) but before commit so both land atomically.
    record_audit(
        db,
        action="Create", resource_type="entities", resource_id=ent.id,
        actor_user_id=current.id, entity_id=ent.id,
        field_changes=field_diff({}, _entity_snapshot(ent)),
        request=request,
    )
    db.commit()
    db.refresh(ent)
    detail = _detail_payload(db, tenant_id, ent)
    _strip_sensitive(detail, perms)
    return detail


@router.put("/{entity_id}", response_model=EntityDetail)
def update_entity(
    entity_id: uuid.UUID,
    payload: EntityUpdate,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("entities.edit")),
):
    tenant_id = principal.tenant_id
    ent = _get_or_404(db, tenant_id, entity_id)
    if not perms.has_on_entity("entities.edit", ent.id):
        raise HTTPException(403, "Insufficient scope for this entity")

    before = _entity_snapshot(ent)

    data = payload.model_dump(exclude_unset=True)
    unset_parent = data.pop("unset_parent", False)
    bank_full = data.pop("bank_account_number", None)
    if bank_full is not None:
        data["bank_account_number_masked"] = f"****{bank_full[-4:]}" if bank_full else None

    if unset_parent:
        ent.parent_entity_id = None
    elif "parent_entity_id" in data:
        new_parent = data["parent_entity_id"]
        if new_parent is not None:
            if new_parent == ent.id:
                raise HTTPException(400, "Entity cannot be its own parent")
            exists = db.scalar(
                select(Entity.id).where(Entity.id == new_parent, _tenant_filter(tenant_id))
            )
            if exists is None:
                raise HTTPException(400, "parent_entity_id not found")
            if _would_create_cycle(db, tenant_id, ent.id, new_parent):
                raise HTTPException(400, "Cannot set parent — would create a circular hierarchy")
        ent.parent_entity_id = new_parent
    data.pop("parent_entity_id", None)

    # Sensitive-field writes require entities.view_sensitive (OR entities.admin)
    sensitive_touched = any(k in data for k in ("bank_name", "bank_account_name")) or bank_full is not None
    if sensitive_touched and not (perms.has("entities.view_sensitive") or perms.has("entities.admin")):
        raise HTTPException(403, "Banking fields require entities.view_sensitive")

    for k, v in data.items():
        setattr(ent, k, v)

    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig)
        if "uq_entities_companies_house_number" in msg:
            raise HTTPException(409, "companies_house_number already exists for this tenant")
        if "uq_entities_vat_number" in msg:
            raise HTTPException(409, "vat_number already exists for this tenant")
        raise HTTPException(409, "Integrity error")

    after = _entity_snapshot(ent)
    changes = field_diff(before, after)
    if changes:
        record_audit(
            db,
            action="Update", resource_type="entities", resource_id=ent.id,
            actor_user_id=current.id, entity_id=ent.id,
            field_changes=changes, request=request,
        )
    db.commit()
    db.refresh(ent)
    detail = _detail_payload(db, tenant_id, ent)
    _strip_sensitive(detail, perms)
    return detail


@router.delete("/{entity_id}", status_code=204)
def delete_entity(
    entity_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("entities.delete")),
):
    tenant_id = principal.tenant_id
    ent = _get_or_404(db, tenant_id, entity_id)
    if not perms.has_on_entity("entities.delete", ent.id):
        raise HTTPException(403, "Insufficient scope for this entity")

    child_count = db.scalar(
        select(func.count()).select_from(Entity)
        .where(Entity.parent_entity_id == ent.id, _tenant_filter(tenant_id))
    ) or 0
    if child_count > 0:
        raise HTTPException(
            409,
            f"Cannot delete: {child_count} child entity(ies) reference this entity. "
            "Set status to Struck_off instead, or reassign children first.",
        )
    before = _entity_snapshot(ent)
    ent_id = ent.id  # preserve before deletion flushes
    try:
        record_audit(
            db,
            action="Delete", resource_type="entities", resource_id=ent_id,
            actor_user_id=current.id,
            field_changes=field_diff(before, {}),
            metadata={"entity_name": ent.name},
            request=request,
        )
        db.delete(ent)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Cannot delete: this entity is referenced by other records. Set status to Struck_off instead."
        )
