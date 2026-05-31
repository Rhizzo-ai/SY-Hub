"""Budget Change Requests (BCRs) service — Chat 33 §R3 (Prompt 2.6).

Workflow that writes `budget_lines.approved_changes` while reusing the
existing `services/budgets.py::_recompute_line` + `recompute_summary`
math. Three live BCR types: Transfer, ContingencyDrawdown, Adjustment.

State machine:
  Draft → Submitted → Approved → Applied   (happy path)
  Draft|Submitted → Withdrawn               (terminal)
  Submitted → Rejected                      (terminal)
  Applied / Rejected / Withdrawn            (terminal — no further moves)

Audit pattern: this service writes audits IN-SERVICE via
`services.audit.record_audit`, mirroring the newer Track-2 pattern
(suppliers / CIS / PO / PO approvals / supplier_documents). The legacy
budgets service audits at the ROUTER layer; that divergence is noted
here. New BCR code follows the newer pattern for cohesion with the
2.5+ Track-2 code base.

Self-approval (LD2 — reuses 2.4C):
  approve_bcr() blocks when `bcr.created_by == user.id` AND
  `gross_movement >= get_budget_self_approval_threshold(db)`.
  GROSS movement = sum(abs(delta)) over the BCR's detail lines —
  net_impact is stored for reporting only and does NOT drive the guard.
  NULL-creator fail-open. Super-admin NOT exempt.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth.permissions import UserPermissions
from app.models.budget_changes import (
    BudgetChange, BudgetChangeLine,
    BUDGET_CHANGE_STATUSES, BUDGET_CHANGE_TYPES, TERMINAL_BCR_STATUSES,
)
from app.models.budgets import Budget, BudgetLine
from app.models.user import User
from app.services import budgets as budgets_svc
from app.services.audit import field_diff, record_audit
from app.services.budget_errors import (
    BudgetNotFoundError, BudgetSelfApprovalError, BudgetStateError,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

_ALLOWED_PARENT_STATUSES = frozenset({"Active", "Locked"})


def _coerce_decimal(v: Any, *, field: str) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"{field} not numeric: {e}") from e


def _quantize(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"))


def _next_reference(db: Session, budget_id: uuid.UUID) -> str:
    """Generate the next BCR reference (BCR-0001, BCR-0002, …) for this
    budget. Race-safe under the parent budget row lock held by the caller.
    """
    count = db.scalar(
        select(func.count(BudgetChange.id)).where(
            BudgetChange.budget_id == budget_id
        )
    ) or 0
    return f"BCR-{count + 1:04d}"


def _load_bcr_for_read(
    db: Session, bcr_id: uuid.UUID, user: User, perms: UserPermissions,
) -> BudgetChange:
    bcr = db.scalar(
        select(BudgetChange).where(BudgetChange.id == bcr_id).options(
            selectinload(BudgetChange.lines),
        )
    )
    if bcr is None:
        raise BudgetNotFoundError("Budget change not found")
    # Tenant + project scope via parent budget.
    budgets_svc._load_budget_for_read(db, bcr.budget_id, user, perms)
    return bcr


def _load_bcr_for_write(
    db: Session, bcr_id: uuid.UUID, user: User, perms: UserPermissions,
    *, lock_for_update: bool = True,
) -> tuple[BudgetChange, Budget]:
    """Load BCR + parent budget, both row-locked on the parent.

    Returns (bcr, parent_budget).
    """
    bcr = db.get(BudgetChange, bcr_id)
    if bcr is None:
        raise BudgetNotFoundError("Budget change not found")
    parent = budgets_svc._load_budget_for_write(
        db, bcr.budget_id, user, perms,
        lock_for_update=lock_for_update,
    )
    # Re-fetch the BCR with FOR UPDATE so concurrent transitions race-safe.
    if lock_for_update:
        bcr = db.scalar(
            select(BudgetChange).where(BudgetChange.id == bcr_id)
            .with_for_update().options(selectinload(BudgetChange.lines))
        )
        if bcr is None:
            raise BudgetNotFoundError("Budget change not found")
    return bcr, parent


def _validate_type(t: str) -> str:
    if t not in BUDGET_CHANGE_TYPES:
        raise ValueError(
            f"change_type must be one of {BUDGET_CHANGE_TYPES}; got {t!r}"
        )
    return t


def _validate_lines_input(
    lines: Iterable[dict],
) -> list[tuple[uuid.UUID, Decimal]]:
    """Coerce + validate the (budget_line_id, delta) payload."""
    out: list[tuple[uuid.UUID, Decimal]] = []
    for i, ln in enumerate(lines or []):
        bl_id = ln.get("budget_line_id")
        if bl_id is None:
            raise ValueError(f"lines[{i}].budget_line_id is required")
        if not isinstance(bl_id, uuid.UUID):
            try:
                bl_id = uuid.UUID(str(bl_id))
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"lines[{i}].budget_line_id is not a UUID: {e}"
                ) from e
        if "delta" not in ln:
            raise ValueError(f"lines[{i}].delta is required")
        delta = _coerce_decimal(ln["delta"], field=f"lines[{i}].delta")
        out.append((bl_id, _quantize(delta)))
    if not out:
        raise ValueError("lines is required and must be non-empty")
    return out


def _enforce_type_invariants(
    db: Session,
    *,
    change_type: str,
    parent: Budget,
    lines_input: list[tuple[uuid.UUID, Decimal]],
) -> None:
    """Validate Transfer / ContingencyDrawdown / Adjustment shape.

    Every referenced line must belong to `parent` budget. Type-specific
    invariants per Build Pack §R3.1.
    """
    line_ids = [lid for lid, _ in lines_input]
    rows = db.scalars(
        select(BudgetLine).where(BudgetLine.id.in_(line_ids))
    ).all()
    by_id = {ln.id: ln for ln in rows}
    if len(by_id) != len(set(line_ids)):
        raise ValueError("One or more budget_line_id values are unknown")
    for lid, _ in lines_input:
        ln = by_id.get(lid)
        if ln is None or ln.budget_id != parent.id:
            raise ValueError(
                f"budget_line {lid} does not belong to budget {parent.id}"
            )

    deltas = [d for _, d in lines_input]
    net = sum(deltas, Decimal("0"))

    if change_type == "Transfer":
        if len(lines_input) < 2:
            raise ValueError("Transfer requires at least 2 lines")
        if net != Decimal("0"):
            raise ValueError(
                f"Transfer deltas must sum to 0; got {net}"
            )
    elif change_type == "ContingencyDrawdown":
        if len(lines_input) < 2:
            raise ValueError("ContingencyDrawdown requires at least 2 lines")
        if net != Decimal("0"):
            raise ValueError(
                f"ContingencyDrawdown deltas must sum to 0; got {net}"
            )
        # Every NEGATIVE-delta source line must be a contingency line.
        for lid, delta in lines_input:
            if delta < 0 and not bool(by_id[lid].is_contingency):
                raise ValueError(
                    f"ContingencyDrawdown source line {lid} is not flagged "
                    f"is_contingency=true"
                )
    elif change_type == "Adjustment":
        if net == Decimal("0"):
            raise ValueError(
                "Adjustment must have non-zero net delta; use Transfer "
                "for net-zero movements"
            )
    # Advisory create-time negative-budget check (apply-time guard is
    # authoritative — other BCRs may apply in between).
    for lid, delta in lines_input:
        ln = by_id[lid]
        projected = Decimal(ln.current_budget or 0) + delta
        if projected < 0:
            raise ValueError(
                f"budget_line {lid} would have negative current_budget "
                f"({projected}) after this BCR (advisory; apply-time "
                f"guard is authoritative)"
            )


# ----------------------------------------------------------------------
# Serialiser
# ----------------------------------------------------------------------

def serialise(bcr: BudgetChange) -> dict[str, Any]:
    """Project a BCR + its detail lines to a JSON-safe dict."""
    return {
        "id": str(bcr.id),
        "tenant_id": str(bcr.tenant_id),
        "budget_id": str(bcr.budget_id),
        "reference": bcr.reference,
        "change_type": bcr.change_type,
        "status": bcr.status,
        "title": bcr.title,
        "reason": bcr.reason,
        "net_impact": str(bcr.net_impact),
        "source_variation_id": (
            str(bcr.source_variation_id) if bcr.source_variation_id else None
        ),
        "submitted_at": bcr.submitted_at.isoformat() if bcr.submitted_at else None,
        "submitted_by": str(bcr.submitted_by) if bcr.submitted_by else None,
        "approved_at": bcr.approved_at.isoformat() if bcr.approved_at else None,
        "approved_by": str(bcr.approved_by) if bcr.approved_by else None,
        "applied_at": bcr.applied_at.isoformat() if bcr.applied_at else None,
        "applied_by": str(bcr.applied_by) if bcr.applied_by else None,
        "rejected_at": bcr.rejected_at.isoformat() if bcr.rejected_at else None,
        "rejected_by": str(bcr.rejected_by) if bcr.rejected_by else None,
        "rejection_reason": bcr.rejection_reason,
        "created_at": bcr.created_at.isoformat() if bcr.created_at else None,
        "created_by": str(bcr.created_by) if bcr.created_by else None,
        "updated_at": bcr.updated_at.isoformat() if bcr.updated_at else None,
        "lines": [
            {
                "id": str(ln.id),
                "budget_line_id": str(ln.budget_line_id),
                "delta": str(ln.delta),
            }
            for ln in (bcr.lines or [])
        ],
    }


# ----------------------------------------------------------------------
# Create + update
# ----------------------------------------------------------------------

def create_bcr(
    db: Session,
    *,
    budget_id: uuid.UUID,
    change_type: str,
    title: str,
    reason: Optional[str],
    lines: Iterable[dict],
    user: User,
    perms: UserPermissions,
    source_variation_id: Optional[uuid.UUID] = None,
    request: Optional[Request] = None,
) -> BudgetChange:
    """Create a new BCR in Draft state. Audited Create."""
    change_type = _validate_type(change_type)
    if not title or not title.strip():
        raise ValueError("title is required")
    title = title.strip()

    parent = budgets_svc._load_budget_for_write(
        db, budget_id, user, perms, lock_for_update=True,
    )
    if parent.status not in _ALLOWED_PARENT_STATUSES:
        raise BudgetStateError(
            f"Cannot create BCR on a {parent.status} budget; "
            f"only Active or Locked budgets accept BCRs"
        )

    lines_input = _validate_lines_input(lines)
    _enforce_type_invariants(
        db, change_type=change_type, parent=parent, lines_input=lines_input,
    )

    net = sum((d for _, d in lines_input), Decimal("0"))
    reference = _next_reference(db, budget_id)

    bcr = BudgetChange(
        tenant_id=user.tenant_id,
        budget_id=budget_id,
        reference=reference,
        change_type=change_type,
        status="Draft",
        title=title,
        reason=(reason.strip() if isinstance(reason, str) and reason.strip()
                else None),
        net_impact=_quantize(net),
        source_variation_id=source_variation_id,
        created_by=user.id,
    )
    db.add(bcr)
    db.flush()

    for bl_id, delta in lines_input:
        db.add(BudgetChangeLine(
            tenant_id=user.tenant_id,
            budget_change_id=bcr.id,
            budget_line_id=bl_id,
            delta=delta,
        ))
    db.flush()
    db.refresh(bcr, attribute_names=["lines"])

    record_audit(
        db, action="Create", resource_type="budget_changes",
        resource_id=bcr.id, actor_user_id=user.id,
        project_id=parent.project_id,
        field_changes=field_diff({}, {
            "reference": bcr.reference,
            "change_type": bcr.change_type,
            "status": bcr.status,
            "title": bcr.title,
            "net_impact": str(bcr.net_impact),
            "lines": [
                {"budget_line_id": str(lid), "delta": str(d)}
                for lid, d in lines_input
            ],
        }),
        metadata={
            "kind": "bcr_create",
            "budget_id": str(budget_id),
            "reference": bcr.reference,
        },
        request=request,
    )
    return bcr


def update_bcr(
    db: Session,
    *,
    bcr_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    title: Optional[str] = None,
    reason: Optional[str] = None,
    lines: Optional[Iterable[dict]] = None,
    request: Optional[Request] = None,
) -> BudgetChange:
    """Update a Draft BCR. Title / reason / line set may change. Non-Draft
    BCRs reject with BudgetStateError.
    """
    bcr, parent = _load_bcr_for_write(db, bcr_id, user, perms)
    if bcr.status != "Draft":
        raise BudgetStateError(
            f"Cannot edit BCR in status {bcr.status}; only Draft is editable"
        )

    before = {
        "title": bcr.title,
        "reason": bcr.reason,
        "net_impact": str(bcr.net_impact),
        "lines": [
            {"budget_line_id": str(ln.budget_line_id), "delta": str(ln.delta)}
            for ln in bcr.lines
        ],
    }

    if title is not None:
        title = title.strip()
        if not title:
            raise ValueError("title cannot be empty")
        bcr.title = title

    if reason is not None:
        bcr.reason = reason.strip() if reason.strip() else None

    if lines is not None:
        lines_input = _validate_lines_input(lines)
        _enforce_type_invariants(
            db, change_type=bcr.change_type, parent=parent,
            lines_input=lines_input,
        )
        # Replace lines wholesale (Draft only).
        for ln in list(bcr.lines):
            db.delete(ln)
        db.flush()
        for bl_id, delta in lines_input:
            db.add(BudgetChangeLine(
                tenant_id=user.tenant_id,
                budget_change_id=bcr.id,
                budget_line_id=bl_id,
                delta=delta,
            ))
        bcr.net_impact = _quantize(
            sum((d for _, d in lines_input), Decimal("0"))
        )

    bcr.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(bcr, attribute_names=["lines"])

    after = {
        "title": bcr.title,
        "reason": bcr.reason,
        "net_impact": str(bcr.net_impact),
        "lines": [
            {"budget_line_id": str(ln.budget_line_id), "delta": str(ln.delta)}
            for ln in bcr.lines
        ],
    }
    changes = field_diff(before, after)
    if changes:
        record_audit(
            db, action="Update", resource_type="budget_changes",
            resource_id=bcr.id, actor_user_id=user.id,
            project_id=parent.project_id,
            field_changes=changes,
            metadata={
                "kind": "bcr_update",
                "reference": bcr.reference,
            },
            request=request,
        )
    return bcr


# ----------------------------------------------------------------------
# Workflow transitions
# ----------------------------------------------------------------------

def _stamp_transition(
    db: Session, *, bcr: BudgetChange, parent: Budget, user: User,
    new_status: str, action: str, request: Optional[Request],
    extra_metadata: Optional[dict] = None,
) -> None:
    prev = bcr.status
    bcr.status = new_status
    now = datetime.now(timezone.utc)
    bcr.updated_at = now
    if new_status == "Submitted":
        bcr.submitted_at = now
        bcr.submitted_by = user.id
    elif new_status == "Approved":
        bcr.approved_at = now
        bcr.approved_by = user.id
    elif new_status == "Applied":
        bcr.applied_at = now
        bcr.applied_by = user.id
    elif new_status == "Rejected":
        bcr.rejected_at = now
        bcr.rejected_by = user.id
    # Withdrawn has no dedicated stamp columns — captured via audit.
    meta = {
        "kind": "bcr_transition",
        "reference": bcr.reference,
        "previous_status": prev,
        "new_status": new_status,
    }
    if extra_metadata:
        meta.update(extra_metadata)
    record_audit(
        db, action=action, resource_type="budget_changes",
        resource_id=bcr.id, actor_user_id=user.id,
        project_id=parent.project_id,
        field_changes=[{"field": "status", "old": prev, "new": new_status}],
        metadata=meta,
        request=request,
    )


def submit_bcr(
    db: Session, *, bcr_id: uuid.UUID, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> BudgetChange:
    bcr, parent = _load_bcr_for_write(db, bcr_id, user, perms)
    if bcr.status != "Draft":
        raise BudgetStateError(
            f"Cannot submit BCR in status {bcr.status}; only Draft is submittable"
        )
    _stamp_transition(
        db, bcr=bcr, parent=parent, user=user,
        new_status="Submitted", action="Submit", request=request,
    )
    return bcr


def approve_bcr(
    db: Session, *, bcr_id: uuid.UUID, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> BudgetChange:
    """Submitted → Approved with LD2 self-approval guard (gross movement)."""
    from app.services.system_config import get_budget_self_approval_threshold

    bcr, parent = _load_bcr_for_write(db, bcr_id, user, perms)
    if bcr.status != "Submitted":
        raise BudgetStateError(
            f"Cannot approve BCR in status {bcr.status}; only Submitted is approvable"
        )

    # LD2 self-approval guard — GROSS movement basis.
    # Fail-open if created_by is NULL (legacy/system-seeded BCR).
    if bcr.created_by is not None and bcr.created_by == user.id:
        threshold = get_budget_self_approval_threshold(db=db)
        gross = Decimal("0")
        for ln in bcr.lines:
            gross += abs(Decimal(ln.delta or 0))
        if gross >= threshold:
            raise BudgetSelfApprovalError(
                f"BCR creator cannot self-approve at or above £{threshold} "
                f"gross movement (BCR gross £{gross}); a different user "
                f"must approve."
            )

    _stamp_transition(
        db, bcr=bcr, parent=parent, user=user,
        new_status="Approved", action="Approve", request=request,
    )
    return bcr


def reject_bcr(
    db: Session, *, bcr_id: uuid.UUID, user: User, perms: UserPermissions,
    reason: str,
    request: Optional[Request] = None,
) -> BudgetChange:
    if not reason or not reason.strip():
        raise ValueError("rejection_reason is required")
    bcr, parent = _load_bcr_for_write(db, bcr_id, user, perms)
    if bcr.status != "Submitted":
        raise BudgetStateError(
            f"Cannot reject BCR in status {bcr.status}; only Submitted is rejectable"
        )
    bcr.rejection_reason = reason.strip()
    _stamp_transition(
        db, bcr=bcr, parent=parent, user=user,
        new_status="Rejected", action="Reject", request=request,
        extra_metadata={"rejection_reason": bcr.rejection_reason},
    )
    return bcr


def withdraw_bcr(
    db: Session, *, bcr_id: uuid.UUID, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> BudgetChange:
    bcr, parent = _load_bcr_for_write(db, bcr_id, user, perms)
    if bcr.status not in ("Draft", "Submitted"):
        raise BudgetStateError(
            f"Cannot withdraw BCR in status {bcr.status}; only Draft "
            f"or Submitted BCRs are withdrawable"
        )
    _stamp_transition(
        db, bcr=bcr, parent=parent, user=user,
        new_status="Withdrawn", action="Update", request=request,
        extra_metadata={"kind": "bcr_withdrawn", "reference": bcr.reference},
    )
    return bcr


def apply_bcr(
    db: Session, *, bcr_id: uuid.UUID, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> BudgetChange:
    """Approved → Applied. Writes budget_lines.approved_changes += delta,
    then calls the EXISTING `_recompute_line` + `recompute_summary` to
    propagate the change into header FFC / variance / total_budget.
    """
    bcr, parent = _load_bcr_for_write(db, bcr_id, user, perms)
    if bcr.status != "Approved":
        raise BudgetStateError(
            f"Cannot apply BCR in status {bcr.status}; only Approved is appliable"
        )
    # Defensive re-check parent status — may have transitioned terminal
    # while the BCR sat in Approved.
    if parent.status not in _ALLOWED_PARENT_STATUSES:
        raise BudgetStateError(
            f"Cannot apply BCR: parent budget transitioned to "
            f"{parent.status}; only Active or Locked budgets accept BCR apply"
        )

    # Fresh read of each referenced budget_line under the write lock —
    # do NOT trust values cached at create time (another BCR may have
    # applied in between).
    line_ids = [ln.budget_line_id for ln in bcr.lines]
    fresh_rows = db.scalars(
        select(BudgetLine).where(BudgetLine.id.in_(line_ids))
        .with_for_update()
    ).all()
    by_id = {ln.id: ln for ln in fresh_rows}
    # Compute proposed state — defensive negative-budget guard.
    proposed = {}
    for ln in bcr.lines:
        target = by_id.get(ln.budget_line_id)
        if target is None or target.budget_id != parent.id:
            raise BudgetStateError(
                f"BCR detail line references missing or out-of-budget "
                f"line {ln.budget_line_id}"
            )
        new_approved_changes = (
            Decimal(target.approved_changes or 0) + Decimal(ln.delta or 0)
        )
        new_current_budget = (
            Decimal(target.original_budget or 0) + new_approved_changes
        )
        if new_current_budget < 0:
            raise BudgetStateError(
                f"Apply would drive budget_line {target.id} to negative "
                f"current_budget ({new_current_budget}); refusing "
                f"partial-apply"
            )
        proposed[target.id] = new_approved_changes

    # All-or-nothing apply — write deltas under the same transaction.
    for ln in bcr.lines:
        target = by_id[ln.budget_line_id]
        target.approved_changes = _quantize(proposed[target.id])
        target.updated_at = datetime.now(timezone.utc)
    db.flush()

    # Reuse the existing recompute path — DO NOT duplicate the math.
    db.refresh(parent, attribute_names=["lines"])
    budgets_svc.recompute_summary(db, parent)
    parent.summary_refreshed_at = datetime.now(timezone.utc)
    db.flush()

    _stamp_transition(
        db, bcr=bcr, parent=parent, user=user,
        new_status="Applied", action="Approve", request=request,
        extra_metadata={
            "kind": "bcr_applied",
            "reference": bcr.reference,
            "net_impact": str(bcr.net_impact),
            "lines_affected": len(bcr.lines),
        },
    )
    return bcr


# ----------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------

def get_bcr(
    db: Session, *, bcr_id: uuid.UUID, user: User, perms: UserPermissions,
) -> BudgetChange:
    return _load_bcr_for_read(db, bcr_id, user, perms)


def list_bcrs(
    db: Session, *, budget_id: uuid.UUID, user: User, perms: UserPermissions,
    status: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> list[BudgetChange]:
    # Verify parent visibility first; BudgetNotFoundError surfaces 404 at router.
    budgets_svc._load_budget_for_read(db, budget_id, user, perms)
    stmt = (
        select(BudgetChange).where(BudgetChange.budget_id == budget_id)
        .options(selectinload(BudgetChange.lines))
        .order_by(BudgetChange.created_at.desc())
        .limit(min(limit, 200)).offset(max(offset, 0))
    )
    if status is not None:
        if status not in BUDGET_CHANGE_STATUSES:
            raise ValueError(f"Unknown status {status!r}")
        stmt = stmt.where(BudgetChange.status == status)
    return db.scalars(stmt).all()


def change_log(
    db: Session, *, budget_id: uuid.UUID, user: User, perms: UserPermissions,
) -> list[BudgetChange]:
    """All BCRs for a budget, newest first. The 'change log per budget'."""
    return list_bcrs(
        db, budget_id=budget_id, user=user, perms=perms,
        limit=200, offset=0,
    )
