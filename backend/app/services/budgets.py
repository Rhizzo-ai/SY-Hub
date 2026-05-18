"""Budgets header service — Pattern alpha tenant scoping (Chat 16 / Prompt 2.4A).

Build Pack v3 SQL-join code is locked-superseded; we replicate the existing
_load_appraisal pattern from routers/appraisals.py verbatim:

    db.get(Budget, id) -> db.get(Project, project_id) -> hasattr defensive ->
    _visible_project_ids(user.id, user.tenant_id) filter (skip on is_super_admin).

The defensive `hasattr(project, "tenant_id")` no-op is retained for future-
proofing per alpha-2.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth.permissions import UserPermissions
from app.models.appraisals import Appraisal, AppraisalCostLine
from app.models.budgets import (
    Budget, BudgetLine, BudgetLineItem,
    BUDGET_STATUSES, FTC_METHODS, VARIANCE_STATUSES,
    TERMINAL_BUDGET_STATUSES, LINE_FROZEN_BUDGET_STATUSES,
)
from app.models.projects import Project
from app.models.rbac import UserRole, user_role_projects
from app.models.user import User
from app.services.budget_errors import (
    BudgetCreationError, BudgetNotFoundError, BudgetStateError,
)

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# B10 / Chat 23 design Q2: in-code variance thresholds. SystemConfig
# threshold columns deferred. Updated by Chat 23 Build Pack A R1.1
# from the original 5/15 bands to 0/10 — any positive variance is
# Amber; >=10% is Red.
# ----------------------------------------------------------------------
VARIANCE_AMBER_PCT = Decimal("0.000")     # > 0% over budget = amber
VARIANCE_RED_PCT = Decimal("10.000")      # >= 10% over budget = red


# ----------------------------------------------------------------------
# Tenant scoping (Pattern alpha)
# ----------------------------------------------------------------------
def _visible_project_ids(
    db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID,
) -> Optional[set[uuid.UUID]]:
    """Replica of routers/appraisals.py::_visible_project_ids.

    None  -> unrestricted (any project_scope='All' role grants this)
    set() -> no access
    set(...) -> explicit project ids visible to this user
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
                select(user_role_projects.c.project_id).where(
                    user_role_projects.c.user_role_id == ur.id
                )
            ).all()
            ids.update(r[0] for r in rows)
    if has_all:
        return None
    return ids


def _scope_check_project(
    db: Session, project: Project, user: User, perms: UserPermissions,
) -> None:
    """Raise BudgetNotFoundError if `project` is not visible to `user`.

    Mirrors the defensive `hasattr` + _visible_project_ids pattern from
    routers/appraisals.py::_load_appraisal. Cross-tenant returns 404
    (no leak of existence).
    """
    # alpha-2: dead-today defensive check; survives if projects.tenant_id is
    # added in a future migration.
    if hasattr(project, "tenant_id") and project.tenant_id != user.tenant_id:
        raise BudgetNotFoundError("Budget not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and project.id not in allowed:
            raise BudgetNotFoundError("Budget not found")


def _load_budget_for_read(
    db: Session, budget_id: uuid.UUID, user: User, perms: UserPermissions,
) -> Budget:
    """Read path: tenant-scoped + selectinload of lines & items.

    Query budget per alpha-4: 1 Budget + 1 Project + 1 visible_projects (1–N)
    + 1 selectinload(lines) + 1 selectinload(items) = up to 5 for super_admin
    or single 'All'-scope users.
    """
    b = db.scalar(
        select(Budget).where(Budget.id == budget_id).options(
            selectinload(Budget.lines).selectinload(BudgetLine.items),
        )
    )
    if b is None:
        raise BudgetNotFoundError("Budget not found")
    project = db.get(Project, b.project_id)
    if project is None:
        raise BudgetNotFoundError("Budget not found")
    _scope_check_project(db, project, user, perms)
    return b


def _load_budget_for_write(
    db: Session, budget_id: uuid.UUID, user: User, perms: UserPermissions,
    *, lock_for_update: bool = False,
) -> Budget:
    """Write path: tenant-scoped + optional row lock.

    Three-query path when locking: Budget read -> Project read -> re-fetch
    Budget with FOR UPDATE. Identity-mapped: Budget re-fetch is a row-lock
    SQL hit, not a result re-materialisation.
    """
    b = db.get(Budget, budget_id)
    if b is None:
        raise BudgetNotFoundError("Budget not found")
    project = db.get(Project, b.project_id)
    if project is None:
        raise BudgetNotFoundError("Budget not found")
    _scope_check_project(db, project, user, perms)
    if lock_for_update:
        b = db.scalar(
            select(Budget).where(Budget.id == budget_id).with_for_update()
        )
        if b is None:
            # Vanished between perm check and lock — treat as 404.
            raise BudgetNotFoundError("Budget not found")
    return b


# ----------------------------------------------------------------------
# Variance + summary recompute helpers
# ----------------------------------------------------------------------
def _classify_variance(variance_pct: Decimal) -> str:
    """Classify a variance pct into Green/Amber/Red (design Q2, Chat 23).

    Bands (Chat 23 Build Pack A R1.1):
      - variance_pct <= 0  -> Green (on or under budget)
      - variance_pct >= 10 -> Red
      - otherwise (>0, <10) -> Amber

    Lower-bound for Amber uses strict `>` so exactly 0 stays Green.
    Upper-bound for Red uses `>=` so exactly 10 is Red. This makes the
    bands unambiguous at fence-posts.
    """
    if variance_pct <= 0:
        return "Green"
    if variance_pct >= VARIANCE_RED_PCT:
        return "Red"
    if variance_pct > VARIANCE_AMBER_PCT:
        return "Amber"
    return "Green"


def _recompute_line(line: BudgetLine) -> None:
    """Recompute the cached fields on a single budget line.

    current_budget       = original_budget + approved_changes
    forecast_to_complete = method-dependent (see spec line 2861-ish)
    forecast_final_cost  = actuals_to_date + committed_not_invoiced + ftc
    variance_value       = forecast_final_cost - current_budget
    variance_pct         = variance_value / current_budget * 100
    variance_status      = _classify_variance(variance_pct)

    Actuals/commitments inputs are 0 today (no actuals service yet); the
    formulas land correctly when those land in 2.5.
    """
    orig = Decimal(line.original_budget or 0)
    chg = Decimal(line.approved_changes or 0)
    line.current_budget = orig + chg

    actuals = Decimal(line.actuals_to_date or 0)
    committed = Decimal(line.committed_not_invoiced or 0)

    method = line.ftc_method
    if method == "Manual":
        ftc = Decimal(line.forecast_to_complete or 0)
    elif method == "Budget_Remaining":
        ftc = max(Decimal("0"), line.current_budget - actuals - committed)
    elif method == "Committed_Only":
        ftc = Decimal("0")
    elif method == "Percentage_Complete":
        pct = Decimal(line.percentage_complete or 0)
        # Inverse of completion: remaining cost is (1 - pct) * current_budget,
        # minus what's already actualled/committed.
        remaining = line.current_budget * (Decimal("100") - pct) / Decimal("100")
        ftc = max(Decimal("0"), remaining - actuals - committed)
    else:
        ftc = Decimal(line.forecast_to_complete or 0)
    line.forecast_to_complete = ftc.quantize(Decimal("0.01"))

    line.forecast_final_cost = (actuals + committed + line.forecast_to_complete).quantize(
        Decimal("0.01")
    )
    line.variance_value = (line.forecast_final_cost - line.current_budget).quantize(
        Decimal("0.01")
    )
    if line.current_budget and line.current_budget != 0:
        pct = (line.variance_value / line.current_budget * Decimal("100")).quantize(
            Decimal("0.001")
        )
    else:
        pct = Decimal("0.000")
    line.variance_pct = pct
    line.variance_status = _classify_variance(pct)


def recompute_summary(db: Session, budget: Budget) -> Budget:
    """Recompute the cached aggregate fields on a budget header.

    Iterates the loaded `lines` collection. Caller is responsible for
    ensuring lines are loaded (selectinload or refresh).
    """
    total_budget = Decimal("0")
    total_actuals = Decimal("0")
    total_committed_ni = Decimal("0")
    total_ftc = Decimal("0")
    fpc = Decimal("0")
    for line in budget.lines:
        _recompute_line(line)
        total_budget += line.current_budget or 0
        total_actuals += line.actuals_to_date or 0
        total_committed_ni += line.committed_not_invoiced or 0
        total_ftc += line.forecast_to_complete or 0
        fpc += line.forecast_final_cost or 0

    budget.total_budget = total_budget.quantize(Decimal("0.01"))
    budget.total_actuals = total_actuals.quantize(Decimal("0.01"))
    budget.total_committed_not_invoiced = total_committed_ni.quantize(Decimal("0.01"))
    budget.total_forecast_to_complete = total_ftc.quantize(Decimal("0.01"))
    budget.forecast_final_cost = fpc.quantize(Decimal("0.01"))
    budget.variance_vs_budget = (fpc - total_budget).quantize(Decimal("0.01"))
    if total_budget and total_budget != 0:
        budget.variance_pct = (
            (fpc - total_budget) / total_budget * Decimal("100")
        ).quantize(Decimal("0.001"))
    else:
        budget.variance_pct = Decimal("0.000")
    budget.summary_refreshed_at = datetime.now(timezone.utc)
    return budget


# ----------------------------------------------------------------------
# Create from appraisal
# ----------------------------------------------------------------------
def create_from_appraisal(
    db: Session,
    *,
    project_id: uuid.UUID,
    source_appraisal_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
) -> Budget:
    """Create a new Draft budget seeded from an Approved appraisal's cost lines.

    Phase 1 spec lines 2711-2958 + locked decisions:
      - C1: AppraisalUnit aggregation deferred (no unit loop).
      - D1: AppraisalCostLine field mappings (amount/label) + entity_id from
        project.primary_entity_id.
      - B5 (expanded): guard cl.cost_code_id is None AND cl.amount is None;
        warn on cl.amount == 0.
      - Pattern alpha: tenant scope via project + _visible_project_ids.
      - Phase 1 spec: only Approved appraisals can seed a budget.
      - Merging: same (cost_code_id, subcategory_id, entity_id) tuples sum into
        a single budget_line.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise BudgetCreationError("Project not found")
    _scope_check_project(db, project, user, perms)

    appraisal = db.get(Appraisal, source_appraisal_id)
    if appraisal is None or appraisal.project_id != project_id:
        raise BudgetCreationError("Source appraisal not found for this project")
    # Re-scope through the same project (already checked above) — belt+braces
    # to mirror routers/appraisals.py::_load_appraisal.
    _scope_check_project(db, project, user, perms)

    if appraisal.status != "Approved":
        raise BudgetCreationError(
            f"Only Approved appraisals may seed a budget (got status={appraisal.status})"
        )

    if project.primary_entity_id is None:
        # NOT NULL in schema, but defensive.
        raise BudgetCreationError("Project has no primary_entity_id")

    cost_lines = db.scalars(
        select(AppraisalCostLine).where(
            AppraisalCostLine.appraisal_id == appraisal.id
        )
    ).all()

    if not cost_lines:
        raise BudgetCreationError(
            f"Source appraisal {appraisal.id} has no cost lines; nothing to seed"
        )

    # B5 guards (expanded per Chat 16).
    null_cost_code = [str(cl.id) for cl in cost_lines if cl.cost_code_id is None]
    if null_cost_code:
        suffix = "…" if len(null_cost_code) > 5 else ""
        raise BudgetCreationError(
            f"Cost lines missing cost_code_id: {null_cost_code[:5]}{suffix}"
        )
    null_amount = [str(cl.id) for cl in cost_lines if cl.amount is None]
    if null_amount:
        suffix = "…" if len(null_amount) > 5 else ""
        raise BudgetCreationError(
            f"Cost lines missing amount: {null_amount[:5]}{suffix}"
        )
    zero_amount = [
        str(cl.id) for cl in cost_lines
        if cl.amount is not None and Decimal(cl.amount) == 0
    ]
    if zero_amount:
        log.warning(
            "create_from_appraisal: cost lines with amount=0 (will create £0 "
            "budget_line): %s", zero_amount[:10],
        )

    # Mark any prior is_current=true budget on this project as superseded.
    # B3 partial unique index would otherwise refuse the insert. Use
    # SELECT FOR UPDATE so concurrent /from-appraisal calls serialise.
    prior = db.scalars(
        select(Budget)
        .where(Budget.project_id == project_id, Budget.is_current.is_(True))
        .with_for_update()
    ).all()
    for p in prior:
        if p.status not in TERMINAL_BUDGET_STATUSES:
            # Only Closed budgets can coexist with a new Draft (Closed is a
            # terminal record-keeping state but is_current=True is allowed).
            # Active/Locked/Draft must not coexist with a fresh seed.
            raise BudgetStateError(
                f"Project already has a non-terminal current budget "
                f"({p.status}); supersede or close it before re-seeding"
            )
        p.is_current = False

    # Determine version_number.
    max_version = db.scalar(
        select(Budget.version_number)
        .where(Budget.project_id == project_id)
        .order_by(Budget.version_number.desc())
        .limit(1)
    ) or 0

    # Header.
    budget = Budget(
        project_id=project_id,
        source_appraisal_id=appraisal.id,
        version_number=max_version + 1,
        version_label="Original" if max_version == 0 else f"v{max_version + 1}",
        is_current=True,
        status="Draft",
        created_by_user_id=user.id,
    )
    db.add(budget)
    db.flush()  # need budget.id for line FK

    # Aggregate cost_lines into budget_lines, merging on
    # (cost_code_id, subcategory_id, entity_id). D1: entity_id always =
    # project.primary_entity_id; subcategory always None today (graceful via
    # getattr).
    merge_map: dict[tuple, dict] = {}
    for cl in cost_lines:
        subcat_id = getattr(cl, "cost_code_subcategory_id", None)
        key = (cl.cost_code_id, subcat_id, project.primary_entity_id)
        if key not in merge_map:
            merge_map[key] = {
                "cost_code_id": cl.cost_code_id,
                "cost_code_subcategory_id": subcat_id,
                "entity_id": project.primary_entity_id,
                "line_description": cl.label or "(unlabelled)",
                "original_budget": Decimal("0"),
                "source_count": 0,
            }
        merge_map[key]["original_budget"] += Decimal(cl.amount or 0)
        merge_map[key]["source_count"] += 1

    # Insert lines preserving the order they were first seen (stable).
    # R1.2: every new line gets 4 default items injected post-flush so the
    # newly-created budget is grid-renderable immediately.
    from app.services.budget_lines import _create_default_items  # local to avoid import cycle
    new_lines: list[BudgetLine] = []
    for display_order, (key, vals) in enumerate(merge_map.items()):
        line = BudgetLine(
            budget_id=budget.id,
            cost_code_id=vals["cost_code_id"],
            cost_code_subcategory_id=vals["cost_code_subcategory_id"],
            entity_id=vals["entity_id"],
            line_description=vals["line_description"][:255],
            original_budget=vals["original_budget"],
            approved_changes=Decimal("0"),
            ftc_method="Budget_Remaining",
            display_order=display_order,
        )
        db.add(line)
        new_lines.append(line)
    db.flush()
    for nl in new_lines:
        _create_default_items(db, nl)
    db.flush()

    # Refresh lines for recompute (they were just added so collection is loaded).
    db.refresh(budget, attribute_names=["lines"])
    recompute_summary(db, budget)
    db.flush()
    return budget


# ----------------------------------------------------------------------
# Header updates (notes / version_label)
# ----------------------------------------------------------------------
def update_header(
    db: Session,
    *,
    budget_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    notes: Optional[str] = None,
    version_label: Optional[str] = None,
    _sentinel=object(),
) -> tuple[Budget, dict]:
    """Update notes / version_label. Returns (budget, field_changes)."""
    b = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if b.status in TERMINAL_BUDGET_STATUSES:
        raise BudgetStateError(
            f"Cannot edit header on a {b.status} budget"
        )
    changes: dict = {}
    if notes is not None and notes != b.notes:
        changes["notes"] = {"before": b.notes, "after": notes}
        b.notes = notes
    if version_label is not None and version_label != b.version_label:
        changes["version_label"] = {
            "before": b.version_label, "after": version_label,
        }
        b.version_label = version_label
    return b, changes


# ----------------------------------------------------------------------
# State transitions
# ----------------------------------------------------------------------
def activate(
    db: Session, *, budget_id: uuid.UUID, user: User, perms: UserPermissions,
) -> Budget:
    """Draft -> Active. Gated by budgets.edit per B8."""
    b = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if b.status != "Draft":
        raise BudgetStateError(f"Cannot activate from {b.status}; only Draft")
    b.status = "Active"
    return b


def lock(
    db: Session, *, budget_id: uuid.UUID, user: User, perms: UserPermissions,
) -> Budget:
    """Active -> Locked. Gated by budgets.admin."""
    b = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if b.status != "Active":
        raise BudgetStateError(f"Cannot lock from {b.status}; only Active")
    b.status = "Locked"
    b.locked_at = datetime.now(timezone.utc)
    b.locked_by_user_id = user.id
    return b


def unlock(
    db: Session, *, budget_id: uuid.UUID, user: User, perms: UserPermissions,
) -> Budget:
    """Locked -> Active. Gated by budgets.admin."""
    b = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if b.status != "Locked":
        raise BudgetStateError(f"Cannot unlock from {b.status}; only Locked")
    b.status = "Active"
    b.locked_at = None
    b.locked_by_user_id = None
    return b


def close(
    db: Session, *, budget_id: uuid.UUID, user: User, perms: UserPermissions,
) -> Budget:
    """Active or Locked -> Closed. Gated by budgets.admin."""
    b = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if b.status not in ("Active", "Locked"):
        raise BudgetStateError(
            f"Cannot close from {b.status}; only Active or Locked"
        )
    b.status = "Closed"
    b.closed_at = datetime.now(timezone.utc)
    b.closed_by_user_id = user.id
    return b


def new_version(
    db: Session,
    *, budget_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    label: Optional[str] = None,
) -> tuple[Budget, Budget]:
    """Create a new Draft budget that supersedes the current one.

    Old: status -> Superseded, is_current -> False.
    New: copies lines (and items per B11) with linked_programme_task_id
         carried over (B9). version_number = old + 1.

    Returns (old_budget, new_budget).
    """
    old = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if old.status not in ("Active", "Locked"):
        raise BudgetStateError(
            f"Cannot create new version from {old.status}; only Active or Locked"
        )
    if not old.is_current:
        raise BudgetStateError(
            "Only the current budget version can be superseded"
        )

    # Mark old as superseded.
    old.status = "Superseded"
    old.is_current = False

    # Build new draft.
    new = Budget(
        project_id=old.project_id,
        source_appraisal_id=old.source_appraisal_id,
        version_number=old.version_number + 1,
        version_label=label or f"v{old.version_number + 1}",
        is_current=True,
        status="Draft",
        notes=old.notes,
        created_by_user_id=user.id,
    )
    db.add(new)
    db.flush()

    # Copy lines + items (B11). Reset actuals/commitments and computed
    # fields — they recompute on the way out.
    old_lines = db.scalars(
        select(BudgetLine).where(BudgetLine.budget_id == old.id)
        .options(selectinload(BudgetLine.items))
        .order_by(BudgetLine.display_order)
    ).all()
    for ol in old_lines:
        nl = BudgetLine(
            budget_id=new.id,
            cost_code_id=ol.cost_code_id,
            cost_code_subcategory_id=ol.cost_code_subcategory_id,
            entity_id=ol.entity_id,
            line_description=ol.line_description,
            original_budget=ol.current_budget,  # carry the latest current as new original
            approved_changes=Decimal("0"),
            ftc_method=ol.ftc_method,
            percentage_complete=Decimal("0"),
            linked_programme_task_id=ol.linked_programme_task_id,  # B9
            display_order=ol.display_order,
            notes=ol.notes,
        )
        db.add(nl)
        db.flush()
        for oi in ol.items:
            ni = BudgetLineItem(
                budget_line_id=nl.id,
                description=oi.description,
                quantity=oi.quantity,
                unit=oi.unit,
                rate=oi.rate,
                amount=oi.amount,
                notes=oi.notes,
                display_order=oi.display_order,
            )
            db.add(ni)
    db.flush()
    db.refresh(new, attribute_names=["lines"])
    recompute_summary(db, new)
    db.flush()
    return old, new


# ----------------------------------------------------------------------
# List
# ----------------------------------------------------------------------
def list_budgets(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    project_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    is_current: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Budget]:
    """List budgets visible to this user, with optional filters.

    Tenant scoping: filter to project_ids that are visible. If a specific
    project_id is requested, validate access; otherwise return only the
    visible-projects intersection.
    """
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None:
            return []
        try:
            _scope_check_project(db, project, user, perms)
        except BudgetNotFoundError:
            return []

    stmt = select(Budget)
    if project_id is not None:
        stmt = stmt.where(Budget.project_id == project_id)
    elif not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is None:
            pass  # all
        elif not allowed:
            return []
        else:
            stmt = stmt.where(Budget.project_id.in_(allowed))
    if status is not None:
        stmt = stmt.where(Budget.status == status)
    if is_current is not None:
        stmt = stmt.where(Budget.is_current.is_(is_current))
    stmt = stmt.order_by(
        Budget.project_id, Budget.version_number.desc()
    ).limit(min(limit, 200)).offset(max(offset, 0))
    return db.scalars(stmt).all()
