"""Subcontract variations service — Chat 34 §R3 (Prompt 2.8a).

State machine:
  Raised → Costed → Approved → Issued
  Raised|Costed → Rejected / Withdrawn (terminal)

On approval, `cost_treatment` determines the financial path:
  - WithinContractSum: agreed_value is added to
    `subcontract.current_contract_sum` (LD4).
  - BudgetChange: an `Adjustment`-type BCR is generated via
    `services.budget_changes.create_bcr(...)`. The resulting BCR is a
    normal Draft BCR with its own approve/apply lifecycle (LD3) —
    approving the variation does NOT auto-apply the BCR.

  SoD carry-through: because the BCR creator equals the variation
  approver, the 2.6 self-approval guard means that SAME user cannot
  approve the generated BCR above threshold — a different user must.
  This is correct and intended.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.permissions import UserPermissions
from app.models.budgets import Budget
from app.models.projects import Project
from app.models.subcontracts import (
    Subcontract, SubcontractVariation,
    COST_TREATMENTS, TERMINAL_VARIATION_STATUSES, VARIATION_STATUSES,
)
from app.models.user import User
from app.services import budget_changes as bcr_svc
from app.services import subcontracts as sc_svc
from app.services.audit import field_diff, record_audit


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

class VariationNotFoundError(Exception):
    """Raised when a variation cannot be found or is out-of-tenant."""


class VariationStateError(Exception):
    """Raised on illegal state transition or business rule violation."""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

_AUDIT_COLS: tuple[str, ...] = (
    "subcontract_id", "reference", "title", "description",
    "status", "estimated_value", "agreed_value", "cost_treatment",
    "generated_bcr_id",
    "costed_at", "costed_by",
    "approved_at", "approved_by",
    "issued_at", "issued_by",
    "rejected_at", "rejected_by", "rejection_reason",
)


def _snapshot(v: SubcontractVariation) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in _AUDIT_COLS:
        val = getattr(v, col)
        if isinstance(val, Decimal):
            val = str(val)
        out[col] = val
    return out


def _coerce_decimal(v: Any, *, field: str) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"{field} not numeric: {e}") from e


def _quantize2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"))


def _next_reference(db: Session, subcontract_id: uuid.UUID) -> str:
    """Race-safe under the parent subcontract row lock held by the caller."""
    count = db.scalar(
        select(func.count(SubcontractVariation.id)).where(
            SubcontractVariation.subcontract_id == subcontract_id
        )
    ) or 0
    return f"VAR-{count + 1:04d}"


def _load_for_read(
    db: Session, v_id: uuid.UUID, user: User, perms: UserPermissions,
) -> SubcontractVariation:
    v = db.get(SubcontractVariation, v_id)
    if v is None:
        raise VariationNotFoundError("Variation not found")
    if v.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise VariationNotFoundError("Variation not found")
    # Visibility via parent subcontract's project.
    sc_svc._load_for_read(db, v.subcontract_id, user, perms)
    return v


def _load_for_write(
    db: Session, v_id: uuid.UUID, user: User, perms: UserPermissions,
    *, lock_for_update: bool = True,
) -> tuple[SubcontractVariation, Subcontract]:
    v = db.get(SubcontractVariation, v_id)
    if v is None:
        raise VariationNotFoundError("Variation not found")
    sc = sc_svc._load_for_write(
        db, v.subcontract_id, user, perms, lock_for_update=lock_for_update,
    )
    if lock_for_update:
        v = db.scalar(
            select(SubcontractVariation)
            .where(SubcontractVariation.id == v_id)
            .with_for_update()
        )
        if v is None:
            raise VariationNotFoundError("Variation not found")
    return v, sc


def serialise(v: SubcontractVariation) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "tenant_id": str(v.tenant_id),
        "subcontract_id": str(v.subcontract_id),
        "reference": v.reference,
        "title": v.title,
        "description": v.description,
        "status": v.status,
        "estimated_value": (
            str(v.estimated_value) if v.estimated_value is not None else None
        ),
        "agreed_value": (
            str(v.agreed_value) if v.agreed_value is not None else None
        ),
        "cost_treatment": v.cost_treatment,
        "generated_bcr_id": (
            str(v.generated_bcr_id) if v.generated_bcr_id else None
        ),
        "costed_at": v.costed_at.isoformat() if v.costed_at else None,
        "costed_by": str(v.costed_by) if v.costed_by else None,
        "approved_at": v.approved_at.isoformat() if v.approved_at else None,
        "approved_by": str(v.approved_by) if v.approved_by else None,
        "issued_at": v.issued_at.isoformat() if v.issued_at else None,
        "issued_by": str(v.issued_by) if v.issued_by else None,
        "rejected_at": v.rejected_at.isoformat() if v.rejected_at else None,
        "rejected_by": str(v.rejected_by) if v.rejected_by else None,
        "rejection_reason": v.rejection_reason,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "created_by": str(v.created_by) if v.created_by else None,
        "updated_at": v.updated_at.isoformat() if v.updated_at else None,
    }


# ----------------------------------------------------------------------
# Raise (create)
# ----------------------------------------------------------------------

def raise_variation(
    db: Session,
    *,
    subcontract_id: uuid.UUID,
    title: str,
    user: User,
    perms: UserPermissions,
    description: Optional[str] = None,
    estimated_value: Any = None,
    request: Optional[Request] = None,
) -> SubcontractVariation:
    if not title or not title.strip():
        raise ValueError("title is required")
    title = title.strip()

    sc = sc_svc._load_for_write(db, subcontract_id, user, perms)
    if sc.status != "Active":
        raise VariationStateError(
            f"Variations can only be raised on an Active subcontract; "
            f"subcontract is {sc.status}"
        )

    est_val: Optional[Decimal] = None
    if estimated_value is not None:
        est_val = _quantize2(
            _coerce_decimal(estimated_value, field="estimated_value")
        )

    reference = _next_reference(db, subcontract_id)

    v = SubcontractVariation(
        tenant_id=user.tenant_id,
        subcontract_id=subcontract_id,
        reference=reference,
        title=title,
        description=(
            description.strip()
            if isinstance(description, str) and description.strip()
            else None
        ),
        status="Raised",
        estimated_value=est_val,
        created_by=user.id,
    )
    db.add(v)
    db.flush()

    record_audit(
        db, action="Create", resource_type="subcontract_variations",
        resource_id=v.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=field_diff({}, _snapshot(v)),
        metadata={
            "reference": v.reference,
            "subcontract_reference": sc.reference,
        },
        request=request,
    )
    return v


# ----------------------------------------------------------------------
# Cost (set agreed_value, Raised → Costed)
# ----------------------------------------------------------------------

def cost_variation(
    db: Session, v_id: uuid.UUID,
    *, agreed_value: Any, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> SubcontractVariation:
    v, sc = _load_for_write(db, v_id, user, perms)
    if v.status != "Raised":
        raise VariationStateError(
            f"Can only cost a Raised variation; current={v.status}"
        )

    if agreed_value is None:
        raise ValueError("agreed_value is required")
    av = _quantize2(_coerce_decimal(agreed_value, field="agreed_value"))

    before = _snapshot(v)
    v.agreed_value = av
    v.status = "Costed"
    v.costed_at = datetime.now(timezone.utc)
    v.costed_by = user.id
    db.flush()

    record_audit(
        db, action="Status_Change", resource_type="subcontract_variations",
        resource_id=v.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=field_diff(before, _snapshot(v)),
        metadata={
            "reference": v.reference,
            "subcontract_reference": sc.reference,
            "transition": "Raised→Costed",
        },
        request=request,
    )
    return v


# ----------------------------------------------------------------------
# Approve (Costed → Approved + cost-treatment side-effect)
# ----------------------------------------------------------------------

def _resolve_active_budget(db: Session, project_id: uuid.UUID) -> Budget:
    b = db.scalar(
        select(Budget).where(
            Budget.project_id == project_id,
            Budget.is_current.is_(True),
            Budget.status == "Active",
        )
    )
    if b is None:
        raise ValueError(
            "No Active current budget on the project — cannot raise a "
            "BudgetChange variation."
        )
    return b


def approve_variation(
    db: Session, v_id: uuid.UUID,
    *, cost_treatment: str, user: User, perms: UserPermissions,
    target_budget_line_id: Optional[uuid.UUID] = None,
    request: Optional[Request] = None,
) -> SubcontractVariation:
    if cost_treatment not in COST_TREATMENTS:
        raise ValueError(
            f"cost_treatment must be one of {COST_TREATMENTS}; "
            f"got {cost_treatment!r}"
        )

    v, sc = _load_for_write(db, v_id, user, perms)
    if v.status != "Costed":
        raise VariationStateError(
            f"Can only approve a Costed variation; current={v.status}"
        )
    if v.agreed_value is None:
        # Defensive — the Costed state requires agreed_value, but guard
        # explicitly in case of historical/manual edits.
        raise VariationStateError("Variation has no agreed_value")

    before = _snapshot(v)

    # Branch 1 — fold into the contract sum (LD4).
    if cost_treatment == "WithinContractSum":
        sc.current_contract_sum = _quantize2(
            (sc.current_contract_sum or Decimal("0")) + v.agreed_value
        )
        bcr_id: Optional[uuid.UUID] = None

    # Branch 2 — generate a BCR via 2.6 machinery (LD3).
    else:
        if target_budget_line_id is None:
            raise ValueError(
                "target_budget_line_id is required when "
                "cost_treatment='BudgetChange'"
            )
        budget = _resolve_active_budget(db, sc.project_id)
        bcr = bcr_svc.create_bcr(
            db,
            budget_id=budget.id,
            change_type="Adjustment",
            title=f"{sc.reference} {v.reference}: {v.title}",
            reason=(
                f"Subcontract variation {v.reference} approved on "
                f"{sc.reference} ({sc.title})."
            ),
            lines=[{
                "budget_line_id": target_budget_line_id,
                "delta": str(v.agreed_value),
            }],
            source_variation_id=v.id,
            user=user, perms=perms,
            request=request,
        )
        bcr_id = bcr.id

    v.status = "Approved"
    v.cost_treatment = cost_treatment
    v.generated_bcr_id = bcr_id
    v.approved_at = datetime.now(timezone.utc)
    v.approved_by = user.id
    db.flush()

    record_audit(
        db, action="Approve", resource_type="subcontract_variations",
        resource_id=v.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=field_diff(before, _snapshot(v)),
        metadata={
            "reference": v.reference,
            "subcontract_reference": sc.reference,
            "cost_treatment": cost_treatment,
            "generated_bcr_id": str(bcr_id) if bcr_id else None,
        },
        request=request,
    )
    return v


# ----------------------------------------------------------------------
# Issue (Approved → Issued, terminal)
# ----------------------------------------------------------------------

def issue_variation(
    db: Session, v_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> SubcontractVariation:
    v, sc = _load_for_write(db, v_id, user, perms)
    if v.status != "Approved":
        raise VariationStateError(
            f"Can only issue an Approved variation; current={v.status}"
        )
    before = _snapshot(v)
    v.status = "Issued"
    v.issued_at = datetime.now(timezone.utc)
    v.issued_by = user.id
    db.flush()
    record_audit(
        db, action="Status_Change", resource_type="subcontract_variations",
        resource_id=v.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=field_diff(before, _snapshot(v)),
        metadata={
            "reference": v.reference,
            "subcontract_reference": sc.reference,
            "transition": "Approved→Issued",
        },
        request=request,
    )
    return v


# ----------------------------------------------------------------------
# Reject / Withdraw (terminal from Raised|Costed)
# ----------------------------------------------------------------------

def reject_variation(
    db: Session, v_id: uuid.UUID,
    *, reason: str, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> SubcontractVariation:
    if not reason or not reason.strip():
        raise ValueError("rejection reason is required")
    reason = reason.strip()
    v, sc = _load_for_write(db, v_id, user, perms)
    if v.status not in ("Raised", "Costed"):
        raise VariationStateError(
            f"Can only reject a Raised or Costed variation; current={v.status}"
        )
    before = _snapshot(v)
    v.status = "Rejected"
    v.rejected_at = datetime.now(timezone.utc)
    v.rejected_by = user.id
    v.rejection_reason = reason
    db.flush()
    record_audit(
        db, action="Reject", resource_type="subcontract_variations",
        resource_id=v.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=field_diff(before, _snapshot(v)),
        metadata={
            "reference": v.reference,
            "subcontract_reference": sc.reference,
        },
        request=request,
    )
    return v


def withdraw_variation(
    db: Session, v_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> SubcontractVariation:
    v, sc = _load_for_write(db, v_id, user, perms)
    if v.status not in ("Raised", "Costed"):
        raise VariationStateError(
            f"Can only withdraw a Raised or Costed variation; "
            f"current={v.status}"
        )
    before = _snapshot(v)
    v.status = "Withdrawn"
    db.flush()
    record_audit(
        db, action="Status_Change", resource_type="subcontract_variations",
        resource_id=v.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=field_diff(before, _snapshot(v)),
        metadata={
            "reference": v.reference,
            "subcontract_reference": sc.reference,
            "transition": f"{before['status']}→Withdrawn",
        },
        request=request,
    )
    return v


# ----------------------------------------------------------------------
# Read helpers
# ----------------------------------------------------------------------

def get_variation(
    db: Session, v_id: uuid.UUID, *, user: User, perms: UserPermissions,
) -> SubcontractVariation:
    return _load_for_read(db, v_id, user, perms)


def list_variations(
    db: Session, *, user: User, perms: UserPermissions,
    subcontract_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> list[SubcontractVariation]:
    if status is not None and status not in VARIATION_STATUSES:
        raise ValueError(
            f"status must be one of {VARIATION_STATUSES}; got {status!r}"
        )
    q = select(SubcontractVariation).where(
        SubcontractVariation.tenant_id == user.tenant_id
    )
    if subcontract_id is not None:
        # Authorisation: subcontract visibility.
        sc_svc._load_for_read(db, subcontract_id, user, perms)
        q = q.where(SubcontractVariation.subcontract_id == subcontract_id)
    else:
        # Restrict to subcontracts the user can see (project scope).
        if not perms.is_super_admin:
            allowed = sc_svc._visible_project_ids(
                db, user.id, user.tenant_id,
            )
            if allowed is not None:
                if not allowed:
                    return []
                sub_ids = db.scalars(
                    select(Subcontract.id).where(
                        Subcontract.tenant_id == user.tenant_id,
                        Subcontract.project_id.in_(allowed),
                    )
                ).all()
                if not sub_ids:
                    return []
                q = q.where(SubcontractVariation.subcontract_id.in_(sub_ids))
    if status is not None:
        q = q.where(SubcontractVariation.status == status)
    q = q.order_by(
        SubcontractVariation.created_at.desc()
    ).limit(limit).offset(offset)
    return list(db.scalars(q).all())
