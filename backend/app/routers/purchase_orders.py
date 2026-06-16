"""Purchase Orders router — Chat 24 §R2 (Prompt 2.5).

Mounted under /api/v1/purchase-orders.

Endpoints:
  GET    /purchase-orders                               pos.view
  POST   /projects/{project_id}/purchase-orders         pos.create
  GET    /projects/{project_id}/purchase-orders         pos.view
  GET    /purchase-orders/{po_id}                       pos.view
  PATCH  /purchase-orders/{po_id}                       pos.edit | pos.edit_issued
  DELETE /purchase-orders/{po_id}                       pos.delete (draft only)
  POST   /purchase-orders/{po_id}/submit                pos.submit
  POST   /purchase-orders/{po_id}/issue                 pos.submit  (post-approval)
  POST   /purchase-orders/{po_id}/void                  pos.void
  POST   /purchase-orders/{po_id}/close                 pos.close

Pricing fields are gated by `pos.view_sensitive` at the serialisation
layer (set to null when ungranted).

Tenant scoping: Pattern α via `app.services.po_authz`.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import Principal, get_current_principal
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.services import purchase_orders as svc
from app.services.budget_errors import (
    BudgetLineRaceError, POLineIncompleteError, UnbudgetedAckRequiredError,
)
from app.services.po_authz import PoNotFound
from app.services.po_numbering import NumberingError
from app.services.po_transitions import TransitionError


router = APIRouter(tags=["purchase_orders"])


# ─────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────

class POLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # B105/B106 — Cost-code-first commercial line model.
    #
    # A line names a `cost_code_id` (+ optional `cost_code_subcategory_id`).
    # The service (`create_po`) resolves whether that cost code already has
    # a budget line on this budget (allocate into it) or not (mint one —
    # the unbudgeted path). "Unbudgeted" is now a server outcome, NOT a
    # caller assertion.
    #
    # `budget_line_id` remains accepted as a validated **back-compat
    # alias**: if supplied without `cost_code_id`, the service derives the
    # code from the line; if supplied alongside `cost_code_id`, the
    # service 422s on mismatch. New frontend stops sending it.
    #
    # The legacy `unbudgeted*` cluster is kept as DEPRECATED
    # accepted-but-ignored-for-routing fields so existing callers don't
    # break with `extra="forbid"`. They are treated only as fallbacks for
    # `cost_code_id` / `cost_code_subcategory_id` and emit a one-shot
    # deprecation warning per request (services.purchase_orders).
    #
    # `description`, `quantity`, `unit_rate`, `vat_rate` are OPTIONAL at
    # CREATE — drafts may be incomplete (so AI/manual fill happens
    # progressively). A completeness gate enforces them at SUBMIT
    # (see services.purchase_orders.submit completeness check, §3.8).
    cost_code_id: Optional[uuid.UUID] = None
    cost_code_subcategory_id: Optional[uuid.UUID] = None
    budget_line_id: Optional[uuid.UUID] = None
    # DEPRECATED — accept-but-ignore (see services.purchase_orders).
    unbudgeted: bool = False
    unbudgeted_cost_code_id: Optional[uuid.UUID] = None
    unbudgeted_subcategory_id: Optional[uuid.UUID] = None
    unbudgeted_reason: Optional[str] = Field(None, max_length=2000)
    description: Optional[str] = Field(None, max_length=5000)
    quantity: Optional[float] = Field(None, gt=0)
    unit_rate: Optional[float] = Field(None, ge=0)
    vat_rate: float = Field(20.00, ge=0, le=100)
    cost_code: Optional[str] = Field(None, max_length=20)
    unit: Optional[str] = Field(None, max_length=20)
    line_number: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = Field(None)

    @model_validator(mode="after")
    def _require_resolvable_cost_code(self):
        """B105/B106 — a line MUST resolve to a cost code. Acceptable
        inputs, in priority order (service applies them):

          1. `cost_code_id` present.
          2. `cost_code_id` absent + `budget_line_id` present (server
             derives the code from the budget line — back-compat alias).
          3. `cost_code_id` absent + deprecated
             `unbudgeted_cost_code_id` present (treated as `cost_code_id`,
             deprecation warning logged at service layer).
          4. None of the above → 422.

        If both `cost_code_id` and `budget_line_id` are present, the
        service validates agreement under the lock and 422s on mismatch
        — kept out of the schema so the "alias must agree" logic lives
        in one place.

        Field-level bounds (`> 0` for quantity if present, `>= 0` for
        unit_rate if present, `0..100` for vat_rate) are enforced by
        Field constraints above. Drafts may persist incomplete; submit
        applies the completeness gate (§3.8).
        """
        cc = self.cost_code_id or self.unbudgeted_cost_code_id
        if cc is None and self.budget_line_id is None:
            raise ValueError("cost_code_id is required")
        return self


class POCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: uuid.UUID
    budget_id: uuid.UUID
    # Pack 3.5 — optional package link (NULL = standalone "simple" PO).
    package_id: Optional[uuid.UUID] = None
    po_number_prefix_id: Optional[uuid.UUID] = None
    lines: List[POLineCreate] = Field(..., min_length=1)
    issue_date: Optional[date] = None
    required_by_date: Optional[date] = None
    delivery_address: Optional[str] = None
    delivery_notes: Optional[str] = None
    external_reference: Optional[str] = Field(None, max_length=100)
    approval_required: bool = False
    approval_reason: Optional[str] = None
    notes: Optional[str] = None


class POPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: Optional[uuid.UUID] = None
    budget_id: Optional[uuid.UUID] = None
    issue_date: Optional[date] = None
    required_by_date: Optional[date] = None
    delivery_address: Optional[str] = None
    delivery_notes: Optional[str] = None
    external_reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    approval_required: Optional[bool] = None
    approval_reason: Optional[str] = None


class POVoidBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=1, max_length=2000)


class POCloseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Optional[str] = Field(None, max_length=2000)


class POSubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_reason: Optional[str] = Field(None, max_length=2000)


class POApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: Optional[str] = Field(None, max_length=2000)


class PORejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str = Field(..., min_length=1, max_length=2000)


class POSendBackBody(BaseModel):
    # R7.0b — notes are REQUIRED. Empty/whitespace caught at the service
    # layer (ValueError → 422) so blank strings can't slip past
    # min_length=1.
    model_config = ConfigDict(extra="forbid")
    notes: str = Field(..., min_length=1, max_length=2000)


class POUnlockBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=1, max_length=2000)


# ─────────────────────────────────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────────────────────────────────

def _perm_dep(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> tuple[Principal, UserPermissions]:
    perms = compute_effective_permissions(
        db, principal.user.id, principal.tenant_id,
    )
    return principal, perms


def _require(perms: UserPermissions, code: str) -> None:
    if not perms.has(code):
        raise HTTPException(
            status_code=403, detail=f"Missing permission: {code}",
        )


# ─────────────────────────────────────────────────────────────────────────
# List / Create
# ─────────────────────────────────────────────────────────────────────────

@router.get("/purchase-orders")
def list_endpoint(
    project_id: Optional[uuid.UUID] = Query(None),
    supplier_id: Optional[uuid.UUID] = Query(None),
    status: Optional[List[str]] = Query(None, alias="status"),
    q: Optional[str] = Query(None, min_length=1, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")
    include_sensitive = perms.has("pos.view_sensitive")

    rows, total = svc.list_pos(
        db, user=principal.user, perms=perms,
        project_id=project_id, supplier_id=supplier_id,
        status_in=status, q=q,
        limit=limit, offset=offset,
    )
    return {
        "items": [
            svc.serialise(p, include_sensitive=include_sensitive) for p in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ─────────────────────────────────────────────────────────────────────────
# R5.5: Budget-line / budget scoped PO lists
# (lazy hydration for R6 inline-expand grid + opt-in expand-all)
# ─────────────────────────────────────────────────────────────────────────

@router.get("/budget-lines/{line_id}/purchase-orders")
def list_pos_by_budget_line_endpoint(
    line_id: uuid.UUID,
    status: Optional[List[str]] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    """List POs whose lines touch the given budget_line, gated by
    `pos.view`. Pricing fields gated by `pos.view_sensitive` at
    serialisation.

    Pattern α: an invisible / cross-tenant budget line surfaces as 404,
    NOT 403, NOT empty 200 — existence is not leaked. A visible line
    with zero POs returns 200 + empty list.
    """
    principal, perms = pair
    _require(perms, "pos.view")
    include_sensitive = perms.has("pos.view_sensitive")

    # Pattern α — resolve budget_line → budget → project → primary_entity.
    # tenant_id lives on Entity (Pattern α: not on Budget/BudgetLine/Project).
    from app.models.budgets import Budget, BudgetLine
    from app.models.projects import Project
    from app.models.entity import Entity
    row = db.execute(
        select(
            BudgetLine.id, BudgetLine.budget_id,
            Budget.project_id, Entity.tenant_id,
        )
        .join(Budget, Budget.id == BudgetLine.budget_id)
        .join(Project, Project.id == Budget.project_id)
        .join(Entity, Entity.id == Project.primary_entity_id)
        .where(BudgetLine.id == line_id)
    ).first()
    if row is None or row.tenant_id != principal.user.tenant_id:
        raise HTTPException(status_code=404, detail="Budget line not found")
    if not perms.is_super_admin:
        vis = svc.visible_project_ids(db, principal.user.id, principal.user.tenant_id)
        if vis is not None and row.project_id not in vis:
            raise HTTPException(status_code=404, detail="Budget line not found")

    rows, total = svc.list_pos(
        db, user=principal.user, perms=perms,
        budget_line_id=line_id,
        status_in=status,
        limit=limit, offset=offset,
    )
    return {
        "budget_line_id": str(line_id),
        "items": [svc.serialise(p, include_sensitive=include_sensitive) for p in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/budgets/{budget_id}/purchase-orders")
def list_pos_by_budget_endpoint(
    budget_id: uuid.UUID,
    status: Optional[List[str]] = Query(None, alias="status"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    """Bulk: list every PO touching any line of the given budget, with
    a per-budget-line index so the R6 grid can hydrate every expanded
    row from ONE call.

    Response shape:
      {
        "budget_id": "...",
        "items": [<po>, <po>, ...],          # unique POs, full payload (lines[] included)
        "by_budget_line": {                   # index: blid -> [po_id, po_id, ...]
            "<blid_a>": ["<po_id>", ...],
            "<blid_b>": [...]
        },
        "total": <unique PO count>,
        "limit": ..., "offset": ...
      }

    Each PO appears ONCE in `items`. The index is the only "key" that
    repeats a PO id across budget_line buckets (a PO touching two lines
    of the same budget is indexed under both blids but the payload is
    fetched once). The frontend grid hydrates an expanded row by mapping
    `by_budget_line[blid] -> items.find(po.id == po_id)`.

    Pricing fields gated by `pos.view_sensitive` (server-side). Invisible
    / cross-tenant budgets surface as 404 (Pattern α).
    """
    principal, perms = pair
    _require(perms, "pos.view")
    include_sensitive = perms.has("pos.view_sensitive")

    from app.models.budgets import Budget
    from app.models.projects import Project
    from app.models.entity import Entity
    row = db.execute(
        select(Budget.id, Budget.project_id, Entity.tenant_id)
        .join(Project, Project.id == Budget.project_id)
        .join(Entity, Entity.id == Project.primary_entity_id)
        .where(Budget.id == budget_id)
    ).first()
    if row is None or row.tenant_id != principal.user.tenant_id:
        raise HTTPException(status_code=404, detail="Budget not found")
    if not perms.is_super_admin:
        vis = svc.visible_project_ids(db, principal.user.id, principal.user.tenant_id)
        if vis is not None and row.project_id not in vis:
            raise HTTPException(status_code=404, detail="Budget not found")

    rows, total = svc.list_pos(
        db, user=principal.user, perms=perms,
        budget_id=budget_id,
        status_in=status,
        limit=limit, offset=offset,
    )

    items: list[dict[str, Any]] = []
    by_budget_line: dict[str, list[str]] = {}
    for po in rows:
        items.append(svc.serialise(po, include_sensitive=include_sensitive))
        po_id_str = str(po.id)
        for line in po.lines:
            key = str(line.budget_line_id)
            by_budget_line.setdefault(key, [])
            if po_id_str not in by_budget_line[key]:
                by_budget_line[key].append(po_id_str)

    return {
        "budget_id": str(budget_id),
        "items": items,
        "by_budget_line": by_budget_line,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/projects/{project_id}/purchase-orders", status_code=201)
def create_endpoint(
    project_id: uuid.UUID,
    body: POCreate,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.create")
    include_sensitive = perms.has("pos.view_sensitive")

    payload = body.model_dump(mode="python", exclude_unset=True)
    try:
        po = svc.create_po(
            db, user=principal.user, perms=perms,
            project_id=project_id, payload=payload, request=request,
        )
    except PoNotFound:
        # Pattern α — invisible project surfaces as 404, not 403.
        raise HTTPException(status_code=404, detail="Project not found")
    except BudgetLineRaceError as e:
        # B105/B106 §3.9 — concurrent mint race; client may retry.
        raise HTTPException(
            status_code=409,
            detail={
                "type": "budget_line_race",
                "title": "A budget line for this cost code was just "
                         "created concurrently; retry the request.",
                "cost_code_id": e.cost_code_id,
                "cost_code_subcategory_id": e.cost_code_subcategory_id,
            },
        )
    except NumberingError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(po)
    return svc.serialise(po, include_sensitive=include_sensitive)


@router.get("/projects/{project_id}/purchase-orders")
def list_project_pos_endpoint(
    project_id: uuid.UUID,
    supplier_id: Optional[uuid.UUID] = Query(None),
    status: Optional[List[str]] = Query(None, alias="status"),
    q: Optional[str] = Query(None, min_length=1, max_length=200),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    """Project-scoped PO list — thin wrapper over `svc.list_pos(...)`
    with `project_id` bound from the PATH.

    Mirrors `GET /purchase-orders` (line 154) byte-for-byte aside from
    the path-bound project_id. Closes a latent Chat 24 R5 gap: the
    frontend `listProjectPOs` (lib/api/purchaseOrders.js) has always
    hit this URL — Batch 1 + Batch 2 wired UIs against it. Pattern α
    project-visibility filtering is handled inside `svc.list_pos`
    (visible_project_ids), so an unknown / invisible project surfaces
    as 200 + empty list (mirrors the un-scoped handler's behaviour
    for non-matching filters — see AC4).
    """
    principal, perms = pair
    _require(perms, "pos.view")
    include_sensitive = perms.has("pos.view_sensitive")

    rows, total = svc.list_pos(
        db, user=principal.user, perms=perms,
        project_id=project_id, supplier_id=supplier_id,
        status_in=status, q=q,
        limit=limit, offset=offset,
    )
    return {
        "items": [
            svc.serialise(p, include_sensitive=include_sensitive) for p in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ─────────────────────────────────────────────────────────────────────────
# Get / Patch / Delete
# ─────────────────────────────────────────────────────────────────────────

@router.get("/purchase-orders/{po_id}")
def get_endpoint(
    po_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")
    include_sensitive = perms.has("pos.view_sensitive")
    try:
        po = svc.get_po(db, user=principal.user, perms=perms, po_id=po_id)
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return svc.serialise(po, include_sensitive=include_sensitive)


@router.patch("/purchase-orders/{po_id}")
def patch_endpoint(
    po_id: uuid.UUID,
    body: POPatch,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    # We don't pre-check pos.edit / pos.edit_issued here — the service
    # tier-guard does it and surfaces a more informative 403.
    _require(perms, "pos.view")
    include_sensitive = perms.has("pos.view_sensitive")

    payload = body.model_dump(mode="python", exclude_unset=True)
    try:
        po = svc.update_po(
            db, user=principal.user, perms=perms,
            po_id=po_id, payload=payload, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(po)
    return svc.serialise(po, include_sensitive=include_sensitive)


@router.delete("/purchase-orders/{po_id}", status_code=204)
def delete_endpoint(
    po_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.delete")
    try:
        svc.delete_po(
            db, user=principal.user, perms=perms,
            po_id=po_id, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()


# ─────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────

def _run_transition(
    db: Session, fn, *, principal: Principal, perms: UserPermissions,
    include_sensitive: bool, **kwargs,
):
    """Helper: run a transition fn, map errors, commit, serialise."""
    try:
        po = fn(db, user=principal.user, perms=perms, **kwargs)
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except UnbudgetedAckRequiredError as e:
        # B105/B106 Gate A — 409, body names the blocking line(s).
        raise HTTPException(
            status_code=409,
            detail={
                "type": "unbudgeted_ack_required",
                "title": "Director sign-off required on unbudgeted line(s)",
                "lines": e.blocking,
            },
        )
    except POLineIncompleteError as e:
        # B105/B106 §3.8 — completeness at submit/issue, 422.
        raise HTTPException(
            status_code=422,
            detail={
                "type": "po_line_incomplete",
                "title": "PO line(s) incomplete",
                "incomplete_line_numbers": e.line_numbers,
            },
        )
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    return svc.serialise(po, include_sensitive=include_sensitive)


@router.post("/purchase-orders/{po_id}/submit")
def submit_endpoint(
    po_id: uuid.UUID,
    body: POSubmitBody | None = None,
    request: Request = None,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    # Build pack §3.3 — /submit is gated by pos.create (the creator
    # persona triggers submit). The /issue endpoint (post-approval)
    # is gated by pos.issue.
    _require(perms, "pos.create")
    include_sensitive = perms.has("pos.view_sensitive")
    from app.services import po_approvals as approvals_svc
    try:
        po, approval = approvals_svc.submit_po_with_budget_gate(
            db, user=principal.user, perms=perms, po_id=po_id,
            submission_reason=(body.submission_reason if body else None),
            request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except UnbudgetedAckRequiredError as e:
        # B105/B106 Gate A — 409, PO stays Draft.
        raise HTTPException(
            status_code=409,
            detail={
                "type": "unbudgeted_ack_required",
                "title": "Director sign-off required on unbudgeted line(s)",
                "lines": e.blocking,
            },
        )
    except POLineIncompleteError as e:
        # B105/B106 §3.8 — incomplete PO line(s), 422; PO stays Draft.
        raise HTTPException(
            status_code=422,
            detail={
                "type": "po_line_incomplete",
                "title": "PO line(s) incomplete",
                "incomplete_line_numbers": e.line_numbers,
            },
        )
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    out = svc.serialise(po, include_sensitive=include_sensitive)
    out["approval"] = (
        approvals_svc.serialise_approval(approval) if approval else None
    )
    return out


@router.post("/purchase-orders/{po_id}/issue")
def issue_endpoint(
    po_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    # Build pack §3.3 — /issue (post-approval) gated by pos.issue.
    _require(perms, "pos.issue")
    return _run_transition(
        db, svc.issue_po,
        principal=principal, perms=perms,
        include_sensitive=perms.has("pos.view_sensitive"),
        po_id=po_id, request=request,
    )


@router.post("/purchase-orders/{po_id}/void")
def void_endpoint(
    po_id: uuid.UUID,
    body: POVoidBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.void")
    return _run_transition(
        db, svc.void_po,
        principal=principal, perms=perms,
        include_sensitive=perms.has("pos.view_sensitive"),
        po_id=po_id, reason=body.reason, request=request,
    )


@router.post("/purchase-orders/{po_id}/close")
def close_endpoint(
    po_id: uuid.UUID,
    body: POCloseBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.close")
    return _run_transition(
        db, svc.close_po,
        principal=principal, perms=perms,
        include_sensitive=perms.has("pos.view_sensitive"),
        po_id=po_id, reason=body.reason, request=request,
    )



# ─────────────────────────────────────────────────────────────────────────
# §R3 — Approval endpoints
# ─────────────────────────────────────────────────────────────────────────

@router.post("/purchase-orders/{po_id}/approve")
def approve_endpoint(
    po_id: uuid.UUID,
    body: POApproveBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.approve")
    include_sensitive = perms.has("pos.view_sensitive")
    from app.services import po_approvals as approvals_svc
    try:
        po, row = approvals_svc.approve_po(
            db, user=principal.user, perms=perms, po_id=po_id,
            notes=body.notes, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except approvals_svc.SelfApprovalForbidden:
        raise HTTPException(
            status_code=403,
            detail={
                "type": "po/self-approval-forbidden",
                "title": "Submitter cannot approve their own PO",
            },
        )
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    out = svc.serialise(po, include_sensitive=include_sensitive)
    out["approval"] = approvals_svc.serialise_approval(row)
    return out


@router.post("/purchase-orders/{po_id}/reject")
def reject_endpoint(
    po_id: uuid.UUID,
    body: PORejectBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.approve")
    include_sensitive = perms.has("pos.view_sensitive")
    from app.services import po_approvals as approvals_svc
    try:
        po, row = approvals_svc.reject_po(
            db, user=principal.user, perms=perms, po_id=po_id,
            notes=body.notes, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except approvals_svc.SelfApprovalForbidden:
        raise HTTPException(
            status_code=403,
            detail={
                "type": "po/self-approval-forbidden",
                "title": "Submitter cannot reject their own PO",
            },
        )
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    out = svc.serialise(po, include_sensitive=include_sensitive)
    out["approval"] = approvals_svc.serialise_approval(row)
    return out


@router.post("/purchase-orders/{po_id}/send-back")
def send_back_endpoint(
    po_id: uuid.UUID,
    body: POSendBackBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    """R7.0b — send an `approved` PO back to `draft` for correction.

    Permission gate is `pos.edit` OR `pos.approve` (either suffices).
    Rationale: within-budget auto-approved POs have no approver in the
    loop, so the creator (holds pos.edit) must be able to correct their
    own PO; over-budget POs that an approver formally approved (holds
    pos.approve) may later be found wrong and `reject` is unavailable
    post-approval. NO self-approval guard — send-back IS the correction
    path.
    """
    principal, perms = pair
    if not (perms.has("pos.edit") or perms.has("pos.approve")):
        raise HTTPException(
            status_code=403,
            detail={
                "type": "rbac/forbidden",
                "title": "Requires pos.edit or pos.approve",
            },
        )
    include_sensitive = perms.has("pos.view_sensitive")
    from app.services import po_approvals as approvals_svc
    try:
        po = approvals_svc.send_back_po(
            db, user=principal.user, perms=perms, po_id=po_id,
            notes=body.notes, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    out = svc.serialise(po, include_sensitive=include_sensitive)
    # Back to draft: no open approval row. The reason lives in audit.
    out["approval"] = None
    return out


@router.post("/purchase-orders/{po_id}/unlock")
def unlock_endpoint(
    po_id: uuid.UUID,
    body: POUnlockBody,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.edit")
    include_sensitive = perms.has("pos.view_sensitive")
    from app.services import po_approvals as approvals_svc
    try:
        po = approvals_svc.unlock_po(
            db, user=principal.user, perms=perms, po_id=po_id,
            reason=body.reason, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.commit()
    db.refresh(po)
    return svc.serialise(po, include_sensitive=include_sensitive)


@router.get("/purchase-orders/{po_id}/approvals")
def list_po_approvals_endpoint(
    po_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")
    from app.services import po_approvals as approvals_svc
    try:
        po = svc.get_po(db, user=principal.user, perms=perms, po_id=po_id)
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    rows = approvals_svc.list_approvals_for_po(db, po)
    return {
        "items": [approvals_svc.serialise_approval(r) for r in rows],
        "total": len(rows),
    }


@router.get("/projects/{project_id}/approvals/pending")
def list_project_pending_approvals(
    project_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.approve")
    from app.services import po_approvals as approvals_svc
    items = approvals_svc.list_pending_approvals(
        db, user=principal.user, perms=perms, project_id=project_id,
    )
    return {"items": items, "total": len(items)}


@router.get("/approvals/pending")
def list_all_pending_approvals(
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.approve")
    from app.services import po_approvals as approvals_svc
    items = approvals_svc.list_pending_approvals(
        db, user=principal.user, perms=perms,
    )
    return {"items": items, "total": len(items)}



# ─────────────────────────────────────────────────────────────────────────
# Receipts (Chat 24 §R4)
# ─────────────────────────────────────────────────────────────────────────

class ReceiptLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    po_line_id: uuid.UUID
    quantity_received: float = Field(..., gt=0)


class ReceiptPhotoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_path: str = Field(..., min_length=1, max_length=4000)
    file_type: Optional[str] = Field("application/octet-stream", max_length=100)
    file_size_bytes: int = Field(..., gt=0)
    original_filename: str = Field(..., min_length=1, max_length=500)
    caption: Optional[str] = Field(None, max_length=500)


class ReceiptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    received_date: date
    delivery_note_reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None)
    lines: List[ReceiptLineInput] = Field(..., min_length=1)
    photos: List[ReceiptPhotoInput] = Field(default_factory=list)


class ReceiptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    received_date: Optional[date] = None
    delivery_note_reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


def _map_receipt_error(e: Exception) -> HTTPException:
    """Translate a ReceiptError into the right HTTP status."""
    from app.services.po_receipts import ReceiptError
    if isinstance(e, ReceiptError):
        code = (e.code or "")
        if code == "po/receipt-wrong-status":
            return HTTPException(status_code=409, detail={"code": code, "message": str(e)})
        if code in (
            "po/receipt-edit-forbidden", "po/receipt-delete-forbidden",
            "po/receipt-backdate-forbidden",
        ):
            return HTTPException(status_code=403, detail={"code": code, "message": str(e)})
        return HTTPException(status_code=422, detail={"code": code, "message": str(e)})
    return HTTPException(status_code=422, detail=str(e))


@router.get("/purchase-orders/{po_id}/receipts")
def list_receipts_endpoint(
    po_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")
    from app.services import po_receipts as rsvc
    try:
        rows = rsvc.list_receipts(
            db, user=principal.user, perms=perms, po_id=po_id,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return {"items": [rsvc.serialise(r) for r in rows], "total": len(rows)}


@router.post("/purchase-orders/{po_id}/receipts", status_code=201)
def create_receipt_endpoint(
    po_id: uuid.UUID,
    body: ReceiptCreate,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.receipt")
    from app.services import po_receipts as rsvc
    payload = body.model_dump(mode="python", exclude_unset=False)
    try:
        receipt = rsvc.create_receipt(
            db, user=principal.user, perms=perms,
            po_id=po_id, payload=payload, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    except rsvc.ReceiptError as e:
        raise _map_receipt_error(e)
    db.commit()
    db.refresh(receipt)
    return rsvc.serialise(receipt)
    db.commit()
    db.refresh(receipt)
    return rsvc.serialise(receipt)


@router.get("/receipts/{receipt_id}")
def get_receipt_endpoint(
    receipt_id: uuid.UUID,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")
    from app.services import po_receipts as rsvc
    try:
        receipt = rsvc.get_receipt(
            db, user=principal.user, perms=perms, receipt_id=receipt_id,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return rsvc.serialise(receipt)


@router.patch("/receipts/{receipt_id}")
def patch_receipt_endpoint(
    receipt_id: uuid.UUID,
    body: ReceiptUpdate,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")  # base read access
    from app.services import po_receipts as rsvc
    payload = body.model_dump(mode="python", exclude_unset=True)
    try:
        receipt = rsvc.update_receipt(
            db, user=principal.user, perms=perms,
            receipt_id=receipt_id, payload=payload, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Receipt not found")
    except rsvc.ReceiptError as e:
        raise _map_receipt_error(e)
    db.commit()
    db.refresh(receipt)
    return rsvc.serialise(receipt)


@router.delete("/receipts/{receipt_id}")
def delete_receipt_endpoint(
    receipt_id: uuid.UUID,
    request: Request,
    pair: tuple[Principal, UserPermissions] = Depends(_perm_dep),
    db: Session = Depends(get_db),
):
    principal, perms = pair
    _require(perms, "pos.view")  # base read access
    from app.services import po_receipts as rsvc
    try:
        result = rsvc.delete_receipt(
            db, user=principal.user, perms=perms,
            receipt_id=receipt_id, request=request,
        )
    except PoNotFound:
        raise HTTPException(status_code=404, detail="Receipt not found")
    except rsvc.ReceiptError as e:
        raise _map_receipt_error(e)
    db.commit()
    return result
