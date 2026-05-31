"""Budgets API — Prompt 2.4A (+ 2.4A.1 reorder precursor).

Mounts under /api/v1. 15 endpoints:

  Project-scoped:
    GET    /projects/{project_id}/budgets                       list
    POST   /projects/{project_id}/budgets/from-appraisal        create from approved appraisal

  Budget-scoped (single):
    GET    /budgets/{budget_id}                                 detail with lines/items
    POST   /budgets/{budget_id}/activate                        Draft → Active   [budgets.edit]
    POST   /budgets/{budget_id}/lock                            Active → Locked  [budgets.edit]
    POST   /budgets/{budget_id}/unlock                          Locked → Active  [budgets.admin]
    POST   /budgets/{budget_id}/close                           Active/Locked → Closed [budgets.edit]
    POST   /budgets/{budget_id}/new-version                     Clone, supersede [budgets.edit]

  Lines:
    PATCH  /budget-lines/{line_id}                              edit a single line
    DELETE /budget-lines/{line_id}                              delete a single line (Chat 23 R7.3)
    POST   /budget-lines/reorder                                bulk reorder (2.4A.1)

  Items (line-scoped + standalone):
    GET    /budget-lines/{line_id}/items
    POST   /budget-lines/{line_id}/items
    PATCH  /budget-line-items/{item_id}
    DELETE /budget-line-items/{item_id}

  Internal:
    POST   /internal/budgets/refresh-attention                  scan + toggle [budgets.admin]

Tenant scoping uses **Pattern α**: project-id resolution + `_visible_project_ids`
filter, mirroring routers/appraisals.py. No tenant_id columns on budget tables.

`view_sensitive` permission gates monetary cache fields (`total_actuals`,
`total_committed_not_invoiced`, `forecast_final_cost`, `variance_vs_budget`,
`variance_pct`). When the caller lacks `budgets.view_sensitive`, those keys
are **omitted** (not nullified).

All CUD endpoints write an audit_log row via services.audit.record_audit.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.appraisals import Appraisal
from app.models.budgets import Budget, BudgetLine, BudgetLineItem
from app.models.user import User
from app.schemas.budgets import (
    CreateBudgetFromAppraisalRequest, CreateNewVersionRequest,
    UpdateBudgetLineRequest, CreateBudgetLineItemRequest,
    UpdateBudgetLineItemRequest, ReorderBudgetLinesRequest,
)
from app.services import budgets as budget_svc
from app.services import budget_lines as line_svc
from app.services.audit import record_audit
from app.services.budget_errors import (
    BudgetCreationError, BudgetNotFoundError, BudgetSelfApprovalError,
    BudgetStateError, BudgetValidationError,
)


router = APIRouter(tags=["budgets"])


# ---------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------

def _map(exc: Exception):
    if isinstance(exc, BudgetNotFoundError):
        return HTTPException(404, str(exc) or "Budget not found")
    if isinstance(exc, BudgetValidationError):
        return HTTPException(400, str(exc))
    if isinstance(exc, BudgetCreationError):
        return HTTPException(400, str(exc))
    if isinstance(exc, BudgetSelfApprovalError):
        # Build Pack 2.4C R2.3 — segregation-of-duties refusal is an
        # authorisation refusal (403), NOT a state-machine violation (409).
        return HTTPException(403, str(exc))
    if isinstance(exc, BudgetStateError):
        return HTTPException(409, str(exc))
    return None


# ---------------------------------------------------------------------
# Serialisers (response shapes)
# ---------------------------------------------------------------------

def _serialise_item(i: BudgetLineItem) -> dict:
    return {
        "id": str(i.id),
        "budget_line_id": str(i.budget_line_id),
        "description": i.description,
        "quantity": str(i.quantity) if i.quantity is not None else None,
        "unit": i.unit,
        "rate": str(i.rate) if i.rate is not None else None,
        "amount": str(i.amount),
        "notes": i.notes,
        "display_order": i.display_order,
    }


def _attach_provisional_allocation(
    db: Session, budget: Budget, include_sensitive: bool,
) -> dict[uuid.UUID, str]:
    """Chat 23 R3.9b — compute the per-line provisional sale-price slice.

    Returns a {line_id -> string-decimal} map. Empty when the user lacks
    `budgets.view_sensitive`, the source appraisal has no GDV, or the
    budget has zero lines. Callers stamp the value onto the serialised
    line as `_allocated_sale_price_provisional` (leading underscore =
    "computed, not stored").

    Allocation = `appraisal.gdv_total / len(lines)` (equal split). The
    Build Pack §R3.9b labels this as the v1 provisional model; a
    Future_Tasks entry tracks the proper weighted-by-current_budget
    implementation. We use `gdv_total` because the Appraisal schema
    expresses sale revenue as Gross Development Value — there is no
    column literally named `sale_price` or `revenue`.
    """
    from decimal import Decimal
    if not include_sensitive:
        return {}
    lines = budget.lines or []
    if not lines:
        return {}
    appraisal = db.get(Appraisal, budget.source_appraisal_id)
    if appraisal is None:
        return {}
    gdv = getattr(appraisal, "gdv_total", None)
    if gdv is None or Decimal(gdv) <= 0:
        return {}
    per_line = (Decimal(gdv) / Decimal(len(lines))).quantize(Decimal("0.01"))
    return {line.id: str(per_line) for line in lines}


def _serialise_line(l: BudgetLine, *, include_sensitive: bool,
                    include_items: bool = False,
                    allocations: dict[uuid.UUID, str] | None = None) -> dict:
    d: dict[str, Any] = {
        "id": str(l.id),
        "budget_id": str(l.budget_id),
        "cost_code_id": str(l.cost_code_id),
        "cost_code_subcategory_id": (
            str(l.cost_code_subcategory_id) if l.cost_code_subcategory_id else None
        ),
        "entity_id": str(l.entity_id),
        "line_description": l.line_description,
        "original_budget": str(l.original_budget),
        "approved_changes": str(l.approved_changes),
        "current_budget": str(l.current_budget),
        "ftc_method": l.ftc_method,
        "forecast_to_complete": str(l.forecast_to_complete),
        "percentage_complete": (
            str(l.percentage_complete) if l.percentage_complete is not None else None
        ),
        "linked_programme_task_id": (
            str(l.linked_programme_task_id) if l.linked_programme_task_id else None
        ),
        "is_locked": l.is_locked,
        "requires_attention": l.requires_attention,
        "display_order": l.display_order,
        "notes": l.notes,
        "variance_status": l.variance_status,
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
    }
    if include_sensitive:
        d.update({
            "actuals_to_date": str(l.actuals_to_date),
            "committed_value": str(l.committed_value),
            "invoiced_against_commitment": str(l.invoiced_against_commitment),
            "committed_not_invoiced": str(l.committed_not_invoiced),
            "forecast_final_cost": str(l.forecast_final_cost),
            "variance_value": str(l.variance_value),
            "variance_pct": str(l.variance_pct),
        })
        if allocations is not None and l.id in allocations:
            # Chat 23 R3.9b: provisional sale-price slice for the
            # Forecast profit / margin % columns in BudgetGridV2.
            # Underscore prefix = computed (not a stored column).
            d["_allocated_sale_price_provisional"] = allocations[l.id]
    if include_items:
        d["items"] = [_serialise_item(it) for it in (l.items or [])]
    return d


def _serialise_budget_summary(b: Budget, *, include_sensitive: bool) -> dict:
    base: dict[str, Any] = {
        "id": str(b.id),
        "project_id": str(b.project_id),
        "source_appraisal_id": str(b.source_appraisal_id),
        "version_number": b.version_number,
        "version_label": b.version_label,
        "is_current": b.is_current,
        "status": b.status,
        "total_budget": str(b.total_budget),
        "summary_refreshed_at": (
            b.summary_refreshed_at.isoformat() if b.summary_refreshed_at else None
        ),
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }
    if include_sensitive:
        base.update({
            "total_actuals": str(b.total_actuals),
            "total_committed_not_invoiced": str(b.total_committed_not_invoiced),
            "total_forecast_to_complete": str(b.total_forecast_to_complete),
            "forecast_final_cost": str(b.forecast_final_cost),
            "variance_vs_budget": str(b.variance_vs_budget),
            "variance_pct": str(b.variance_pct),
        })
    return base


def _serialise_budget_detail(b: Budget, *, include_sensitive: bool,
                             db: Session | None = None) -> dict:
    d = _serialise_budget_summary(b, include_sensitive=include_sensitive)
    allocations: dict[uuid.UUID, str] = {}
    if db is not None:
        allocations = _attach_provisional_allocation(db, b, include_sensitive)
    d.update({
        "notes": b.notes,
        "locked_at": b.locked_at.isoformat() if b.locked_at else None,
        "locked_by_user_id": (
            str(b.locked_by_user_id) if b.locked_by_user_id else None
        ),
        "closed_at": b.closed_at.isoformat() if b.closed_at else None,
        "closed_by_user_id": (
            str(b.closed_by_user_id) if b.closed_by_user_id else None
        ),
        "created_by_user_id": str(b.created_by_user_id),
        "lines": [
            _serialise_line(l, include_sensitive=include_sensitive,
                            include_items=True, allocations=allocations)
            for l in sorted(b.lines or [], key=lambda x: x.display_order)
        ],
    })
    return d


# ---------------------------------------------------------------------
# Endpoint 1: list budgets for a project
# ---------------------------------------------------------------------

@router.get("/projects/{project_id}/budgets")
def list_project_budgets(
    project_id: uuid.UUID,
    is_current: Optional[bool] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.view")),
    db: Session = Depends(get_db),
):
    rows = budget_svc.list_budgets(
        db, user=current, perms=perms, project_id=project_id,
        status=status, is_current=is_current, limit=limit, offset=offset,
    )
    include_sensitive = perms.has("budgets.view_sensitive") or perms.is_super_admin
    return {
        "project_id": str(project_id),
        "items": [_serialise_budget_summary(b, include_sensitive=include_sensitive)
                  for b in rows],
        "count": len(rows),
    }


# ---------------------------------------------------------------------
# Endpoint 2: budget detail (≤5 query budget per Build Pack §R3 / B16)
# ---------------------------------------------------------------------

@router.get("/budgets/{budget_id}")
def get_budget(
    budget_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.view")),
    db: Session = Depends(get_db),
):
    try:
        b = budget_svc._load_budget_for_read(db, budget_id, current, perms)
    except BudgetNotFoundError:
        raise HTTPException(404, "Budget not found")
    include_sensitive = perms.has("budgets.view_sensitive") or perms.is_super_admin
    return _serialise_budget_detail(b, include_sensitive=include_sensitive, db=db)


# ---------------------------------------------------------------------
# Endpoint 3: create from approved appraisal
# ---------------------------------------------------------------------

@router.post("/projects/{project_id}/budgets/from-appraisal", status_code=201)
def create_from_appraisal(
    project_id: uuid.UUID,
    body: CreateBudgetFromAppraisalRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.create")),
    db: Session = Depends(get_db),
):
    try:
        b = budget_svc.create_from_appraisal(
            db, project_id=project_id,
            source_appraisal_id=body.source_appraisal_id,
            user=current, perms=perms,
        )
    except (BudgetCreationError, BudgetStateError, BudgetNotFoundError) as exc:
        raise _map(exc)

    if body.notes is not None:
        b.notes = body.notes

    record_audit(
        db, action="Create", resource_type="budgets",
        resource_id=b.id, actor_user_id=current.id,
        project_id=project_id, field_changes=[],
        metadata={
            "kind": "create_from_appraisal",
            "source_appraisal_id": str(body.source_appraisal_id),
            "version_number": b.version_number,
            "lines_created": len(b.lines or []),
            "total_budget": str(b.total_budget),
        },
        request=request,
    )
    db.commit()
    db.refresh(b)
    include_sensitive = perms.has("budgets.view_sensitive") or perms.is_super_admin
    return _serialise_budget_detail(b, include_sensitive=include_sensitive, db=db)


# ---------------------------------------------------------------------
# Endpoints 4–7: state machine transitions
# ---------------------------------------------------------------------

def _state_change(
    db: Session, request: Request, current: User, perms: UserPermissions,
    *, budget_id: uuid.UUID, transition: str, svc_fn,
) -> dict:
    try:
        before = budget_svc._load_budget_for_write(
            db, budget_id, current, perms, lock_for_update=False,
        )
        previous_status = before.status
        b = svc_fn(db, budget_id=budget_id, user=current, perms=perms)
    except (BudgetSelfApprovalError, BudgetStateError, BudgetNotFoundError) as exc:
        raise _map(exc)
    record_audit(
        db, action="Status_Change", resource_type="budgets",
        resource_id=b.id, actor_user_id=current.id,
        project_id=b.project_id, field_changes=[],
        metadata={
            "kind": transition,
            "previous_status": previous_status,
            "new_status": b.status,
        },
        request=request,
    )
    db.commit()
    db.refresh(b)
    include_sensitive = perms.has("budgets.view_sensitive") or perms.is_super_admin
    return _serialise_budget_detail(b, include_sensitive=include_sensitive, db=db)


@router.post("/budgets/{budget_id}/activate")
def activate_budget(
    budget_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    return _state_change(
        db, request, current, perms,
        budget_id=budget_id, transition="activate", svc_fn=budget_svc.activate,
    )


@router.post("/budgets/{budget_id}/lock")
def lock_budget(
    budget_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    return _state_change(
        db, request, current, perms,
        budget_id=budget_id, transition="lock", svc_fn=budget_svc.lock,
    )


@router.post("/budgets/{budget_id}/unlock")
def unlock_budget(
    budget_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.admin")),
    db: Session = Depends(get_db),
):
    return _state_change(
        db, request, current, perms,
        budget_id=budget_id, transition="unlock", svc_fn=budget_svc.unlock,
    )


@router.post("/budgets/{budget_id}/close")
def close_budget(
    budget_id: uuid.UUID, request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    return _state_change(
        db, request, current, perms,
        budget_id=budget_id, transition="close", svc_fn=budget_svc.close,
    )


# ---------------------------------------------------------------------
# Endpoint 8: new version
# ---------------------------------------------------------------------

@router.post("/budgets/{budget_id}/new-version", status_code=201)
def new_version(
    budget_id: uuid.UUID,
    body: CreateNewVersionRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    try:
        old, new = budget_svc.new_version(
            db, budget_id=budget_id, user=current, perms=perms,
            label=body.version_label,
        )
    except (BudgetStateError, BudgetNotFoundError) as exc:
        raise _map(exc)
    if body.notes is not None:
        new.notes = body.notes
    record_audit(
        db, action="Create", resource_type="budgets",
        resource_id=new.id, actor_user_id=current.id,
        project_id=new.project_id, field_changes=[],
        metadata={
            "kind": "new_version",
            "superseded_id": str(old.id),
            "previous_version_number": old.version_number,
            "new_version_number": new.version_number,
            "version_label": body.version_label,
            "lines_carried": len(new.lines or []),
        },
        request=request,
    )
    db.commit()
    db.refresh(new)
    include_sensitive = perms.has("budgets.view_sensitive") or perms.is_super_admin
    return _serialise_budget_detail(new, include_sensitive=include_sensitive, db=db)


# ---------------------------------------------------------------------
# Endpoint 9: PATCH a budget line
# ---------------------------------------------------------------------

@router.patch("/budget-lines/{line_id}")
def update_line(
    line_id: uuid.UUID,
    body: UpdateBudgetLineRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    # Resolve the budget id with a single targeted column lookup so we can
    # delegate to bulk_update_lines (which scopes via Budget).
    bid = db.scalar(
        select(BudgetLine.budget_id).where(BudgetLine.id == line_id)
    )
    if bid is None:
        raise HTTPException(404, "Budget line not found")
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(400, "No editable fields supplied")
    try:
        b, changes = line_svc.bulk_update_lines(
            db, budget_id=bid, user=current, perms=perms,
            updates=[{"id": line_id, **payload}],
        )
    except (BudgetStateError, BudgetNotFoundError) as exc:
        raise _map(exc)
    line = next((ln for ln in b.lines if ln.id == line_id), None)
    if line is None:
        raise HTTPException(404, "Budget line not found")
    record_audit(
        db, action="Update", resource_type="budget_lines",
        resource_id=line_id, actor_user_id=current.id,
        project_id=b.project_id,
        field_changes=[
            {"field": k, "old": v["before"], "new": v["after"]}
            for entry in changes for k, v in entry["changes"].items()
        ],
        metadata={"budget_id": str(b.id), "kind": "line_update"},
        request=request,
    )
    db.commit()
    db.refresh(line)
    include_sensitive = perms.has("budgets.view_sensitive") or perms.is_super_admin
    return _serialise_line(line, include_sensitive=include_sensitive,
                           include_items=True)


# ---------------------------------------------------------------------
# Endpoint 9c: delete a single budget line (Chat 23 R7.3)
# ---------------------------------------------------------------------

@router.delete("/budget-lines/{line_id}", status_code=204)
def delete_budget_line(
    line_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    """Delete a single budget line.

    Used by the R7.3 bulk-delete fan-out (frontend loops sequential
    DELETEs, capped at 100). Per Build Pack A locked decision: NO bulk
    endpoint. One audit row per delete.

    Error map:
      - 403  caller lacks `budgets.edit`
      - 404  line unknown or cross-tenant
      - 409  budget is Locked / Closed / Superseded
    """
    line = db.get(BudgetLine, line_id)
    if line is None:
        raise HTTPException(404, "Budget line not found")
    budget_id = line.budget_id
    project_id = db.scalar(select(Budget.project_id).where(Budget.id == budget_id))
    line_description = line.line_description or ""
    cost_code_id = str(line.cost_code_id) if line.cost_code_id else None
    try:
        line_svc.delete_line(
            db, budget_id=budget_id, line_id=line_id,
            user=current, perms=perms,
        )
    except (BudgetStateError, BudgetNotFoundError) as exc:
        raise _map(exc)
    record_audit(
        db, action="Delete", resource_type="budget_lines",
        resource_id=line_id, actor_user_id=current.id,
        project_id=project_id, field_changes=[],
        metadata={
            "budget_id": str(budget_id),
            "kind": "line_delete",
            "line_description": line_description,
            "cost_code_id": cost_code_id,
        },
        request=request,
    )
    db.commit()
    return None


# ---------------------------------------------------------------------
# Endpoint 9b: bulk reorder lines (Prompt 2.4A.1 — precursor for 2.4B-i)
# ---------------------------------------------------------------------

@router.post("/budget-lines/reorder")
def reorder_lines(
    body: ReorderBudgetLinesRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    """Atomically reorder every line on a budget.

    Body: `{ budget_id, ordered_line_ids: UUID[] }`. The list MUST include
    every line on the budget exactly once. Returns the refreshed budget
    detail (mirrors lifecycle endpoint shape).

    Error map:
      - 400  ordered_line_ids partial / duplicates / foreign
      - 403  caller lacks `budgets.edit`
      - 404  budget unknown or cross-tenant
      - 409  budget is Locked / Closed / Superseded
    """
    try:
        b, changes = line_svc.bulk_reorder_lines(
            db, budget_id=body.budget_id, user=current, perms=perms,
            ordered_line_ids=list(body.ordered_line_ids),
        )
    except (BudgetValidationError, BudgetStateError, BudgetNotFoundError) as exc:
        raise _map(exc)

    record_audit(
        db, action="Update", resource_type="budget_lines",
        resource_id=b.id, actor_user_id=current.id,
        project_id=b.project_id,
        field_changes=[
            {"field": "display_order", "old": str(c["before"]),
             "new": str(c["after"])}
            for c in changes
        ],
        metadata={
            "budget_id": str(b.id),
            "kind": "lines_reorder",
            "lines_affected": len(changes),
            "total_lines": len(body.ordered_line_ids),
        },
        request=request,
    )
    db.commit()
    db.refresh(b)
    include_sensitive = perms.has("budgets.view_sensitive") or perms.is_super_admin
    return _serialise_budget_detail(b, include_sensitive=include_sensitive, db=db)



# ---------------------------------------------------------------------
# Endpoints 10–11: line items list + create
# ---------------------------------------------------------------------

@router.get("/budget-lines/{line_id}/items")
def list_line_items(
    line_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.view")),
    db: Session = Depends(get_db),
):
    # Tenant scope via budget → project resolution.
    line = db.get(BudgetLine, line_id)
    if line is None:
        raise HTTPException(404, "Budget line not found")
    try:
        budget_svc._load_budget_for_read(db, line.budget_id, current, perms)
    except BudgetNotFoundError:
        raise HTTPException(404, "Budget line not found")
    items = sorted(line.items or [], key=lambda x: x.display_order)
    return {"line_id": str(line_id), "items": [_serialise_item(i) for i in items]}


@router.post("/budget-lines/{line_id}/items", status_code=201)
def create_line_item(
    line_id: uuid.UUID,
    body: CreateBudgetLineItemRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    try:
        item = line_svc.create_item(
            db, line_id=line_id, user=current, perms=perms,
            description=body.description, amount=body.amount,
            quantity=body.quantity, unit=body.unit, rate=body.rate,
            notes=body.notes,
        )
    except (BudgetStateError, BudgetNotFoundError) as exc:
        raise _map(exc)
    line = db.get(BudgetLine, line_id)
    budget = db.get(Budget, line.budget_id) if line else None
    record_audit(
        db, action="Create", resource_type="budget_line_items",
        resource_id=item.id, actor_user_id=current.id,
        project_id=budget.project_id if budget else None,
        field_changes=[],
        metadata={
            "budget_line_id": str(line_id),
            "amount": str(item.amount),
        },
        request=request,
    )
    db.commit()
    db.refresh(item)
    return _serialise_item(item)


# ---------------------------------------------------------------------
# Endpoints 12–13: line item PATCH + DELETE
# ---------------------------------------------------------------------

@router.patch("/budget-line-items/{item_id}")
def update_line_item(
    item_id: uuid.UUID,
    body: UpdateBudgetLineItemRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    item_lookup = db.get(BudgetLineItem, item_id)
    if item_lookup is None:
        raise HTTPException(404, "Budget line item not found")
    line_id = item_lookup.budget_line_id
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(400, "No editable fields supplied")
    try:
        item, changes = line_svc.update_item(
            db, line_id=line_id, item_id=item_id,
            user=current, perms=perms, fields=payload,
        )
    except (BudgetStateError, BudgetNotFoundError) as exc:
        raise _map(exc)
    line = db.get(BudgetLine, line_id)
    budget = db.get(Budget, line.budget_id) if line else None
    record_audit(
        db, action="Update", resource_type="budget_line_items",
        resource_id=item.id, actor_user_id=current.id,
        project_id=budget.project_id if budget else None,
        field_changes=[
            {"field": k, "old": v["before"], "new": v["after"]}
            for k, v in changes.items()
        ],
        metadata={"budget_line_id": str(line_id), "kind": "item_update"},
        request=request,
    )
    db.commit()
    db.refresh(item)
    return _serialise_item(item)


@router.delete("/budget-line-items/{item_id}", status_code=204)
def delete_line_item(
    item_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.edit")),
    db: Session = Depends(get_db),
):
    item_lookup = db.get(BudgetLineItem, item_id)
    if item_lookup is None:
        raise HTTPException(404, "Budget line item not found")
    line_id = item_lookup.budget_line_id
    line = db.get(BudgetLine, line_id)
    budget = db.get(Budget, line.budget_id) if line else None
    project_id = budget.project_id if budget else None
    item_amount = str(item_lookup.amount)
    try:
        line_svc.delete_item(
            db, line_id=line_id, item_id=item_id,
            user=current, perms=perms,
        )
    except (BudgetStateError, BudgetNotFoundError) as exc:
        raise _map(exc)
    record_audit(
        db, action="Delete", resource_type="budget_line_items",
        resource_id=item_id, actor_user_id=current.id,
        project_id=project_id, field_changes=[],
        metadata={"budget_line_id": str(line_id), "amount": item_amount},
        request=request,
    )
    db.commit()
    return None


# ---------------------------------------------------------------------
# Endpoint 14: refresh-attention scan (admin-gated)
# ---------------------------------------------------------------------

@router.post("/internal/budgets/refresh-attention")
def refresh_attention(
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.admin")),
    db: Session = Depends(get_db),
):
    result = line_svc.scan_requires_attention(db, user=current, perms=perms)
    record_audit(
        db, action="Update", resource_type="budgets",
        resource_id=current.id,  # synthetic: scan is session-scoped, no single resource
        actor_user_id=current.id,
        field_changes=[],
        metadata={
            "kind": "scan_requires_attention",
            "flagged": result["flagged"],
            "cleared": result["cleared"],
            "scanned": result["scanned"],
        },
        request=request,
    )
    db.commit()
    return result
