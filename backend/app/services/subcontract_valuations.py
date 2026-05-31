"""Subcontract valuations service — Chat 35 §R3.1 (Prompt 2.8b).

The inbound subcontractor payment cycle (JCT-style):
  Subcontractor applies cumulative gross_applied_to_date ─ we assess ─
  certification computes retention movement + CIS (labour only) ─
  posts an actual via the EXISTING `actuals.create_actual(...)`
  service ─ creates the Payment notice.

LD1 — valuation posts an actual on certification (do NOT duplicate the
      money columns; reuse the actuals service's compute helpers).
LD2 — CIS on labour only.
LD3 — CIS rate from `supplier.current_cis_status`:
        Gross → 0%, Net → 20%, Unmatched | Unverified | NULL → 30%.
      If `subcontract.cis_applies=false`, no CIS regardless.
LD4 — cumulative model:
        gross_this_cert = gross_applied_to_date − previous_gross_certified
        retention_cumulative = gross_applied_to_date × retention_pct / 100
        retention_this_cert  = retention_cumulative − previous_retention_held
        cis_deduction_this_cert = labour_portion × cis_rate_pct / 100
        net_payable_this_cert = gross_this_cert
                                − retention_this_cert
                                − cis_deduction_this_cert
LD5 — §R0.2-confirmed net_amount basis is PRE-DEDUCTION: the posted
      actual carries net_amount = gross_this_cert and the deduction
      fields as separate columns. The cost-tracker subtracts retention
      from `actuals_to_date` itself.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth.permissions import UserPermissions
from app.models.actuals import Actual
from app.models.budgets import Budget, BudgetLine
from app.models.projects import Project
from app.models.rbac import UserRole, user_role_projects
from app.models.sc_valuations import (
    SubcontractValuation, VALUATION_STATUSES, TERMINAL_VALUATION_STATUSES,
)
from app.models.subcontracts import Subcontract
from app.models.suppliers import Supplier
from app.models.user import User
from app.services.audit import field_diff, record_audit


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ValuationNotFoundError(Exception):
    """Raised when a valuation cannot be found OR is out-of-tenant."""


class ValuationStateError(Exception):
    """Raised on illegal state transition or business rule violation."""


# ---------------------------------------------------------------------------
# CIS rate mapping (LD3)
# ---------------------------------------------------------------------------

_CIS_RATE_MAP: dict[Optional[str], Decimal] = {
    "Gross": Decimal("0"),
    "Net": Decimal("20"),
    "Unmatched": Decimal("30"),
    "Unverified": Decimal("30"),
    None: Decimal("30"),  # defensive — never-verified case
}


def cis_rate_for_status(status: Optional[str]) -> Decimal:
    """Map `suppliers.current_cis_status` to deduction rate %.

    Unknown values default to 30 (defensive — same as Unmatched).
    """
    if status in _CIS_RATE_MAP:
        return _CIS_RATE_MAP[status]
    return Decimal("30")


# ---------------------------------------------------------------------------
# Audit snapshot
# ---------------------------------------------------------------------------

_AUDIT_COLS: tuple[str, ...] = (
    "subcontract_id", "reference", "valuation_number", "status",
    "period_start", "period_end",
    "gross_applied_to_date", "gross_this_cert",
    "labour_portion", "materials_portion",
    "previous_certified_net", "retention_rate_pct",
    "retention_this_cert", "cis_rate_pct",
    "cis_deduction_this_cert", "net_payable_this_cert",
    "over_claim_flag", "over_claim_note",
    "posted_actual_id",
)


def _snapshot(v: SubcontractValuation) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in _AUDIT_COLS:
        val = getattr(v, col)
        if isinstance(val, Decimal):
            val = str(val)
        elif isinstance(val, (date, datetime)):
            val = val.isoformat()
        elif isinstance(val, uuid.UUID):
            val = str(val)
        out[col] = val
    return out


# ---------------------------------------------------------------------------
# Tenant / project scoping (Pattern α replica from subcontracts service)
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


def _scope_check_subcontract(
    db: Session, sc: Subcontract, user: User, perms: UserPermissions,
) -> None:
    if sc.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise ValuationNotFoundError("Subcontract not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and sc.project_id not in allowed:
            raise ValuationNotFoundError("Subcontract not found")


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

def _coerce_decimal(v: Any, *, field: str) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"{field} not numeric: {e}") from e


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Numbering — race-safe under subcontract row lock
# ---------------------------------------------------------------------------

def _next_valuation_number(
    db: Session, subcontract_id: uuid.UUID,
) -> int:
    """Return (max(valuation_number) + 1) within the subcontract."""
    n = db.scalar(
        select(func.coalesce(func.max(SubcontractValuation.valuation_number), 0))
        .where(SubcontractValuation.subcontract_id == subcontract_id)
    ) or 0
    return int(n) + 1


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def _load_subcontract_for_write(
    db: Session, subcontract_id: uuid.UUID,
    user: User, perms: UserPermissions,
) -> Subcontract:
    sc = db.scalar(
        select(Subcontract).where(Subcontract.id == subcontract_id)
        .with_for_update()
    )
    if sc is None:
        raise ValuationNotFoundError("Subcontract not found")
    _scope_check_subcontract(db, sc, user, perms)
    return sc


def _load_valuation_for_write(
    db: Session, val_id: uuid.UUID,
    user: User, perms: UserPermissions,
    *, lock_for_update: bool = True,
) -> SubcontractValuation:
    v = db.get(SubcontractValuation, val_id)
    if v is None:
        raise ValuationNotFoundError("Valuation not found")
    sc = db.get(Subcontract, v.subcontract_id)
    if sc is None:
        raise ValuationNotFoundError("Valuation not found")
    _scope_check_subcontract(db, sc, user, perms)
    if v.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise ValuationNotFoundError("Valuation not found")
    if lock_for_update:
        v = db.scalar(
            select(SubcontractValuation)
            .where(SubcontractValuation.id == val_id)
            .with_for_update()
        )
        if v is None:
            raise ValuationNotFoundError("Valuation not found")
    return v


def _load_valuation_for_read(
    db: Session, val_id: uuid.UUID,
    user: User, perms: UserPermissions,
) -> SubcontractValuation:
    v = db.get(SubcontractValuation, val_id)
    if v is None:
        raise ValuationNotFoundError("Valuation not found")
    sc = db.get(Subcontract, v.subcontract_id)
    if sc is None:
        raise ValuationNotFoundError("Valuation not found")
    _scope_check_subcontract(db, sc, user, perms)
    if v.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise ValuationNotFoundError("Valuation not found")
    return v


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

# Fields gated behind subcontract_valuations.view_sensitive.
SENSITIVE_FIELDS: frozenset[str] = frozenset({
    "cis_rate_pct", "cis_deduction_this_cert",
    "retention_this_cert", "net_payable_this_cert",
    "previous_certified_net",
})


def serialise(
    v: SubcontractValuation, *, include_sensitive: bool,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": str(v.id),
        "tenant_id": str(v.tenant_id),
        "subcontract_id": str(v.subcontract_id),
        "reference": v.reference,
        "valuation_number": v.valuation_number,
        "status": v.status,
        "period_start": v.period_start.isoformat() if v.period_start else None,
        "period_end": v.period_end.isoformat() if v.period_end else None,
        "gross_applied_to_date": str(v.gross_applied_to_date),
        "gross_this_cert": str(v.gross_this_cert),
        "labour_portion": str(v.labour_portion),
        "materials_portion": str(v.materials_portion),
        "retention_rate_pct": (
            str(v.retention_rate_pct) if v.retention_rate_pct is not None
            else None
        ),
        "over_claim_flag": v.over_claim_flag,
        "over_claim_note": v.over_claim_note,
        "posted_actual_id": (
            str(v.posted_actual_id) if v.posted_actual_id else None
        ),
        "submitted_at": v.submitted_at.isoformat() if v.submitted_at else None,
        "certified_at": v.certified_at.isoformat() if v.certified_at else None,
        "rejected_at": v.rejected_at.isoformat() if v.rejected_at else None,
        "rejection_reason": v.rejection_reason,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "created_by": str(v.created_by) if v.created_by else None,
    }
    if include_sensitive:
        base["previous_certified_net"] = (
            str(v.previous_certified_net)
            if v.previous_certified_net is not None else None
        )
        base["retention_this_cert"] = (
            str(v.retention_this_cert)
            if v.retention_this_cert is not None else None
        )
        base["cis_rate_pct"] = (
            str(v.cis_rate_pct) if v.cis_rate_pct is not None else None
        )
        base["cis_deduction_this_cert"] = (
            str(v.cis_deduction_this_cert)
            if v.cis_deduction_this_cert is not None else None
        )
        base["net_payable_this_cert"] = (
            str(v.net_payable_this_cert)
            if v.net_payable_this_cert is not None else None
        )
    else:
        for f in SENSITIVE_FIELDS:
            base[f] = None
    return base


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_valuation(
    db: Session,
    *,
    subcontract_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    gross_applied_to_date: Any,
    labour_portion: Any = 0,
    materials_portion: Any = 0,
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
    request: Optional[Request] = None,
) -> SubcontractValuation:
    """Create a Draft valuation. Subcontract must be Active or Completed."""
    sc = _load_subcontract_for_write(db, subcontract_id, user, perms)
    if sc.status not in ("Active", "Completed"):
        raise ValuationStateError(
            f"Cannot create a valuation on a {sc.status} subcontract "
            "(must be Active or Completed)"
        )

    gross = _q2(_coerce_decimal(
        gross_applied_to_date, field="gross_applied_to_date",
    ))
    if gross < 0:
        raise ValueError("gross_applied_to_date must be ≥ 0")
    labour = _q2(_coerce_decimal(labour_portion, field="labour_portion"))
    materials = _q2(_coerce_decimal(materials_portion, field="materials_portion"))
    if labour < 0 or materials < 0:
        raise ValueError("labour_portion and materials_portion must be ≥ 0")

    number = _next_valuation_number(db, subcontract_id)
    reference = f"VAL-{number:04d}"

    v = SubcontractValuation(
        tenant_id=sc.tenant_id,
        subcontract_id=subcontract_id,
        reference=reference,
        valuation_number=number,
        status="Draft",
        period_start=period_start,
        period_end=period_end,
        gross_applied_to_date=gross,
        gross_this_cert=Decimal("0"),  # computed at certify
        labour_portion=labour,
        materials_portion=materials,
        created_by=user.id,
    )
    db.add(v)
    db.flush()

    record_audit(
        db, action="Create", resource_type="subcontract_valuations",
        resource_id=v.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=field_diff({}, _snapshot(v)),
        metadata={"reference": v.reference},
        request=request,
    )
    return v


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

def submit_valuation(
    db: Session, val_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> SubcontractValuation:
    v = _load_valuation_for_write(db, val_id, user, perms)
    if v.status != "Draft":
        raise ValuationStateError(
            f"Cannot submit a {v.status} valuation"
        )
    v.status = "Submitted"
    v.submitted_at = datetime.now(timezone.utc)
    v.submitted_by = user.id
    db.flush()
    record_audit(
        db, action="Status_Change", resource_type="subcontract_valuations",
        resource_id=v.id, actor_user_id=user.id,
        field_changes=[{"field": "status", "old": "Draft", "new": "Submitted"}],
        metadata={"reference": v.reference},
        request=request,
    )
    return v


# ---------------------------------------------------------------------------
# Reject
# ---------------------------------------------------------------------------

def reject_valuation(
    db: Session, val_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    reason: str,
    request: Optional[Request] = None,
) -> SubcontractValuation:
    if not reason or not reason.strip():
        raise ValueError("rejection reason is required")
    v = _load_valuation_for_write(db, val_id, user, perms)
    if v.status != "Submitted":
        raise ValuationStateError(
            f"Cannot reject a {v.status} valuation (must be Submitted)"
        )
    old_status = v.status
    v.status = "Rejected"
    v.rejected_at = datetime.now(timezone.utc)
    v.rejected_by = user.id
    v.rejection_reason = reason.strip()
    db.flush()
    record_audit(
        db, action="Status_Change", resource_type="subcontract_valuations",
        resource_id=v.id, actor_user_id=user.id,
        field_changes=[
            {"field": "status", "old": old_status, "new": "Rejected"},
        ],
        metadata={"reference": v.reference, "reason": v.rejection_reason},
        request=request,
    )
    return v


# ---------------------------------------------------------------------------
# Certify — the core of 2.8b
# ---------------------------------------------------------------------------

def _pick_budget_line_for_subcontract(
    db: Session, sc: Subcontract,
) -> BudgetLine:
    """Return any non-terminal budget line on the project (the actual
    must hit a real budget line, per actuals service).

    In a fully wired ledger this is configured per-subcontract; for now
    we pick the first available active budget line. If none exists,
    raise — the caller cannot proceed.
    """
    line = db.scalar(
        select(BudgetLine).join(Budget, BudgetLine.budget_id == Budget.id)
        .where(
            Budget.project_id == sc.project_id,
            Budget.status.notin_(("Superseded", "Closed")),
        ).limit(1)
    )
    if line is None:
        raise ValuationStateError(
            "No active budget line available on the project — "
            "cannot post the certified valuation as an actual."
        )
    return line


def certify_valuation(
    db: Session, val_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    transaction_date: Optional[date] = None,
    description: Optional[str] = None,
    request: Optional[Request] = None,
    budget_line_id: Optional[uuid.UUID] = None,
) -> SubcontractValuation:
    """Certify a Submitted valuation. Computes deduction snapshots,
    posts the actual via the EXISTING actuals service, creates the
    Payment notice.

    Per §R0.2 the posted actual carries `net_amount = gross_this_cert`
    (PRE-deduction basis); retention + CIS are recorded as separate
    columns on the actual.
    """
    # Local imports to avoid circular deps.
    from app.schemas.actuals import CreateActualRequest
    from app.services import actuals as actuals_svc
    from app.services import payment_notices as pn_svc

    v = _load_valuation_for_write(db, val_id, user, perms)
    if v.status != "Submitted":
        raise ValuationStateError(
            f"Cannot certify a {v.status} valuation (must be Submitted)"
        )

    sc = _load_subcontract_for_write(db, v.subcontract_id, user, perms)
    if sc.status not in ("Active", "Completed"):
        raise ValuationStateError(
            f"Cannot certify against a {sc.status} subcontract"
        )

    # 1. Previous certified totals.
    prior = db.execute(
        select(
            func.coalesce(
                func.sum(SubcontractValuation.gross_this_cert), 0,
            ),
            func.coalesce(
                func.sum(SubcontractValuation.retention_this_cert), 0,
            ),
            func.coalesce(
                func.sum(SubcontractValuation.net_payable_this_cert), 0,
            ),
        ).where(
            SubcontractValuation.subcontract_id == v.subcontract_id,
            SubcontractValuation.status == "Certified",
        )
    ).one()
    previous_gross_certified = _q2(_coerce_decimal(
        prior[0], field="previous_gross_certified",
    ))
    previous_retention_held = _q2(_coerce_decimal(
        prior[1], field="previous_retention_held",
    ))
    previous_certified_net = _q2(_coerce_decimal(
        prior[2], field="previous_certified_net",
    ))

    # 2. gross_this_cert and validations.
    gross_atd = _q2(v.gross_applied_to_date)
    gross_this_cert = _q2(gross_atd - previous_gross_certified)
    if gross_this_cert < 0:
        raise ValueError(
            "gross_applied_to_date is less than previous_gross_certified "
            f"(application went backwards: {gross_atd} < "
            f"{previous_gross_certified})"
        )
    labour = _q2(v.labour_portion)
    materials = _q2(v.materials_portion)
    if (labour + materials) != gross_this_cert:
        raise ValueError(
            "labour_portion + materials_portion must equal gross_this_cert "
            f"({labour} + {materials} = {labour + materials} != "
            f"{gross_this_cert})"
        )

    # 3. CIS rate (LD2 + LD3).
    if not sc.cis_applies:
        cis_rate = Decimal("0")
    else:
        supplier = db.get(Supplier, sc.subcontractor_id)
        status = supplier.current_cis_status if supplier else None
        cis_rate = cis_rate_for_status(status)

    # 4. Retention movement.
    retention_pct = _q2(sc.retention_pct)
    retention_cumulative = _q2(gross_atd * retention_pct / Decimal("100"))
    retention_this_cert = _q2(retention_cumulative - previous_retention_held)

    # 5. CIS deduction (LD2 — labour only).
    cis_deduction_this_cert = _q2(labour * cis_rate / Decimal("100"))

    # 6. Net payable this cert.
    net_payable_this_cert = _q2(
        gross_this_cert - retention_this_cert - cis_deduction_this_cert,
    )
    if net_payable_this_cert < 0:
        raise ValueError(
            "net_payable_this_cert computed negative — check "
            "retention_pct / CIS rate / labour split inputs"
        )

    # 7. Over-claim warn-not-block.
    over_claim_flag = False
    over_claim_note: Optional[str] = None
    if gross_atd > sc.current_contract_sum:
        over_claim_flag = True
        over_claim_note = (
            f"gross_applied_to_date ({gross_atd}) exceeds "
            f"current_contract_sum ({sc.current_contract_sum}). "
            "Warn-not-block (LD §R3.1 step 5)."
        )

    # 8. Post the actual via the EXISTING actuals service.
    #    §R0.2 PRE-deduction basis: net_amount = gross_this_cert. The
    #    retention_amount/cis_*_amount columns carry the deductions
    #    separately; the actuals service does NOT subtract them from
    #    net_amount (the cost-tracker subtracts retention from
    #    actuals_to_date itself). Confirmed by reading
    #    services/actuals._compute_retention + _compute_cis_deduction
    #    + budgets_reconciliation.recompute_for_line.
    line = (
        db.get(BudgetLine, budget_line_id)
        if budget_line_id is not None
        else _pick_budget_line_for_subcontract(db, sc)
    )
    if line is None:
        raise ValuationStateError(
            "budget_line_id not found"
        )
    budget = db.get(Budget, line.budget_id)
    if budget is None or budget.project_id != sc.project_id:
        raise ValuationStateError(
            "budget_line is not on the subcontract's project"
        )

    supplier_for_actual = db.get(Supplier, sc.subcontractor_id)
    supplier_name = (
        supplier_for_actual.name if supplier_for_actual else "Subcontractor"
    )

    actual_desc = description or (
        f"Subcontract valuation {v.reference} cert "
        f"#{v.valuation_number} ({sc.reference})"
    )
    txn_date = transaction_date or date.today()

    # The actuals.create_actual service computes retention_amount /
    # cis_deduction_amount from the rate fields IF retention_amount /
    # cis fields are not explicitly provided. We pass the explicit
    # `retention_amount` we computed (the MOVEMENT, not the cumulative)
    # so it's not recomputed from rate × net_amount.
    payload = CreateActualRequest(
        project_id=sc.project_id,
        budget_line_id=line.id,
        entity_id=line.entity_id,
        source_type="SC_Valuation",
        source_reference=v.reference,
        transaction_date=txn_date,
        posting_date=txn_date,
        description=actual_desc,
        net_amount=gross_this_cert,
        vat_amount=Decimal("0"),
        vat_rate_pct=Decimal("20"),
        is_vat_recoverable=True,
        currency="GBP",
        supplier_id=sc.subcontractor_id,
        supplier_name_snapshot=supplier_name,
        is_cis_applicable=(sc.cis_applies and cis_rate > 0),
        cis_deduction_rate_pct=(cis_rate if sc.cis_applies else None),
        cis_labour_amount=(labour if sc.cis_applies else None),
        cis_materials_amount=(materials if sc.cis_applies else None),
        retention_rate_pct=(retention_pct if retention_pct > 0 else None),
        retention_amount=(
            retention_this_cert if retention_this_cert != 0 else None
        ),
        related_subcontract_id=sc.id,
    )
    actual = actuals_svc.create_actual(
        db, payload=payload, user=user, perms=perms, request=request,
    )
    actuals_svc.post_actual(
        db, actual_id=actual.id, user=user, perms=perms, request=request,
    )

    # 9. Commit snapshot fields on the valuation row.
    v.gross_this_cert = gross_this_cert
    v.previous_certified_net = previous_certified_net
    v.retention_rate_pct = retention_pct
    v.retention_this_cert = retention_this_cert
    v.cis_rate_pct = cis_rate
    v.cis_deduction_this_cert = cis_deduction_this_cert
    v.net_payable_this_cert = net_payable_this_cert
    v.over_claim_flag = over_claim_flag
    v.over_claim_note = over_claim_note
    v.posted_actual_id = actual.id
    v.status = "Certified"
    v.certified_at = datetime.now(timezone.utc)
    v.certified_by = user.id
    db.flush()

    # 10. Auto-create the Payment notice.
    pn_svc.create_payment_notice_internal(
        db, valuation=v, user=user, request=request,
    )

    record_audit(
        db, action="Status_Change", resource_type="subcontract_valuations",
        resource_id=v.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=[
            {"field": "status", "old": "Submitted", "new": "Certified"},
        ],
        metadata={
            "reference": v.reference,
            "gross_this_cert": str(gross_this_cert),
            "retention_this_cert": str(retention_this_cert),
            "cis_deduction_this_cert": str(cis_deduction_this_cert),
            "net_payable_this_cert": str(net_payable_this_cert),
            "posted_actual_id": str(actual.id),
            "over_claim_flag": over_claim_flag,
        },
        request=request,
    )
    return v


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_valuation(
    db: Session, val_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
) -> SubcontractValuation:
    return _load_valuation_for_read(db, val_id, user, perms)


def list_valuations(
    db: Session,
    *, user: User, perms: UserPermissions,
    subcontract_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> list[SubcontractValuation]:
    if status is not None and status not in VALUATION_STATUSES:
        raise ValueError(
            f"status must be one of {VALUATION_STATUSES}; got {status!r}"
        )
    q = select(SubcontractValuation).where(
        SubcontractValuation.tenant_id == user.tenant_id,
    )
    if subcontract_id is not None:
        q = q.where(SubcontractValuation.subcontract_id == subcontract_id)
    if status is not None:
        q = q.where(SubcontractValuation.status == status)
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None:
            if not allowed:
                return []
            # Join through subcontracts to filter by project visibility.
            q = q.join(
                Subcontract,
                SubcontractValuation.subcontract_id == Subcontract.id,
            ).where(Subcontract.project_id.in_(allowed))
    q = q.order_by(
        SubcontractValuation.valuation_number.desc(),
    ).limit(limit).offset(offset)
    return list(db.scalars(q).all())
