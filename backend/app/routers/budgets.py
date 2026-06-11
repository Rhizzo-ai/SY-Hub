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

B88 Pack 2 (Chat 51) — `view_sensitive` semantic split:
  * LINE-level money keys (`actuals_to_date`, `committed_value`,
    `invoiced_against_commitment`, `committed_not_invoiced`,
    `forecast_final_cost`, `variance_value`, `variance_pct`,
    `actuals_this_period`) are now returned to ALL callers, but ONLY
    on lines the caller is entitled to see (Tier 2 = construction
    scope, filtered by `cost_code_scope`).
  * HEADER-level cached totals on Budget — `total_budget`,
    `total_actuals`, `total_committed_not_invoiced`,
    `total_forecast_to_complete`, `forecast_final_cost`,
    `variance_vs_budget`, `variance_pct` — are full-scope-only,
    because the cache aggregates ALL lines (land / sales / etc.) and
    is not safe to leak to construction-scope callers. Tier 2 obtains
    its scoped totals exclusively from `GET /budgets/{id}/grid`.
  * `_allocated_sale_price_provisional` (line-level) stays full-scope
    only.

All CUD endpoints write an audit_log row via services.audit.record_audit.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.appraisals import Appraisal
from app.models.budgets import Budget, BudgetLine, BudgetLineItem
from app.models.cost_codes import CostCode, CostCodeSection
from app.models.user import User
from app.schemas.budgets import (
    CreateBudgetFromAppraisalRequest, CreateNewVersionRequest,
    UpdateBudgetLineRequest, CreateBudgetLineItemRequest,
    UpdateBudgetLineItemRequest, ReorderBudgetLinesRequest,
)
from app.services import budgets as budget_svc
from app.services import budget_lines as line_svc
from app.services import cost_code_scope as scope_svc
from app.services.audit import record_audit
from app.services.budget_errors import (
    BudgetCreationError, BudgetNotFoundError, BudgetSelfApprovalError,
    BudgetStateError, BudgetValidationError,
)


log = logging.getLogger(__name__)
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


def _serialise_line(l: BudgetLine, *, include_sensitive: bool,  # noqa: E741
                    include_items: bool = False,
                    allocations: dict[uuid.UUID, str] | None = None) -> dict:
    # B88 Pack 2 §R5 / D4 — line-level money keys are now visible to
    # ALL callers on in-scope lines (was view_sensitive-gated). Scope
    # filtering happens upstream in the serialiser/router. The
    # `include_sensitive` parameter is retained because it still gates
    # the Tier-1-only `_allocated_sale_price_provisional` derived column.
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
        # Chat 39 §R2 B-CONTINGENCY: exposed so the contingency-drawdown
        # BCR dialog can validate the source line. Default false; never
        # null in DB (server_default on the column).
        "is_contingency": bool(l.is_contingency),
        "created_at": l.created_at.isoformat() if l.created_at else None,
        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        # B88 Pack 2 §R5 / D4 — money keys promoted out of the
        # `include_sensitive` block: ALL callers see them on in-scope
        # lines. The Tier-2 scope filter is applied upstream so a
        # construction-only caller never reaches these keys for a land
        # / sales / professional-fees line in the first place.
        "actuals_to_date": str(l.actuals_to_date),
        "committed_value": str(l.committed_value),
        "invoiced_against_commitment": str(l.invoiced_against_commitment),
        "committed_not_invoiced": str(l.committed_not_invoiced),
        "actuals_this_period": (
            str(l.actuals_this_period) if l.actuals_this_period is not None else None
        ),
        "forecast_final_cost": str(l.forecast_final_cost),
        "variance_value": str(l.variance_value),
        "variance_pct": str(l.variance_pct),
    }
    if include_sensitive:
        if allocations is not None and l.id in allocations:
            # Chat 23 R3.9b: provisional sale-price slice for the
            # Forecast profit / margin % columns in BudgetGridV2.
            # Underscore prefix = computed (not a stored column).
            # B88 Pack 2: stays full-scope-only (never on Tier 2).
            d["_allocated_sale_price_provisional"] = allocations[l.id]
    if include_items:
        d["items"] = [_serialise_item(it) for it in (l.items or [])]
    return d


def _serialise_budget_summary(b: Budget, *, include_sensitive: bool,
                              scope: str = "full") -> dict:
    """Serialise a budget header row.

    B88 Pack 2 §R5: ALL cached header money keys (incl. `total_budget`)
    are now full-scope-only. Tier 2 callers get scoped totals from
    `GET /budgets/{id}/grid` exclusively. The `scope` parameter
    distinguishes a "full-entitled but constructionally-narrowed" call
    (also drops the keys) from a true full-budget read.
    """
    emit_header_money = include_sensitive and scope == "full"
    base: dict[str, Any] = {
        "id": str(b.id),
        "project_id": str(b.project_id),
        "source_appraisal_id": str(b.source_appraisal_id),
        "version_number": b.version_number,
        "version_label": b.version_label,
        "is_current": b.is_current,
        "status": b.status,
        "summary_refreshed_at": (
            b.summary_refreshed_at.isoformat() if b.summary_refreshed_at else None
        ),
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }
    if emit_header_money:
        base["total_budget"] = str(b.total_budget)
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
                             db: Session | None = None,
                             scope: str = "full",
                             construction_codes: set | None = None) -> dict:
    """Serialise a budget detail body, applying construction-scope
    line filter when scope='construction' (Build Pack §5 fix 1).
    """
    d = _serialise_budget_summary(
        b, include_sensitive=include_sensitive, scope=scope,
    )
    allocations: dict[uuid.UUID, str] = {}
    if db is not None and scope == "full":
        allocations = _attach_provisional_allocation(db, b, include_sensitive)

    lines = sorted(b.lines or [], key=lambda x: x.display_order)
    if scope == "construction":
        if construction_codes is None:
            from app.services.cost_code_scope import construction_cost_code_ids
            construction_codes = construction_cost_code_ids(db) if db else set()
        lines = [ln for ln in lines if ln.cost_code_id in construction_codes]

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
            for l in lines  # noqa: E741
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
    scope = scope_svc.caller_scope(perms)
    return {
        "project_id": str(project_id),
        "items": [_serialise_budget_summary(
            b, include_sensitive=include_sensitive, scope=scope,
        ) for b in rows],
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
    scope = scope_svc.caller_scope(perms)
    return _serialise_budget_detail(
        b, include_sensitive=include_sensitive, db=db, scope=scope,
    )


# ---------------------------------------------------------------------
# Endpoint 2b: grouped grid (B88 Pack 2)
# ---------------------------------------------------------------------

_TOTALS_KEYS = (
    "original_budget", "approved_changes", "current_budget",
    "committed_value", "invoiced_against_commitment",
    "committed_not_invoiced", "actuals_to_date", "actuals_this_period",
    "forecast_to_complete", "forecast_final_cost",
    "variance_value",
)


def _zero_totals() -> dict[str, Decimal]:
    return {k: Decimal("0") for k in _TOTALS_KEYS}


def _line_totals(line: BudgetLine) -> dict[str, Decimal]:
    return {
        "original_budget": Decimal(line.original_budget or 0),
        "approved_changes": Decimal(line.approved_changes or 0),
        "current_budget": Decimal(line.current_budget or 0),
        "committed_value": Decimal(line.committed_value or 0),
        "invoiced_against_commitment": Decimal(
            line.invoiced_against_commitment or 0
        ),
        "committed_not_invoiced": Decimal(line.committed_not_invoiced or 0),
        "actuals_to_date": Decimal(line.actuals_to_date or 0),
        "actuals_this_period": Decimal(line.actuals_this_period or 0),
        "forecast_to_complete": Decimal(line.forecast_to_complete or 0),
        "forecast_final_cost": Decimal(line.forecast_final_cost or 0),
        "variance_value": Decimal(line.variance_value or 0),
    }


def _add_totals(dst: dict, src: dict) -> None:
    for k in _TOTALS_KEYS:
        dst[k] = dst[k] + src[k]


def _finalise_totals(totals: dict) -> dict:
    """Compute variance_pct + status from accumulated current_budget /
    variance_value Decimals, then stringify."""
    cb = totals["current_budget"]
    vv = totals["variance_value"]
    if cb and cb != 0:
        pct = (vv / cb * Decimal("100")).quantize(Decimal("0.001"))
    else:
        pct = Decimal("0.000")
    out = {k: str(totals[k].quantize(Decimal("0.01"))) for k in _TOTALS_KEYS}
    out["variance_pct"] = str(pct)
    out["variance_status"] = budget_svc._classify_variance(pct)
    return out


@router.get("/budgets/{budget_id}/grid")
def get_budget_grid(
    budget_id: uuid.UUID,
    scope: Optional[str] = Query(default=None, pattern="^(full|construction)$"),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("budgets.view")),
    db: Session = Depends(get_db),
):
    """B88 Pack 2 §4 — grouped Job-Costing grid.

    Response: grouped tree (group → subgroup → lines) with subtotals
    rolled up from included lines. Tier 2 (construction-scope) callers
    receive ONLY in-scope groups; out-of-scope groups are OMITTED
    (never present-but-empty). `?scope=` may only narrow the caller's
    entitled scope; widening attempts are silently clamped.
    """
    try:
        b = budget_svc._load_budget_for_read(db, budget_id, current, perms)
    except BudgetNotFoundError:
        raise HTTPException(404, "Budget not found")

    include_sensitive = perms.has("budgets.view_sensitive") or perms.is_super_admin
    effective_scope = scope_svc.resolve_request_scope(perms, scope)

    # Pre-load cost codes + sections in two queries (no N+1).
    cost_codes_by_id: dict[uuid.UUID, CostCode] = {
        c.id: c for c in db.scalars(select(CostCode)).all()
    }
    sections_by_id: dict[uuid.UUID, CostCodeSection] = {
        s.id: s for s in db.scalars(select(CostCodeSection)).all()
    }

    allocations: dict[uuid.UUID, str] = {}
    if effective_scope == "full":
        allocations = _attach_provisional_allocation(db, b, include_sensitive)

    # Synthetic "Unassigned" section for orphaned lines (full scope only).
    UNASSIGNED_KEY = "__unassigned__"

    # Determine for each line which section path it belongs to.
    # Returns (group_section_id_or_key, subgroup_section_id_or_None,
    # is_construction_scoped) — last bool determines tier-2 inclusion.
    def _classify(line: BudgetLine):
        cc = cost_codes_by_id.get(line.cost_code_id)
        if cc is None:
            return (UNASSIGNED_KEY, None, False)
        sec = sections_by_id.get(cc.section_id)
        if sec is None:
            return (UNASSIGNED_KEY, None, False)
        if sec.parent_section_id is not None:
            parent = sections_by_id.get(sec.parent_section_id)
            if parent is None:
                # Orphan parent — fall back to the subgroup as a group.
                in_scope = sec.included_in_construction_scope
                return (sec.id, None, in_scope)
            in_scope = parent.included_in_construction_scope or sec.included_in_construction_scope
            return (parent.id, sec.id, in_scope)
        return (sec.id, None, sec.included_in_construction_scope)

    # Bucket lines.
    # groups: { group_key -> {section, subgroups: {sub_id -> [lines]}, direct_lines: [lines]} }
    groups: dict[Any, dict[str, Any]] = {}
    for line in (b.lines or []):
        group_key, sub_id, in_scope = _classify(line)
        if effective_scope == "construction" and not in_scope:
            continue
        if effective_scope == "construction" and group_key == UNASSIGNED_KEY:
            continue
        if group_key not in groups:
            groups[group_key] = {
                "direct_lines": [],
                "subgroups": {},  # sub_id -> [lines]
            }
        if sub_id is None:
            groups[group_key]["direct_lines"].append(line)
        else:
            groups[group_key]["subgroups"].setdefault(sub_id, []).append(line)

    # Order groups by display_order; unassigned trails last.
    def _group_sort_key(key):
        if key == UNASSIGNED_KEY:
            return (1, 9999, "")
        sec = sections_by_id.get(key)
        if sec is None:
            return (1, 9998, "")
        return (0, sec.display_order, sec.code)

    sorted_group_keys = sorted(groups.keys(), key=_group_sort_key)

    # Code display ordering for lines.
    def _line_sort_key(line: BudgetLine):
        cc = cost_codes_by_id.get(line.cost_code_id)
        cc_order = cc.display_order if cc else 99999
        return (cc_order, line.display_order or 0)

    out_groups: list[dict] = []
    budget_totals = _zero_totals()
    for gkey in sorted_group_keys:
        bucket = groups[gkey]
        group_totals = _zero_totals()

        # Build subgroup nodes
        sub_nodes: list[dict] = []
        for sub_id, sub_lines in bucket["subgroups"].items():
            sub_totals = _zero_totals()
            line_nodes: list[dict] = []
            for ln in sorted(sub_lines, key=_line_sort_key):
                _add_totals(sub_totals, _line_totals(ln))
                line_nodes.append(_grid_line_node(ln, cost_codes_by_id,
                                                  include_sensitive, allocations,
                                                  effective_scope))
            sub_sec = sections_by_id.get(sub_id)
            sub_nodes.append({
                "section_id": str(sub_id),
                "code": sub_sec.code if sub_sec else "?",
                "name": sub_sec.name if sub_sec else "Unknown",
                "display_order": sub_sec.display_order if sub_sec else 0,
                "included_in_construction_scope": (
                    bool(sub_sec.included_in_construction_scope) if sub_sec else False
                ),
                "subtotals": _finalise_totals(sub_totals),
                "lines": line_nodes,
            })
            _add_totals(group_totals, sub_totals)
        sub_nodes.sort(key=lambda n: n["display_order"])

        # Build direct lines under the group (lines not under any subgroup)
        direct_line_nodes: list[dict] = []
        for ln in sorted(bucket["direct_lines"], key=_line_sort_key):
            _add_totals(group_totals, _line_totals(ln))
            direct_line_nodes.append(_grid_line_node(ln, cost_codes_by_id,
                                                     include_sensitive, allocations,
                                                     effective_scope))

        if gkey == UNASSIGNED_KEY:
            group_node = {
                "section_id": None,
                "code": "?",
                "name": "Unassigned",
                "display_order": 9999,
                "included_in_construction_scope": False,
                "subtotals": _finalise_totals(group_totals),
                "subgroups": sub_nodes,
                "lines": direct_line_nodes,
            }
            log.warning(
                "Orphan budget lines on budget %s — %d direct + %d subgrouped",
                str(b.id), len(direct_line_nodes), len(sub_nodes),
            )
        else:
            sec = sections_by_id.get(gkey)
            group_node = {
                "section_id": str(gkey),
                "code": sec.code if sec else "?",
                "name": sec.name if sec else "Unknown",
                "display_order": sec.display_order if sec else 0,
                "included_in_construction_scope": (
                    bool(sec.included_in_construction_scope) if sec else False
                ),
                "subtotals": _finalise_totals(group_totals),
                "subgroups": sub_nodes,
                "lines": direct_line_nodes,
            }
        out_groups.append(group_node)
        _add_totals(budget_totals, group_totals)

    # Header — non-money + computed totals.
    header = {
        "id": str(b.id),
        "project_id": str(b.project_id),
        "version_number": b.version_number,
        "version_label": b.version_label,
        "is_current": b.is_current,
        "status": b.status,
        "summary_refreshed_at": (
            b.summary_refreshed_at.isoformat() if b.summary_refreshed_at else None
        ),
        "notes": b.notes,
        "scope": effective_scope,
        "totals": _finalise_totals(budget_totals),
    }
    return {"budget": header, "groups": out_groups}


def _grid_line_node(
    line: BudgetLine,
    cost_codes_by_id: dict,
    include_sensitive: bool,
    allocations: dict,
    effective_scope: str,
) -> dict:
    cc = cost_codes_by_id.get(line.cost_code_id)
    d = {
        "id": str(line.id),
        "cost_code_id": str(line.cost_code_id),
        "cost_code": (
            {
                "id": str(cc.id),
                "code": cc.code,
                "name": cc.name,
            }
            if cc else None
        ),
        "cost_code_subcategory_id": (
            str(line.cost_code_subcategory_id)
            if line.cost_code_subcategory_id else None
        ),
        "line_description": line.line_description,
        "entity_id": str(line.entity_id),
        "original_budget": str(line.original_budget),
        "approved_changes": str(line.approved_changes),
        "current_budget": str(line.current_budget),
        "committed_value": str(line.committed_value),
        "invoiced_against_commitment": str(line.invoiced_against_commitment),
        "committed_not_invoiced": str(line.committed_not_invoiced),
        "actuals_to_date": str(line.actuals_to_date),
        "actuals_this_period": (
            str(line.actuals_this_period)
            if line.actuals_this_period is not None else None
        ),
        "forecast_to_complete": str(line.forecast_to_complete),
        "ftc_method": line.ftc_method,
        "forecast_final_cost": str(line.forecast_final_cost),
        "variance_value": str(line.variance_value),
        "variance_pct": str(line.variance_pct),
        "variance_status": line.variance_status,
        "percentage_complete": (
            str(line.percentage_complete)
            if line.percentage_complete is not None else None
        ),
        "is_contingency": bool(line.is_contingency),
        "is_locked": bool(line.is_locked),
        "requires_attention": bool(line.requires_attention),
        "display_order": line.display_order,
        "notes": line.notes,
        "updated_at": line.updated_at.isoformat() if line.updated_at else None,
    }
    # Tier-1-only allocation slice; never present on construction scope.
    if effective_scope == "full" and include_sensitive and line.id in allocations:
        d["_allocated_sale_price_provisional"] = allocations[line.id]
    return d


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
    scope = scope_svc.caller_scope(perms)
    return _serialise_budget_detail(
        b, include_sensitive=include_sensitive, db=db, scope=scope,
    )


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
    scope = scope_svc.caller_scope(perms)
    return _serialise_budget_detail(
        b, include_sensitive=include_sensitive, db=db, scope=scope,
    )


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
    scope = scope_svc.caller_scope(perms)
    return _serialise_budget_detail(
        new, include_sensitive=include_sensitive, db=db, scope=scope,
    )


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
    # B88 Pack 2 §R5 fix 4 — Tier 2 callers must not read OR write
    # out-of-scope lines. 404 mirrors the cross-tenant convention
    # (existence must not leak).
    line_for_scope = db.get(BudgetLine, line_id)
    try:
        scope_svc.assert_line_in_scope(db, perms, line_for_scope)
    except BudgetNotFoundError:
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
    # B88 Pack 2 §R5 fix 4 — scope guard (404, mirrors cross-tenant).
    try:
        scope_svc.assert_line_in_scope(db, perms, line)
    except BudgetNotFoundError:
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
    # B88 Pack 2 §R5 fix 4 — reorder requires every line id; Tier 2
    # callers cannot enumerate out-of-scope lines, so the operation
    # is restricted to full-budget access (403 with a clear message).
    if scope_svc.caller_scope(perms) != "full":
        raise HTTPException(
            403, "Full-budget access required to reorder budget lines",
        )
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
    scope = scope_svc.caller_scope(perms)
    return _serialise_budget_detail(
        b, include_sensitive=include_sensitive, db=db, scope=scope,
    )



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
    # B88 Pack 2 §R5 fix 4 — scope guard.
    try:
        scope_svc.assert_line_in_scope(db, perms, line)
    except BudgetNotFoundError:
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
    # B88 Pack 2 §R5 fix 4 — scope guard on out-of-scope line.
    _line = db.get(BudgetLine, line_id)
    if _line is None:
        raise HTTPException(404, "Budget line not found")
    try:
        scope_svc.assert_line_in_scope(db, perms, _line)
    except BudgetNotFoundError:
        raise HTTPException(404, "Budget line not found")
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
    # B88 Pack 2 §R5 fix 4 — scope guard via parent line.
    _line = db.get(BudgetLine, line_id)
    if _line is not None:
        try:
            scope_svc.assert_line_in_scope(db, perms, _line)
        except BudgetNotFoundError:
            raise HTTPException(404, "Budget line item not found")
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
    # B88 Pack 2 §R5 fix 4 — scope guard via parent line.
    if line is not None:
        try:
            scope_svc.assert_line_in_scope(db, perms, line)
        except BudgetNotFoundError:
            raise HTTPException(404, "Budget line item not found")
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
