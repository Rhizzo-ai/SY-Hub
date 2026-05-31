"""Payment notices service — Chat 35 §R3.2 (Prompt 2.8b).

Two notice types:
  - `Payment`  — auto-created at certification (snapshot of certified
                 figures). Created via `create_payment_notice_internal`
                 from the valuations service.
  - `PayLess`  — manual JCT pay-less notice issued against a
                 CERTIFIED valuation (withhold notice).

Reference format: `PN-NNNN` per valuation (sequence-per-valuation, not
per-tenant; mirrors the variation-per-subcontract numbering pattern).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.permissions import UserPermissions
from app.models.rbac import UserRole, user_role_projects
from app.models.sc_valuations import (
    PaymentNotice, NOTICE_TYPES, SubcontractValuation,
)
from app.models.subcontracts import Subcontract
from app.models.user import User
from app.services.audit import field_diff, record_audit


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PaymentNoticeNotFoundError(Exception):
    """Raised when a payment notice cannot be found OR is out-of-tenant."""


class PaymentNoticeStateError(Exception):
    """Raised on business rule violations (e.g. PayLess on non-Certified)."""


# ---------------------------------------------------------------------------
# Audit snapshot
# ---------------------------------------------------------------------------

_AUDIT_COLS: tuple[str, ...] = (
    "subcontract_valuation_id", "reference", "notice_type",
    "gross_certified", "retention", "cis_deducted", "net_due",
    "due_date", "notes",
)


def _snapshot(n: PaymentNotice) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in _AUDIT_COLS:
        val = getattr(n, col)
        if isinstance(val, Decimal):
            val = str(val)
        elif isinstance(val, (date, datetime)):
            val = val.isoformat()
        elif isinstance(val, uuid.UUID):
            val = str(val)
        out[col] = val
    return out


# ---------------------------------------------------------------------------
# Tenant / project visibility
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Numbering
# ---------------------------------------------------------------------------

def _next_notice_reference(
    db: Session, valuation_id: uuid.UUID,
) -> str:
    count = db.scalar(
        select(func.count(PaymentNotice.id)).where(
            PaymentNotice.subcontract_valuation_id == valuation_id,
        )
    ) or 0
    return f"PN-{count + 1:04d}"


# ---------------------------------------------------------------------------
# Internal — called from valuations.certify_valuation
# ---------------------------------------------------------------------------

def create_payment_notice_internal(
    db: Session, *, valuation: SubcontractValuation,
    user: User, request: Optional[Request] = None,
) -> PaymentNotice:
    """Auto-create the Payment notice snapshot at certification time."""
    reference = _next_notice_reference(db, valuation.id)
    n = PaymentNotice(
        tenant_id=valuation.tenant_id,
        subcontract_valuation_id=valuation.id,
        reference=reference,
        notice_type="Payment",
        gross_certified=valuation.gross_this_cert,
        retention=valuation.retention_this_cert or Decimal("0"),
        cis_deducted=valuation.cis_deduction_this_cert or Decimal("0"),
        net_due=valuation.net_payable_this_cert or Decimal("0"),
        issued_by=user.id,
    )
    db.add(n)
    db.flush()

    sc = db.get(Subcontract, valuation.subcontract_id)
    record_audit(
        db, action="Create", resource_type="payment_notices",
        resource_id=n.id, actor_user_id=user.id,
        project_id=sc.project_id if sc else None,
        field_changes=field_diff({}, _snapshot(n)),
        metadata={
            "reference": n.reference,
            "notice_type": n.notice_type,
            "valuation_reference": valuation.reference,
        },
        request=request,
    )
    return n


# ---------------------------------------------------------------------------
# Manual PayLess notice
# ---------------------------------------------------------------------------

def create_payless_notice(
    db: Session,
    *,
    valuation_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    withhold_amount: Any,
    reason: str,
    due_date: Optional[date] = None,
    request: Optional[Request] = None,
) -> PaymentNotice:
    """Issue a PayLess notice against a Certified valuation."""
    from decimal import InvalidOperation

    if not reason or not reason.strip():
        raise ValueError("PayLess notice requires a reason")
    try:
        amt = Decimal(str(withhold_amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"withhold_amount not numeric: {e}") from e
    if amt < 0:
        raise ValueError("withhold_amount must be ≥ 0")

    v = db.get(SubcontractValuation, valuation_id)
    if v is None:
        raise PaymentNoticeNotFoundError("Valuation not found")
    sc = db.get(Subcontract, v.subcontract_id)
    if sc is None:
        raise PaymentNoticeNotFoundError("Subcontract not found")
    if sc.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise PaymentNoticeNotFoundError("Valuation not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and sc.project_id not in allowed:
            raise PaymentNoticeNotFoundError("Valuation not found")

    if v.status != "Certified":
        raise PaymentNoticeStateError(
            "PayLess notices can only be issued against a Certified "
            f"valuation (current status: {v.status})"
        )

    net_payable = v.net_payable_this_cert or Decimal("0")
    new_net = (net_payable - amt).quantize(Decimal("0.01"))

    reference = _next_notice_reference(db, v.id)
    n = PaymentNotice(
        tenant_id=v.tenant_id,
        subcontract_valuation_id=v.id,
        reference=reference,
        notice_type="PayLess",
        gross_certified=v.gross_this_cert,
        retention=v.retention_this_cert or Decimal("0"),
        cis_deducted=v.cis_deduction_this_cert or Decimal("0"),
        net_due=new_net,
        due_date=due_date,
        notes=reason.strip(),
        issued_by=user.id,
    )
    db.add(n)
    db.flush()

    record_audit(
        db, action="Create", resource_type="payment_notices",
        resource_id=n.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=field_diff({}, _snapshot(n)),
        metadata={
            "reference": n.reference,
            "notice_type": "PayLess",
            "valuation_reference": v.reference,
            "withhold_amount": str(amt),
            "reason": reason.strip(),
        },
        request=request,
    )
    return n


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _scope_for_notice(
    db: Session, n: PaymentNotice, user: User, perms: UserPermissions,
) -> None:
    if n.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise PaymentNoticeNotFoundError("Payment notice not found")
    v = db.get(SubcontractValuation, n.subcontract_valuation_id)
    if v is None:
        raise PaymentNoticeNotFoundError("Payment notice not found")
    sc = db.get(Subcontract, v.subcontract_id)
    if sc is None:
        raise PaymentNoticeNotFoundError("Payment notice not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and sc.project_id not in allowed:
            raise PaymentNoticeNotFoundError("Payment notice not found")


def get_payment_notice(
    db: Session, notice_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
) -> PaymentNotice:
    n = db.get(PaymentNotice, notice_id)
    if n is None:
        raise PaymentNoticeNotFoundError("Payment notice not found")
    _scope_for_notice(db, n, user, perms)
    return n


def list_payment_notices(
    db: Session,
    *, user: User, perms: UserPermissions,
    subcontract_valuation_id: Optional[uuid.UUID] = None,
    limit: int = 50, offset: int = 0,
) -> list[PaymentNotice]:
    q = select(PaymentNotice).where(PaymentNotice.tenant_id == user.tenant_id)
    if subcontract_valuation_id is not None:
        q = q.where(
            PaymentNotice.subcontract_valuation_id == subcontract_valuation_id,
        )
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None:
            if not allowed:
                return []
            q = q.join(
                SubcontractValuation,
                PaymentNotice.subcontract_valuation_id == SubcontractValuation.id,
            ).join(
                Subcontract,
                SubcontractValuation.subcontract_id == Subcontract.id,
            ).where(Subcontract.project_id.in_(allowed))
    q = q.order_by(PaymentNotice.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(q).all())


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def serialise(n: PaymentNotice) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "tenant_id": str(n.tenant_id),
        "subcontract_valuation_id": str(n.subcontract_valuation_id),
        "reference": n.reference,
        "notice_type": n.notice_type,
        "gross_certified": str(n.gross_certified),
        "retention": str(n.retention),
        "cis_deducted": str(n.cis_deducted),
        "net_due": str(n.net_due),
        "due_date": n.due_date.isoformat() if n.due_date else None,
        "notes": n.notes,
        "issued_at": n.issued_at.isoformat() if n.issued_at else None,
        "issued_by": str(n.issued_by) if n.issued_by else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
