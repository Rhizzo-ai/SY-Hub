"""Actuals service — Prompt 2.5A / Chat 19A.

Pattern alpha tenant scoping mirrors app.services.budgets._visible_project_ids.

Status machine (also enforced at the DB trigger level for financial fields):
    Draft -> Posted -> Paid                  (happy path)
    Draft -> Void                            (cancellation pre-post)
    Posted -> Disputed -> Posted             (un-dispute)
    Posted -> Void  (with reason)            (post-post cancellation)
    Disputed -> Void (with reason)
    Paid -> (terminal)                       (correct via credit note)
    Void -> (terminal, immutable)

Reconciliation: every state change that affects actuals_to_date emits a call
to `app.services.budgets_reconciliation.recompute_for_line(budget_line_id)`.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.permissions import UserPermissions
from app.models.actuals import (
    Actual, ActualChangeLog, ACTUAL_STATUSES, ACTUAL_SOURCE_TYPES,
    VALID_TRANSITIONS, TERMINAL_ACTUAL_STATUSES,
)
from app.models.budgets import Budget, BudgetLine, TERMINAL_BUDGET_STATUSES
from app.models.entity import Entity
from app.models.projects import Project
from app.models.rbac import UserRole, user_role_projects
from app.models.user import User
from app.services.actual_errors import (
    ActualError, ActualNotFoundError, BudgetLineLockedError,
    BudgetLineNotInProjectError, DuplicateExternalIdError,
    ImmutableFieldError, InvalidTransitionError, MissingRequiredFieldError,
)
from app.services.audit import record_audit
from app.services import budgets_reconciliation

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Tenant scoping (Pattern alpha) — mirrors budgets._visible_project_ids
# ----------------------------------------------------------------------
def _visible_project_ids(
    db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID,
) -> Optional[set[uuid.UUID]]:
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
    """Raise ActualNotFoundError if `project` is not visible to `user`.

    Cross-tenant returns 404 (no leak of existence). Mirrors budgets.
    """
    if hasattr(project, "tenant_id") and project.tenant_id != user.tenant_id:
        raise ActualNotFoundError("Actual not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and project.id not in allowed:
            raise ActualNotFoundError("Actual not found")


def _load_actual(
    db: Session, actual_id: uuid.UUID, user: User, perms: UserPermissions,
    *, lock_for_update: bool = False,
) -> Actual:
    a = db.get(Actual, actual_id)
    if a is None:
        raise ActualNotFoundError("Actual not found")
    project = db.get(Project, a.project_id)
    if project is None:
        raise ActualNotFoundError("Actual not found")
    _scope_check_project(db, project, user, perms)
    if lock_for_update:
        a = db.scalar(
            select(Actual).where(Actual.id == actual_id).with_for_update()
        )
        if a is None:
            raise ActualNotFoundError("Actual not found")
    return a


def _validate_budget_line_belongs_to_project(
    db: Session, budget_line_id: uuid.UUID, project_id: uuid.UUID,
) -> BudgetLine:
    """The budget_line MUST be on the same project as the actual. Otherwise
    we'd have an actual posted against a line that variance never reaches.
    """
    line = db.get(BudgetLine, budget_line_id)
    if line is None:
        raise BudgetLineNotInProjectError(
            f"Budget line {budget_line_id} not found",
        )
    budget = db.get(Budget, line.budget_id)
    if budget is None or budget.project_id != project_id:
        raise BudgetLineNotInProjectError(
            f"Budget line {budget_line_id} is not on project {project_id}",
        )
    # CRITICAL: Reject lines whose parent budget is in a terminal state
    # (Superseded / Archived). Spec: actuals must hit the CURRENT version.
    if budget.status in TERMINAL_BUDGET_STATUSES:
        raise BudgetLineLockedError(
            f"Budget line belongs to a {budget.status} budget; "
            "post actuals against the Current budget version instead.",
        )
    return line


# ----------------------------------------------------------------------
# Auto-calc helpers
# ----------------------------------------------------------------------

def _compute_gross(net: Decimal, vat: Decimal) -> Decimal:
    return (Decimal(net) + Decimal(vat)).quantize(Decimal("0.01"))


def _compute_retention(
    net_amount: Decimal,
    retention_rate_pct: Optional[Decimal],
    explicit_retention: Optional[Decimal],
) -> Optional[Decimal]:
    """If retention_amount supplied explicitly, use it. Otherwise compute from
    rate * net. Returns None when neither rate nor explicit value given."""
    if explicit_retention is not None:
        return Decimal(explicit_retention).quantize(Decimal("0.01"))
    if retention_rate_pct is not None and retention_rate_pct > 0:
        return (Decimal(net_amount) * Decimal(retention_rate_pct) / Decimal("100")).quantize(
            Decimal("0.01")
        )
    return None


def _compute_cis_deduction(
    is_cis_applicable: bool,
    rate_pct: Optional[Decimal],
    labour: Optional[Decimal],
) -> Optional[Decimal]:
    if not is_cis_applicable or rate_pct is None or labour is None:
        return None
    return (Decimal(labour) * Decimal(rate_pct) / Decimal("100")).quantize(Decimal("0.01"))


# ----------------------------------------------------------------------
# Change-log helper
# ----------------------------------------------------------------------

def _log_change(
    db: Session,
    *,
    actual_id: uuid.UUID,
    event_type: str,
    actor_user_id: Optional[uuid.UUID],
    payload: Optional[dict] = None,
) -> None:
    """Append an immutable row to actuals_change_log."""
    row = ActualChangeLog(
        actual_id=actual_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        event_payload=payload or {},
    )
    db.add(row)


# ----------------------------------------------------------------------
# CRUD: create / update / delete (Draft only)
# ----------------------------------------------------------------------

def create_actual(
    db: Session,
    *,
    payload,  # CreateActualRequest
    user: User,
    perms: UserPermissions,
    request=None,
    source_overrides: Optional[dict] = None,
) -> Actual:
    """Create a Draft actual. Auto-computes gross_amount, cis_deduction_amount,
    retention_amount where rules apply.

    `source_overrides` is used internally by the AI-capture promote path to
    pass through ai_capture_metadata + document_ids without re-validating.
    """
    if payload.source_type not in ACTUAL_SOURCE_TYPES:
        raise MissingRequiredFieldError(
            f"source_type must be one of {ACTUAL_SOURCE_TYPES}",
        )

    project = db.get(Project, payload.project_id)
    if project is None:
        raise ActualNotFoundError("Project not found")
    _scope_check_project(db, project, user, perms)

    _validate_budget_line_belongs_to_project(
        db, payload.budget_line_id, payload.project_id,
    )

    entity = db.get(Entity, payload.entity_id)
    if entity is None or entity.tenant_id != user.tenant_id:
        raise MissingRequiredFieldError(
            f"Entity {payload.entity_id} not found in tenant",
        )

    # Auto-compute
    gross = _compute_gross(payload.net_amount, payload.vat_amount or Decimal("0"))
    retention = _compute_retention(
        payload.net_amount,
        payload.retention_rate_pct,
        payload.retention_amount,
    )
    cis_deduction = _compute_cis_deduction(
        payload.is_cis_applicable,
        payload.cis_deduction_rate_pct,
        payload.cis_labour_amount,
    )

    if payload.currency != "GBP" and payload.exchange_rate is None:
        raise MissingRequiredFieldError(
            "exchange_rate required when currency != GBP",
        )

    overrides = source_overrides or {}
    row = Actual(
        project_id=payload.project_id,
        budget_line_id=payload.budget_line_id,
        entity_id=payload.entity_id,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        external_id=payload.external_id,
        transaction_date=payload.transaction_date,
        posting_date=payload.posting_date or date.today(),
        description=payload.description,
        net_amount=payload.net_amount,
        vat_amount=payload.vat_amount or Decimal("0"),
        gross_amount=gross,
        vat_rate_pct=payload.vat_rate_pct,
        is_vat_recoverable=payload.is_vat_recoverable,
        currency=payload.currency,
        exchange_rate=payload.exchange_rate,
        supplier_id=payload.supplier_id,
        supplier_name_snapshot=payload.supplier_name_snapshot,
        supplier_invoice_ref=payload.supplier_invoice_ref,
        is_cis_applicable=payload.is_cis_applicable,
        cis_deduction_rate_pct=payload.cis_deduction_rate_pct,
        cis_labour_amount=payload.cis_labour_amount,
        cis_materials_amount=payload.cis_materials_amount,
        cis_deduction_amount=cis_deduction,
        retention_rate_pct=payload.retention_rate_pct,
        retention_amount=retention,
        linked_commitment_id=payload.linked_commitment_id,
        related_subcontract_id=payload.related_subcontract_id,
        status="Draft",
        document_ids=overrides.get("document_ids", []),
        ai_capture_metadata=overrides.get("ai_capture_metadata"),
        created_by_user_id=user.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        msg = str(e.orig).lower()
        if "uq_actuals_external_id_source" in msg:
            raise DuplicateExternalIdError(
                f"external_id={payload.external_id!r} already exists for "
                f"source_type={payload.source_type!r}",
            ) from e
        raise

    _log_change(
        db, actual_id=row.id, event_type="Created",
        actor_user_id=user.id,
        payload={"net_amount": str(row.net_amount), "status": "Draft"},
    )

    record_audit(
        db, action="Create", resource_type="actual", resource_id=row.id,
        actor_user_id=user.id, project_id=row.project_id, entity_id=row.entity_id,
        metadata={"source_type": row.source_type, "net_amount": str(row.net_amount)},
        request=request,
    )

    db.flush()
    return row


def update_draft_actual(
    db: Session,
    *,
    actual_id: uuid.UUID,
    payload,  # UpdateDraftActualRequest
    user: User,
    perms: UserPermissions,
    request=None,
) -> Actual:
    """Edit a Draft actual. Posted+ rows must use specific endpoints."""
    a = _load_actual(db, actual_id, user, perms, lock_for_update=True)
    if a.status != "Draft":
        raise ImmutableFieldError(
            f"Actual is {a.status} — edits to a Posted+ actual must go via "
            "a credit note (see Xero_Credit_Note source_type).",
        )

    changes: list[dict] = []
    data = payload.model_dump(exclude_unset=True)

    # Resolve to compute gross/retention/cis after applying
    for field, new in data.items():
        old = getattr(a, field)
        if old == new:
            continue
        changes.append({"field": field, "old": old, "new": new})
        setattr(a, field, new)

    if "budget_line_id" in data:
        _validate_budget_line_belongs_to_project(
            db, a.budget_line_id, a.project_id,
        )

    # Recompute derived
    if "net_amount" in data or "vat_amount" in data:
        a.gross_amount = _compute_gross(a.net_amount, a.vat_amount or Decimal("0"))
    if any(f in data for f in ("net_amount", "retention_rate_pct", "retention_amount")):
        a.retention_amount = _compute_retention(
            a.net_amount, a.retention_rate_pct,
            data.get("retention_amount", a.retention_amount),
        )
    if any(f in data for f in ("is_cis_applicable", "cis_deduction_rate_pct", "cis_labour_amount")):
        a.cis_deduction_amount = _compute_cis_deduction(
            a.is_cis_applicable, a.cis_deduction_rate_pct, a.cis_labour_amount,
        )

    db.flush()

    if changes:
        _log_change(
            db, actual_id=a.id, event_type="Edited",
            actor_user_id=user.id,
            payload={"fields_changed": [c["field"] for c in changes]},
        )
        record_audit(
            db, action="Update", resource_type="actual", resource_id=a.id,
            actor_user_id=user.id, project_id=a.project_id, entity_id=a.entity_id,
            field_changes=[{"field": c["field"], "old": str(c["old"]), "new": str(c["new"])}
                           for c in changes],
            request=request,
        )

    return a


def delete_draft_actual(
    db: Session,
    *,
    actual_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    request=None,
) -> None:
    """Hard-delete a Draft actual. ChangeLog rows are also removed.

    Posted+ rows must be voided, not deleted.
    """
    a = _load_actual(db, actual_id, user, perms, lock_for_update=True)
    if a.status != "Draft":
        raise InvalidTransitionError(
            f"Cannot delete {a.status} actual — use Void instead.",
        )
    # Manually delete change_log rows first (RESTRICT FK).
    db.query(ActualChangeLog).filter(ActualChangeLog.actual_id == a.id).delete()
    record_audit(
        db, action="Delete", resource_type="actual", resource_id=a.id,
        actor_user_id=user.id, project_id=a.project_id, entity_id=a.entity_id,
        request=request,
    )
    db.delete(a)
    db.flush()


# ----------------------------------------------------------------------
# State transitions
# ----------------------------------------------------------------------

def _check_transition(current: str, target: str) -> None:
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(
            f"Invalid status transition: {current} -> {target}",
        )


def post_actual(
    db: Session, *, actual_id: uuid.UUID, user: User, perms: UserPermissions,
    request=None, notes: Optional[str] = None,
) -> Actual:
    a = _load_actual(db, actual_id, user, perms, lock_for_update=True)
    _check_transition(a.status, "Posted")
    a.status = "Posted"
    a.posted_at = datetime.now(timezone.utc)
    a.posted_by_user_id = user.id
    db.flush()
    _log_change(db, actual_id=a.id, event_type="Posted",
                actor_user_id=user.id, payload={"notes": notes})
    budgets_reconciliation.recompute_for_line(db, a.budget_line_id)
    record_audit(
        db, action="Post", resource_type="actual", resource_id=a.id,
        actor_user_id=user.id, project_id=a.project_id, entity_id=a.entity_id,
        metadata={"net_amount": str(a.net_amount)},
        request=request,
    )
    return a


def mark_paid(
    db: Session, *, actual_id: uuid.UUID, paid_date: date,
    payment_reference: str, user: User, perms: UserPermissions, request=None,
) -> Actual:
    a = _load_actual(db, actual_id, user, perms, lock_for_update=True)
    _check_transition(a.status, "Paid")
    a.status = "Paid"
    a.paid_date = paid_date
    a.payment_reference = payment_reference
    db.flush()
    _log_change(db, actual_id=a.id, event_type="Paid",
                actor_user_id=user.id,
                payload={"paid_date": str(paid_date),
                         "payment_reference": payment_reference})
    budgets_reconciliation.recompute_for_line(db, a.budget_line_id)
    record_audit(
        db, action="Mark_Paid", resource_type="actual", resource_id=a.id,
        actor_user_id=user.id, project_id=a.project_id, entity_id=a.entity_id,
        metadata={"payment_reference": payment_reference,
                  "paid_date": str(paid_date)},
        request=request,
    )
    return a


def void_actual(
    db: Session, *, actual_id: uuid.UUID, void_reason: str,
    user: User, perms: UserPermissions, request=None,
) -> Actual:
    a = _load_actual(db, actual_id, user, perms, lock_for_update=True)
    if a.status == "Void":
        raise InvalidTransitionError("Actual is already Void")
    if a.status == "Paid":
        raise InvalidTransitionError(
            "Cannot void a Paid actual — issue a credit note instead.",
        )
    a.status = "Void"
    a.voided_at = datetime.now(timezone.utc)
    a.voided_by_user_id = user.id
    a.void_reason = void_reason
    db.flush()
    _log_change(db, actual_id=a.id, event_type="Voided",
                actor_user_id=user.id, payload={"reason": void_reason})
    budgets_reconciliation.recompute_for_line(db, a.budget_line_id)
    record_audit(
        db, action="Void", resource_type="actual", resource_id=a.id,
        actor_user_id=user.id, project_id=a.project_id, entity_id=a.entity_id,
        metadata={"reason": void_reason},
        request=request,
    )
    return a


def dispute_actual(
    db: Session, *, actual_id: uuid.UUID, dispute_reason: str,
    user: User, perms: UserPermissions, request=None,
) -> Actual:
    a = _load_actual(db, actual_id, user, perms, lock_for_update=True)
    _check_transition(a.status, "Disputed")
    a.status = "Disputed"
    a.disputed_at = datetime.now(timezone.utc)
    a.disputed_by_user_id = user.id
    a.dispute_reason = dispute_reason
    db.flush()
    _log_change(db, actual_id=a.id, event_type="Disputed",
                actor_user_id=user.id, payload={"reason": dispute_reason})
    budgets_reconciliation.recompute_for_line(db, a.budget_line_id)
    record_audit(
        db, action="Dispute", resource_type="actual", resource_id=a.id,
        actor_user_id=user.id, project_id=a.project_id, entity_id=a.entity_id,
        metadata={"reason": dispute_reason},
        request=request,
    )
    return a


def undispute_actual(
    db: Session, *, actual_id: uuid.UUID, user: User, perms: UserPermissions,
    request=None, notes: Optional[str] = None,
) -> Actual:
    a = _load_actual(db, actual_id, user, perms, lock_for_update=True)
    _check_transition(a.status, "Posted")  # Disputed -> Posted
    a.status = "Posted"
    a.disputed_at = None
    a.disputed_by_user_id = None
    a.dispute_reason = None
    db.flush()
    _log_change(db, actual_id=a.id, event_type="Undisputed",
                actor_user_id=user.id, payload={"notes": notes})
    budgets_reconciliation.recompute_for_line(db, a.budget_line_id)
    record_audit(
        db, action="Undispute", resource_type="actual", resource_id=a.id,
        actor_user_id=user.id, project_id=a.project_id, entity_id=a.entity_id,
        request=request,
    )
    return a


def release_retention(
    db: Session, *, actual_id: uuid.UUID, retention_release_date: date,
    user: User, perms: UserPermissions, request=None,
) -> Actual:
    a = _load_actual(db, actual_id, user, perms, lock_for_update=True)
    if a.retention_amount is None or a.retention_amount == 0:
        raise InvalidTransitionError(
            "Actual has no retention amount to release.",
        )
    if a.retention_released:
        # Idempotent noop. Don't error, don't log a second time.
        return a
    a.retention_released = True
    a.retention_release_date = retention_release_date
    db.flush()
    _log_change(db, actual_id=a.id, event_type="Retention_Released",
                actor_user_id=user.id,
                payload={"release_date": str(retention_release_date),
                         "amount": str(a.retention_amount)})
    budgets_reconciliation.recompute_for_line(db, a.budget_line_id)
    record_audit(
        db, action="Release_Retention", resource_type="actual", resource_id=a.id,
        actor_user_id=user.id, project_id=a.project_id, entity_id=a.entity_id,
        metadata={"amount": str(a.retention_amount),
                  "release_date": str(retention_release_date)},
        request=request,
    )
    return a


# ----------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------

def list_actuals(
    db: Session, *, filters, user: User, perms: UserPermissions,
) -> tuple[list[Actual], int]:
    """Return (rows, total_count). Filters per ActualsListFilters schema."""
    q = select(Actual)

    # Project visibility scoping
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None:
            if not allowed:
                return [], 0
            q = q.where(Actual.project_id.in_(allowed))

    if filters.project_id:
        q = q.where(Actual.project_id == filters.project_id)
    if filters.budget_line_id:
        q = q.where(Actual.budget_line_id == filters.budget_line_id)
    if filters.entity_id:
        q = q.where(Actual.entity_id == filters.entity_id)
    if filters.status:
        q = q.where(Actual.status == filters.status)
    if filters.source_type:
        q = q.where(Actual.source_type == filters.source_type)
    if filters.supplier_id:
        q = q.where(Actual.supplier_id == filters.supplier_id)
    if filters.transaction_date_from:
        q = q.where(Actual.transaction_date >= filters.transaction_date_from)
    if filters.transaction_date_to:
        q = q.where(Actual.transaction_date <= filters.transaction_date_to)

    # total before pagination
    count_q = select(func.count()).select_from(q.subquery())
    total = int(db.execute(count_q).scalar() or 0)

    rows = db.scalars(
        q.order_by(Actual.transaction_date.desc(), Actual.created_at.desc())
        .offset(filters.offset).limit(filters.limit)
    ).all()
    return list(rows), total


def get_change_log(
    db: Session, *, actual_id: uuid.UUID, user: User, perms: UserPermissions,
) -> list[ActualChangeLog]:
    a = _load_actual(db, actual_id, user, perms)
    return db.scalars(
        select(ActualChangeLog)
        .where(ActualChangeLog.actual_id == a.id)
        .order_by(ActualChangeLog.occurred_at.desc())
    ).all()
