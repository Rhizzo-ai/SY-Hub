"""Budget lines + budget line items service — Pattern alpha tenant scoping.

Mirrors app.services.budgets._load_budget_for_write semantics. Cross-tenant
or unknown line/item -> BudgetNotFoundError -> 404.

Line edits via bulk_update_lines accept a constrained allowlist of fields.
Writes are sequenced: load + lock budget -> apply changes -> recompute_summary.
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import UserPermissions
from app.models.budgets import (
    Budget, BudgetLine, BudgetLineItem,
    LINE_FROZEN_BUDGET_STATUSES, TERMINAL_BUDGET_STATUSES, FTC_METHODS,
)
from app.models.cost_codes import CostCode, CostCodeSubcategory
from app.models.entity import Entity
from app.models.projects import Project
from app.models.user import User
from app.services.budget_errors import (
    BudgetNotFoundError, BudgetStateError, BudgetValidationError,
)
from app.services.budgets import (
    _scope_check_project, _load_budget_for_write, recompute_summary,
)

log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Chat 23 R1.2 — default 4 budget_line_items injected on every new line.
# Order is stable: Materials, Labour, Equipment, Subcontractor.
# These are description-based conventions, NOT enforced types — users
# can rename/delete/add freely after creation.
# Amounts are 0.00 so the parent line's `original_budget` is the
# accountant-set total and items are placeholders for breakdown entry.
# Also consumed by:
#   - services.budgets.create_from_appraisal (R1.2 second call-site)
#   - migrations.0027 backfill of zero-item lines (R1.3)
# ----------------------------------------------------------------------
DEFAULT_LINE_ITEMS: tuple[str, ...] = (
    "Materials",
    "Labour",
    "Equipment",
    "Subcontractor",
)


def _create_default_items(db: Session, line: BudgetLine) -> list[BudgetLineItem]:
    """Insert the 4 default items for a freshly-created line.

    Idempotent guard: if the line already has ANY items, this is a no-op
    and returns an empty list. This protects against double-creation
    when callers re-flush or test fixtures re-seed.

    Caller is responsible for `db.flush()`. We do not flush here so the
    caller can batch flushes when seeding many lines (e.g. create_from_
    appraisal). Returns the list of created BudgetLineItem objects (empty
    on the idempotent-skip path).
    """
    existing = db.scalar(
        select(BudgetLineItem)
        .where(BudgetLineItem.budget_line_id == line.id)
        .limit(1)
    )
    if existing is not None:
        return []
    items: list[BudgetLineItem] = []
    for idx, label in enumerate(DEFAULT_LINE_ITEMS):
        item = BudgetLineItem(
            budget_line_id=line.id,
            description=label,
            amount=Decimal("0"),
            display_order=idx,
        )
        db.add(item)
        items.append(item)
    return items


# Whitelist of fields callers may set via bulk_update_lines.
_LINE_EDITABLE_FIELDS = frozenset({
    "line_description",
    "original_budget",
    "approved_changes",
    "ftc_method",
    "forecast_to_complete",
    "percentage_complete",
    "linked_programme_task_id",
    "display_order",
    "notes",
    "is_locked",
    "requires_attention",
})


def _load_line_for_item_write(
    db: Session,
    line_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
) -> BudgetLine:
    """Pattern alpha-6: db.get chain + tenant scope + frozen-state guard."""
    line = db.get(BudgetLine, line_id)
    if line is None:
        raise BudgetNotFoundError("Budget line not found")
    budget = db.get(Budget, line.budget_id)
    if budget is None:
        raise BudgetNotFoundError("Budget line not found")
    project = db.get(Project, budget.project_id)
    if project is None:
        raise BudgetNotFoundError("Budget line not found")
    _scope_check_project(db, project, user, perms)
    if budget.status in LINE_FROZEN_BUDGET_STATUSES:
        raise BudgetStateError(
            f"Cannot manage items on lines of a {budget.status} budget"
        )
    return line


def _validate_cost_code_subcategory(
    db: Session, cost_code_id: uuid.UUID,
    cost_code_subcategory_id: Optional[uuid.UUID],
) -> None:
    """Subcat must belong to the cost_code if provided."""
    if cost_code_subcategory_id is None:
        return
    sub = db.get(CostCodeSubcategory, cost_code_subcategory_id)
    if sub is None or sub.cost_code_id != cost_code_id:
        raise BudgetStateError(
            "cost_code_subcategory_id does not belong to cost_code_id"
        )


def _validate_entity_in_tenant(
    db: Session, entity_id: uuid.UUID, tenant_id: uuid.UUID,
) -> None:
    e = db.get(Entity, entity_id)
    if e is None or e.tenant_id != tenant_id:
        # Cross-tenant entity lookup => 404 (do not leak).
        raise BudgetNotFoundError("Entity not found")


# ----------------------------------------------------------------------
# Line CRUD
# ----------------------------------------------------------------------
def create_line(
    db: Session,
    *,
    budget_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    cost_code_id: uuid.UUID,
    cost_code_subcategory_id: Optional[uuid.UUID],
    entity_id: uuid.UUID,
    line_description: str,
    original_budget: Decimal = Decimal("0"),
    ftc_method: str = "Budget_Remaining",
    linked_programme_task_id: Optional[uuid.UUID] = None,
    notes: Optional[str] = None,
) -> BudgetLine:
    b = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if b.status in LINE_FROZEN_BUDGET_STATUSES:
        raise BudgetStateError(f"Cannot add lines to a {b.status} budget")

    cc = db.get(CostCode, cost_code_id)
    if cc is None:
        raise BudgetStateError("cost_code_id not found")
    _validate_cost_code_subcategory(db, cost_code_id, cost_code_subcategory_id)
    _validate_entity_in_tenant(db, entity_id, user.tenant_id)
    if ftc_method not in FTC_METHODS:
        raise BudgetStateError(f"ftc_method must be one of {FTC_METHODS}")

    # Compute next display_order.
    next_order = (db.scalar(
        select(BudgetLine.display_order)
        .where(BudgetLine.budget_id == b.id)
        .order_by(BudgetLine.display_order.desc()).limit(1)
    ) or -1) + 1

    line = BudgetLine(
        budget_id=b.id,
        cost_code_id=cost_code_id,
        cost_code_subcategory_id=cost_code_subcategory_id,
        entity_id=entity_id,
        line_description=line_description[:255],
        original_budget=Decimal(original_budget),
        approved_changes=Decimal("0"),
        ftc_method=ftc_method,
        linked_programme_task_id=linked_programme_task_id,
        display_order=next_order,
        notes=notes,
    )
    db.add(line)
    db.flush()

    # R1.2: every new line ships with the 4 default items so the grid has
    # rows to render and so item-level edits never start from empty.
    _create_default_items(db, line)
    db.flush()

    # Recompute parent summary.
    db.refresh(b, attribute_names=["lines"])
    recompute_summary(db, b)
    db.flush()
    return line


# ----------------------------------------------------------------------
# B102 — Unbudgeted-Order Handling: helper used by PO + package flows
# when a caller raises an order against a cost code with no existing
# budget line. Single source of truth for the auto-line so both code
# paths produce identical rows.
# ----------------------------------------------------------------------
_UNBUDGETED_SOURCES: frozenset[str] = frozenset({"purchase_order", "package"})


def create_unbudgeted_line(
    db: Session,
    *,
    budget_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    cost_code_id: uuid.UUID,
    cost_code_subcategory_id: Optional[uuid.UUID] = None,
    entity_id: Optional[uuid.UUID] = None,
    reason: str,
    source: str,
) -> BudgetLine:
    """Create a £0 budget line flagged as unbudgeted (B102).

    Used by the PO and package services when the caller raises an order
    against a cost code that has no existing budget line. The line is
    forced Red + requires_attention=True and carries the raiser's reason
    so a director can later acknowledge it via
    `clear_unbudgeted` (Gate 4).

    Trust boundary: the caller is responsible for permission gating
    (pos.create / packages.edit upstream). This helper does NOT itself
    check a permission — creating the line is a side-effect of an
    authorised upstream write.

    Args:
      budget_id: target budget. Must be writable per the create_line
        budget-status guard (LINE_FROZEN_BUDGET_STATUSES rejected by
        create_line — i.e. Locked / Superseded / Closed). Draft/Active
        are permitted at the helper level; the upstream PO service
        layer additionally requires Active.
      cost_code_id: cost code the auto-line will hang on. Used to build
        a deterministic line_description ("Unbudgeted — {code} {name}").
      cost_code_subcategory_id: optional subcat; validated against the
        cost code by `_validate_cost_code_subcategory`.
      entity_id: if None, falls back to the budget's project
        `primary_entity_id` (mirrors how appraisal-seeded lines source
        entity). Validated to be in the user's tenant by
        `_validate_entity_in_tenant`.
      reason: mandatory, non-empty after strip (D-E2). The schema layer
        also enforces this; the service-level check is a backstop so
        callers that bypass the schema (tests, internal jobs) cannot
        sneak through a blank.
      source: must be 'purchase_order' or 'package'. Anything else is
        a programmer error and raises BudgetStateError.

    Returns:
      The persisted BudgetLine with `is_unbudgeted=True`,
      `variance_status='Red'`, `requires_attention=True`,
      `unbudgeted_reason=reason.strip()`, `unbudgeted_source=source`,
      `unbudgeted_created_by=user.id`, original_budget=0,
      `unbudgeted_cleared_at=None`.

    Lock re-entrancy: `create_line` internally re-acquires
    SELECT ... FOR UPDATE on the budget row. PostgreSQL row locks are
    re-entrant within a single transaction, so callers that have
    already locked the budget (e.g. `create_po`) are safe to invoke
    this helper inline — no deadlock, no block. Gate 5 (T7) exercises
    the live PO path end-to-end.
    """
    # D-E2 backstop — schema also enforces, but the helper is a public
    # service entrypoint and may be called outside an HTTP request.
    if not reason or not reason.strip():
        raise BudgetStateError("unbudgeted_reason is required")
    if source not in _UNBUDGETED_SOURCES:
        raise BudgetStateError(
            "unbudgeted_source must be one of 'purchase_order' or 'package'"
        )

    # Resolve entity: caller-supplied wins, else project's primary entity.
    if entity_id is None:
        # Load the budget without taking a lock here — `create_line` will
        # acquire FOR UPDATE inside the same transaction. We only need
        # the project_id to find the project's primary_entity_id.
        b_for_proj = db.get(Budget, budget_id)
        if b_for_proj is None:
            raise BudgetNotFoundError("Budget not found")
        project = db.get(Project, b_for_proj.project_id)
        if project is None or project.primary_entity_id is None:
            raise BudgetStateError(
                "cannot resolve entity_id from budget's project"
            )
        entity_id = project.primary_entity_id

    # Cost-code presence drives line_description. We look up the
    # cost code here so the description can be built before delegating
    # to `create_line`. `create_line` will independently re-validate the
    # cost code via `db.get(CostCode, ...)`; the cost is one extra cache
    # hit on a small lookup table — acceptable.
    cc = db.get(CostCode, cost_code_id)
    if cc is None:
        raise BudgetStateError("cost_code_id not found")
    description_raw = f"Unbudgeted — {cc.code} {cc.name}"
    line_description = description_raw[:255]

    # Delegate base-row creation. This:
    #   - locks the budget FOR UPDATE
    #   - validates LINE_FROZEN_BUDGET_STATUSES (rejects Locked/etc.)
    #   - validates cost code + subcategory + entity-in-tenant
    #   - computes display_order
    #   - inserts the row + the 4 default items
    #   - calls recompute_summary on the parent (which sets
    #     variance_status from variance maths — see post-call override).
    line = create_line(
        db,
        budget_id=budget_id,
        user=user,
        perms=perms,
        cost_code_id=cost_code_id,
        cost_code_subcategory_id=cost_code_subcategory_id,
        entity_id=entity_id,
        line_description=line_description,
        original_budget=Decimal("0"),
        notes=None,
    )

    # Apply B102 markers AFTER create_line's internal recompute_summary
    # has run. We deliberately do NOT call recompute_summary or
    # db.refresh(line) again — that would re-derive variance_status from
    # maths (which for a £0 line would land Green) and clobber the
    # forced Red. The forced Red + requires_attention is the visual
    # signal to the operator that this is an unbudgeted line awaiting
    # director acknowledgement; its lifecycle is independent of the
    # variance scan (D-E1).
    line.is_unbudgeted = True
    line.unbudgeted_reason = reason.strip()
    line.unbudgeted_source = source
    line.unbudgeted_created_by = user.id
    line.variance_status = "Red"
    line.requires_attention = True
    db.flush()
    return line


def bulk_update_lines(
    db: Session,
    *,
    budget_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    updates: list[dict],
) -> tuple[Budget, list[dict]]:
    """Bulk update lines on a budget.

    Each update dict must contain `id` plus 1+ of _LINE_EDITABLE_FIELDS.
    Unknown keys -> BudgetStateError. Lines on other budgets -> 404.

    Returns (budget, per_line_field_changes) for the route layer to audit.
    """
    b = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if b.status in LINE_FROZEN_BUDGET_STATUSES:
        raise BudgetStateError(f"Cannot edit lines on a {b.status} budget")

    # Build a single-query lookup for performance and to keep test #91 happy.
    line_ids = [u["id"] for u in updates if "id" in u]
    lines_by_id: dict[uuid.UUID, BudgetLine] = {
        ln.id: ln for ln in db.scalars(
            select(BudgetLine).where(
                BudgetLine.budget_id == b.id,
                BudgetLine.id.in_(line_ids),
            )
        ).all()
    }

    field_changes: list[dict] = []
    for update in updates:
        if "id" not in update:
            raise BudgetStateError("each update requires an 'id' field")
        line_id = update["id"]
        line = lines_by_id.get(line_id)
        if line is None:
            raise BudgetNotFoundError(f"Budget line {line_id} not on this budget")
        per_line = {"id": str(line_id), "changes": {}}
        for k, v in update.items():
            if k == "id":
                continue
            if k not in _LINE_EDITABLE_FIELDS:
                raise BudgetStateError(f"Field '{k}' is not editable")
            if k == "ftc_method" and v not in FTC_METHODS:
                raise BudgetStateError(
                    f"ftc_method must be one of {FTC_METHODS}"
                )
            old = getattr(line, k)
            # Decimal coercion for numeric fields.
            if k in ("approved_changes", "original_budget",
                    "forecast_to_complete", "percentage_complete"
                    ) and v is not None:
                v = Decimal(v)
            if old != v:
                per_line["changes"][k] = {
                    "before": str(old) if old is not None else None,
                    "after": str(v) if v is not None else None,
                }
                setattr(line, k, v)
        if per_line["changes"]:
            field_changes.append(per_line)

    db.flush()
    db.refresh(b, attribute_names=["lines"])
    recompute_summary(db, b)
    db.flush()
    return b, field_changes


def delete_line(
    db: Session,
    *,
    budget_id: uuid.UUID,
    line_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
) -> Budget:
    b = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if b.status in LINE_FROZEN_BUDGET_STATUSES:
        raise BudgetStateError(f"Cannot delete lines on a {b.status} budget")
    line = db.get(BudgetLine, line_id)
    if line is None or line.budget_id != b.id:
        raise BudgetNotFoundError("Budget line not found")
    db.delete(line)
    db.flush()
    db.refresh(b, attribute_names=["lines"])
    recompute_summary(db, b)
    db.flush()
    return b


# ----------------------------------------------------------------------
# Bulk reorder (Prompt 2.4A.1 — precursor patch for 2.4B-i drag-reorder)
# ----------------------------------------------------------------------
def bulk_reorder_lines(
    db: Session,
    *,
    budget_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    ordered_line_ids: list[uuid.UUID],
) -> tuple[Budget, list[dict]]:
    """Atomically rewrite `display_order` on every line of a budget.

    Contract:
      - `ordered_line_ids` MUST contain every line on the budget exactly once
        (no missing, no foreign, no duplicates). A partial / duplicated /
        foreign list raises `BudgetValidationError` -> 400 at route layer.
      - Budget must be in a non-frozen status (Draft or Active). Frozen
        statuses raise `BudgetStateError` -> 409.
      - Cross-tenant or unknown budget raises `BudgetNotFoundError` -> 404.
      - All writes happen in a single transaction under a SELECT ... FOR
        UPDATE on the parent budget (via `_load_budget_for_write`), so two
        concurrent reorders serialise rather than racing.
      - Every affected line's `updated_at` is bumped to `now()` (line-level
        "version" proxy until 2.4B-i ships a true version column).

    Returns `(budget, changes)` where `changes` is a per-line list of
    `{id, before, after}` describing the position delta. Lines whose
    position is unchanged are omitted from `changes` so the audit row
    stays tight.
    """
    b = _load_budget_for_write(db, budget_id, user, perms, lock_for_update=True)
    if b.status in LINE_FROZEN_BUDGET_STATUSES:
        raise BudgetStateError(
            f"Cannot reorder lines on a {b.status} budget"
        )

    if not ordered_line_ids:
        raise BudgetValidationError("ordered_line_ids must be non-empty")
    if len(ordered_line_ids) != len(set(ordered_line_ids)):
        raise BudgetValidationError("ordered_line_ids contains duplicates")

    current_lines = db.scalars(
        select(BudgetLine).where(BudgetLine.budget_id == b.id)
    ).all()
    current_ids: set[uuid.UUID] = {ln.id for ln in current_lines}
    submitted_ids: set[uuid.UUID] = set(ordered_line_ids)

    if submitted_ids != current_ids:
        foreign = sorted(str(i) for i in (submitted_ids - current_ids))
        missing = sorted(str(i) for i in (current_ids - submitted_ids))
        parts: list[str] = [
            "ordered_line_ids must contain every line on this budget "
            "exactly once",
        ]
        if foreign:
            parts.append(f"foreign ids: {foreign}")
        if missing:
            parts.append(f"missing ids: {missing}")
        raise BudgetValidationError("; ".join(parts))

    lines_by_id: dict[uuid.UUID, BudgetLine] = {ln.id: ln for ln in current_lines}
    changes: list[dict] = []
    for new_pos, line_id in enumerate(ordered_line_ids):
        line = lines_by_id[line_id]
        before = line.display_order
        if before != new_pos:
            changes.append({
                "id": str(line_id),
                "before": before,
                "after": new_pos,
            })
        # Always set: even unchanged lines may need updated_at bumped if the
        # caller wants the line-level "version" proxy advanced. We only
        # actually touch updated_at when the order changed; unchanged
        # lines are no-ops at the SQL layer.
        line.display_order = new_pos

    # Stamp updated_at on every affected line. Done in a separate pass so
    # the timestamp is uniform across the batch (mirrors recompute_summary).
    if changes:
        from sqlalchemy.sql import func as sa_func
        for entry in changes:
            ln = lines_by_id[uuid.UUID(entry["id"])]
            ln.updated_at = sa_func.now()

    db.flush()
    db.refresh(b, attribute_names=["lines"])
    # Reorder doesn't touch budget totals, but recompute_summary stamps
    # `summary_refreshed_at` which the frontend uses as a cache-bust signal.
    recompute_summary(db, b)
    db.flush()
    return b, changes



# ----------------------------------------------------------------------
# Item CRUD
# ----------------------------------------------------------------------
def create_item(
    db: Session,
    *,
    line_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    description: str,
    amount: Decimal,
    quantity: Optional[Decimal] = None,
    unit: Optional[str] = None,
    rate: Optional[Decimal] = None,
    notes: Optional[str] = None,
) -> BudgetLineItem:
    line = _load_line_for_item_write(db, line_id, user, perms)
    next_order = (db.scalar(
        select(BudgetLineItem.display_order)
        .where(BudgetLineItem.budget_line_id == line.id)
        .order_by(BudgetLineItem.display_order.desc()).limit(1)
    ) or -1) + 1
    item = BudgetLineItem(
        budget_line_id=line.id,
        description=description[:255],
        quantity=Decimal(quantity) if quantity is not None else None,
        unit=unit[:20] if unit else None,
        rate=Decimal(rate) if rate is not None else None,
        amount=Decimal(amount),
        notes=notes,
        display_order=next_order,
    )
    db.add(item)
    db.flush()
    return item


def update_item(
    db: Session,
    *,
    line_id: uuid.UUID,
    item_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    fields: dict,
) -> tuple[BudgetLineItem, dict]:
    line = _load_line_for_item_write(db, line_id, user, perms)
    item = db.get(BudgetLineItem, item_id)
    if item is None or item.budget_line_id != line.id:
        raise BudgetNotFoundError("Budget line item not found")

    allowed = {"description", "quantity", "unit", "rate", "amount",
               "notes", "display_order"}
    changes: dict = {}
    for k, v in fields.items():
        if k not in allowed:
            raise BudgetStateError(f"Field '{k}' is not editable")
        if k in ("quantity", "rate", "amount") and v is not None:
            v = Decimal(v)
        old = getattr(item, k)
        if old != v:
            changes[k] = {
                "before": str(old) if old is not None else None,
                "after": str(v) if v is not None else None,
            }
            setattr(item, k, v)
    db.flush()
    return item, changes


def delete_item(
    db: Session,
    *,
    line_id: uuid.UUID,
    item_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
) -> None:
    line = _load_line_for_item_write(db, line_id, user, perms)
    item = db.get(BudgetLineItem, item_id)
    if item is None or item.budget_line_id != line.id:
        raise BudgetNotFoundError("Budget line item not found")
    db.delete(item)
    db.flush()


# ----------------------------------------------------------------------
# Requires-attention scan (Phase 1 spec lines 2911–2916)
# ----------------------------------------------------------------------
def scan_requires_attention(
    db: Session, *, user: User, perms: UserPermissions,
) -> dict:
    """Toggle `requires_attention` on every visible budget_line based on
    variance_status. Clauses 2 (stale actuals) and 3 (programme task
    completed but under-billed) are deferred to Prompts 2.5 / 3.2.

    For 2.4A scope:
      - flag where `variance_status == 'Red'` and not yet flagged
      - clear where `requires_attention=True` but no longer Red

    Returns {flagged, cleared, scanned}.
    """
    from app.services.budgets import _visible_project_ids

    stmt = select(BudgetLine).join(Budget, Budget.id == BudgetLine.budget_id)
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is None:
            pass
        elif not allowed:
            return {"flagged": 0, "cleared": 0, "scanned": 0}
        else:
            stmt = stmt.where(Budget.project_id.in_(allowed))

    flagged = 0
    cleared = 0
    scanned = 0
    skipped_unbudgeted = 0
    for line in db.scalars(stmt).all():
        scanned += 1
        # B102 D-E1: never let the variance scan touch the
        # variance_status / requires_attention of an unbudgeted line
        # whose director acknowledgement has not yet landed. Its
        # Red/attention state is owned by the unbudgeted sign-off
        # lifecycle, not by variance maths. Counted as `scanned` (we
        # visited it) but not `flagged`/`cleared`. After
        # acknowledgement (cleared_at set), the line rejoins normal
        # scan behaviour — see test_scan_resumes_after_acknowledgement.
        if line.is_unbudgeted and line.unbudgeted_cleared_at is None:
            skipped_unbudgeted += 1
            continue
        should_flag = (line.variance_status == "Red")
        if should_flag and not line.requires_attention:
            line.requires_attention = True
            flagged += 1
        elif not should_flag and line.requires_attention:
            line.requires_attention = False
            cleared += 1
    db.flush()
    return {
        "flagged": flagged,
        "cleared": cleared,
        "scanned": scanned,
        "skipped_unbudgeted": skipped_unbudgeted,
    }
