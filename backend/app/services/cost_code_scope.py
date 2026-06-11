"""B88 Pack 2 — Construction-scope resolution + write-guard helper.

The Tier 2 (Construction Budget) screen is **backend-enforced** —
non-`budgets.view_sensitive` callers never receive non-construction
lines, totals, or write access to out-of-scope lines / items.

Scope membership is data-driven by the
`cost_code_sections.included_in_construction_scope` flag (Build Pack
§2 / D9). Operators retoggle via `PATCH /cost-code-sections/{id}`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import UserPermissions
from app.models.budgets import BudgetLine
from app.models.cost_codes import CostCode, CostCodeSection
from app.services.budget_errors import BudgetNotFoundError


def construction_section_ids(db: Session) -> set[uuid.UUID]:
    """Return the set of section ids with construction-scope=true."""
    rows = db.scalars(
        select(CostCodeSection.id).where(
            CostCodeSection.included_in_construction_scope.is_(True),
        )
    ).all()
    return set(rows)


def construction_cost_code_ids(db: Session) -> set[uuid.UUID]:
    """Return the set of cost-code ids that sit under a
    construction-scoped section."""
    section_ids = construction_section_ids(db)
    if not section_ids:
        return set()
    rows = db.scalars(
        select(CostCode.id).where(CostCode.section_id.in_(section_ids))
    ).all()
    return set(rows)


def caller_scope(perms: UserPermissions) -> str:
    """Single source of truth for Tier 1 vs Tier 2 (Build Pack §3).

    Returns "full" for `budgets.view_sensitive` holders (or super_admin),
    "construction" otherwise.
    """
    if perms.is_super_admin or perms.has("budgets.view_sensitive"):
        return "full"
    return "construction"


def resolve_request_scope(perms: UserPermissions, requested: str | None) -> str:
    """Clamp a caller-supplied `?scope=` parameter to the caller's
    entitlement (Build Pack §4).

    - Full-scope caller passing `construction` is honoured (preview).
    - Construction-scope caller passing `full` is silently clamped to
      construction (200, never 403/422).
    - Anything else / absent → the caller's entitled scope.
    """
    entitled = caller_scope(perms)
    if requested == "construction":
        return "construction"
    if requested == "full":
        return entitled  # may be construction if not entitled
    return entitled


def assert_line_in_scope(
    db: Session, perms: UserPermissions, line: BudgetLine,
) -> None:
    """Write-guard: raise BudgetNotFoundError if `line` is out of the
    caller's scope (Build Pack §5 fix 4).

    Existence must not leak across the scope boundary — mirror the
    cross-tenant 404 convention, NOT a 403.
    """
    if caller_scope(perms) == "full":
        return
    construction_codes = construction_cost_code_ids(db)
    if line.cost_code_id not in construction_codes:
        raise BudgetNotFoundError("Budget line not found")
