"""Entities CRUD router — Prompt 1.1."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_tenant_id
from app.models import Entity, ENTITY_STATUSES, ENTITY_TYPES
from app.schemas.entity import (
    EntityCreate,
    EntityDetail,
    EntityListResponse,
    EntityRead,
    EntitySummary,
    EntityUpdate,
)

router = APIRouter(prefix="/entities", tags=["entities"])


# ---------- Helpers ----------

SORTABLE_FIELDS = {
    "name": Entity.name,
    "legal_name": Entity.legal_name,
    "entity_type": Entity.entity_type,
    "status": Entity.status,
    "companies_house_number": Entity.companies_house_number,
    "vat_number": Entity.vat_number,
    "year_end": Entity.year_end,
    "created_at": Entity.created_at,
    "updated_at": Entity.updated_at,
}


def _tenant_filter(tenant_id: uuid.UUID):
    return Entity.tenant_id == tenant_id


def _get_or_404(db: Session, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Entity:
    ent = db.scalar(
        select(Entity).where(Entity.id == entity_id, _tenant_filter(tenant_id))
    )
    if ent is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent


def _would_create_cycle(
    db: Session,
    tenant_id: uuid.UUID,
    entity_id: uuid.UUID,
    new_parent_id: uuid.UUID,
) -> bool:
    """Walk ancestors of new_parent_id; if we ever hit entity_id, it's a cycle."""
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


def _detail_payload(db: Session, tenant_id: uuid.UUID, ent: Entity) -> EntityDetail:
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


# ---------- Routes ----------

@router.get("", response_model=EntityListResponse)
def list_entities(
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    q: Optional[str] = Query(default=None, description="Search on name / legal_name"),
    entity_type: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    include_struck_off: bool = Query(default=False),
    parent_entity_id: Optional[uuid.UUID] = Query(default=None),
    sort: str = Query(default="name"),
    dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    conditions = [_tenant_filter(tenant_id)]
    if q:
        needle = f"%{q.strip()}%"
        conditions.append(or_(Entity.name.ilike(needle), Entity.legal_name.ilike(needle)))
    if entity_type:
        if entity_type not in ENTITY_TYPES:
            raise HTTPException(status_code=400, detail="Invalid entity_type filter")
        conditions.append(Entity.entity_type == entity_type)
    if status_filter:
        if status_filter not in ENTITY_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status filter")
        conditions.append(Entity.status == status_filter)
    elif not include_struck_off:
        # Default: hide Struck_off from active lists but keep queryable via status filter
        conditions.append(Entity.status != "Struck_off")
    if parent_entity_id is not None:
        conditions.append(Entity.parent_entity_id == parent_entity_id)

    total = db.scalar(
        select(func.count()).select_from(Entity).where(and_(*conditions))
    ) or 0

    sort_col = SORTABLE_FIELDS.get(sort, Entity.name)
    order = sort_col.desc() if dir == "desc" else sort_col.asc()

    rows = db.scalars(
        select(Entity)
        .where(and_(*conditions))
        .order_by(order, Entity.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return EntityListResponse(
        items=[EntityRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{entity_id}", response_model=EntityDetail)
def get_entity(
    entity_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    ent = _get_or_404(db, tenant_id, entity_id)
    return _detail_payload(db, tenant_id, ent)


@router.post("", response_model=EntityDetail, status_code=status.HTTP_201_CREATED)
def create_entity(
    payload: EntityCreate,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    data = payload.model_dump()
    # Mask bank account: only last 4 digits stored
    bank_full = data.pop("bank_account_number", None)
    if bank_full:
        data["bank_account_number_masked"] = f"****{bank_full[-4:]}"

    # Validate parent belongs to tenant & is not cyclic
    parent_id = data.get("parent_entity_id")
    if parent_id is not None:
        parent = db.scalar(
            select(Entity).where(
                Entity.id == parent_id, _tenant_filter(tenant_id)
            )
        )
        if parent is None:
            raise HTTPException(status_code=400, detail="parent_entity_id not found")

    ent = Entity(tenant_id=tenant_id, **data)
    db.add(ent)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig)
        if "uq_entities_companies_house_number" in msg:
            raise HTTPException(
                status_code=409,
                detail="companies_house_number already exists for this tenant",
            )
        if "uq_entities_vat_number" in msg:
            raise HTTPException(
                status_code=409,
                detail="vat_number already exists for this tenant",
            )
        raise HTTPException(status_code=409, detail="Integrity error")
    db.refresh(ent)
    return _detail_payload(db, tenant_id, ent)


@router.put("/{entity_id}", response_model=EntityDetail)
def update_entity(
    entity_id: uuid.UUID,
    payload: EntityUpdate,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    ent = _get_or_404(db, tenant_id, entity_id)
    data = payload.model_dump(exclude_unset=True)

    unset_parent = data.pop("unset_parent", False)
    bank_full = data.pop("bank_account_number", None)
    if bank_full is not None:
        data["bank_account_number_masked"] = (
            f"****{bank_full[-4:]}" if bank_full else None
        )

    # Cycle check when changing parent
    if unset_parent:
        ent.parent_entity_id = None
    elif "parent_entity_id" in data:
        new_parent = data["parent_entity_id"]
        if new_parent is not None:
            if new_parent == ent.id:
                raise HTTPException(
                    status_code=400,
                    detail="Entity cannot be its own parent",
                )
            exists = db.scalar(
                select(Entity.id).where(
                    Entity.id == new_parent, _tenant_filter(tenant_id)
                )
            )
            if exists is None:
                raise HTTPException(
                    status_code=400, detail="parent_entity_id not found"
                )
            if _would_create_cycle(db, tenant_id, ent.id, new_parent):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot set parent — would create a circular hierarchy",
                )
        ent.parent_entity_id = new_parent
    data.pop("parent_entity_id", None)

    for k, v in data.items():
        setattr(ent, k, v)

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig)
        if "uq_entities_companies_house_number" in msg:
            raise HTTPException(
                status_code=409,
                detail="companies_house_number already exists for this tenant",
            )
        if "uq_entities_vat_number" in msg:
            raise HTTPException(
                status_code=409,
                detail="vat_number already exists for this tenant",
            )
        raise HTTPException(status_code=409, detail="Integrity error")
    db.refresh(ent)
    return _detail_payload(db, tenant_id, ent)


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity(
    entity_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    ent = _get_or_404(db, tenant_id, entity_id)

    # Block delete if any child entities reference it.
    # (Additional tables — projects, users etc. — will add their own refs
    # in later prompts; with ON DELETE RESTRICT the DB will reject those.)
    child_count = db.scalar(
        select(func.count())
        .select_from(Entity)
        .where(Entity.parent_entity_id == ent.id, _tenant_filter(tenant_id))
    ) or 0
    if child_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete: {child_count} child entity(ies) reference this entity. "
                "Set status to Struck_off instead, or reassign children first."
            ),
        )

    try:
        db.delete(ent)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete: this entity is referenced by other records. "
                "Set status to Struck_off instead."
            ),
        )
