"""Retention releases service — Chat 35 §R3.3 (Prompt 2.8b).

Two release types per subcontract (each releasable ONCE):
  - `PC`  — Practical Completion release (default 50%)
  - `DLP` — Defects Liability Period end release (the rest)

Each release posts a NEGATIVE-retention actual (source_type='SC_Valuation')
to flow the held retention back into actuals_to_date (cost-tracker sees
the released retention as paid out).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.auth.permissions import UserPermissions
from app.models.actuals import Actual
from app.models.budgets import Budget, BudgetLine
from app.models.rbac import UserRole, user_role_projects
from app.models.sc_valuations import (
    RetentionRelease, RETENTION_RELEASE_TYPES,
)
from app.models.subcontracts import Subcontract
from app.models.suppliers import Supplier
from app.models.user import User
from app.services.audit import field_diff, record_audit


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class RetentionReleaseNotFoundError(Exception):
    """Raised on missing / out-of-tenant subcontract."""


class RetentionReleaseStateError(Exception):
    """Raised on business rule violations (e.g. type already released)."""


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
# Helpers
# ---------------------------------------------------------------------------

def _coerce_decimal(v: Any, *, field: str) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"{field} not numeric: {e}") from e


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"))


def _load_subcontract_for_write(
    db: Session, subcontract_id: uuid.UUID,
    user: User, perms: UserPermissions,
) -> Subcontract:
    sc = db.scalar(
        select(Subcontract).where(Subcontract.id == subcontract_id)
        .with_for_update()
    )
    if sc is None:
        raise RetentionReleaseNotFoundError("Subcontract not found")
    if sc.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise RetentionReleaseNotFoundError("Subcontract not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and sc.project_id not in allowed:
            raise RetentionReleaseNotFoundError("Subcontract not found")
    return sc


def _retention_held_for_subcontract(
    db: Session, subcontract_id: uuid.UUID,
) -> Decimal:
    """Sum of retention_amount from Posted/Paid SC_Valuation actuals
    not yet retention_released, minus releases already booked
    (those carry negative retention_amount)."""
    total = db.scalar(
        select(func.coalesce(func.sum(Actual.retention_amount), 0))
        .where(
            Actual.related_subcontract_id == subcontract_id,
            Actual.source_type == "SC_Valuation",
            Actual.status.in_(("Posted", "Paid")),
            Actual.retention_released.is_(False),
            Actual.retention_amount.isnot(None),
        )
    ) or 0
    return _q2(_coerce_decimal(total, field="retention_held"))


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------

def release_retention(
    db: Session,
    *,
    subcontract_id: uuid.UUID,
    release_type: str,
    user: User,
    perms: UserPermissions,
    release_pct: Any = None,
    released_on: Optional[date] = None,
    notes: Optional[str] = None,
    request: Optional[Request] = None,
) -> RetentionRelease:
    """Release retention (PC or DLP) on a subcontract.

    Posts a NEGATIVE-retention actual to flow the released amount into
    actuals_to_date.

    `release_pct` defaults to 50 for PC and 100 for DLP (i.e. the
    remaining retention pool after PC).
    """
    from app.schemas.actuals import CreateActualRequest
    from app.services import actuals as actuals_svc

    if release_type not in RETENTION_RELEASE_TYPES:
        raise ValueError(
            f"release_type must be one of {RETENTION_RELEASE_TYPES}; "
            f"got {release_type!r}"
        )

    sc = _load_subcontract_for_write(db, subcontract_id, user, perms)

    # Default pct: PC = 50, DLP = 100 of the remaining held.
    if release_pct is None:
        pct = Decimal("50") if release_type == "PC" else Decimal("100")
    else:
        pct = _q2(_coerce_decimal(release_pct, field="release_pct"))
    if pct <= 0 or pct > 100:
        raise ValueError("release_pct must be in (0, 100]")

    # Total retention currently held on this subcontract.
    held = _retention_held_for_subcontract(db, subcontract_id)
    if held <= 0:
        raise RetentionReleaseStateError(
            "No retention held against this subcontract to release"
        )

    amount = _q2(held * pct / Decimal("100"))
    rel_date = released_on or date.today()

    # Pick a budget line — same heuristic as certify (any active line).
    line = db.scalar(
        select(BudgetLine).join(Budget, BudgetLine.budget_id == Budget.id)
        .where(
            Budget.project_id == sc.project_id,
            Budget.status.notin_(("Superseded", "Closed")),
        ).limit(1)
    )
    if line is None:
        raise RetentionReleaseStateError(
            "No active budget line available on the project — "
            "cannot post the retention release as an actual."
        )
    supplier = db.get(Supplier, sc.subcontractor_id)
    supplier_name = supplier.name if supplier else "Subcontractor"

    description = (
        f"Retention release {release_type} ({pct}%) — {sc.reference}"
    )

    # Negative retention movement; net_amount=0 (no new work value).
    payload = CreateActualRequest(
        project_id=sc.project_id,
        budget_line_id=line.id,
        entity_id=line.entity_id,
        source_type="SC_Valuation",
        source_reference=f"RETENTION_RELEASE_{release_type}",
        transaction_date=rel_date,
        posting_date=rel_date,
        description=description,
        net_amount=Decimal("0"),
        vat_amount=Decimal("0"),
        vat_rate_pct=Decimal("20"),
        is_vat_recoverable=True,
        currency="GBP",
        supplier_id=sc.subcontractor_id,
        supplier_name_snapshot=supplier_name,
        is_cis_applicable=False,
        retention_amount=-amount,  # NEGATIVE — releases the held bucket
        related_subcontract_id=sc.id,
    )
    actual = actuals_svc.create_actual(
        db, payload=payload, user=user, perms=perms, request=request,
    )
    actuals_svc.post_actual(
        db, actual_id=actual.id, user=user, perms=perms, request=request,
    )

    row = RetentionRelease(
        tenant_id=sc.tenant_id,
        subcontract_id=sc.id,
        release_type=release_type,
        release_pct=pct,
        amount_released=amount,
        released_on=rel_date,
        released_by=user.id,
        posted_actual_id=actual.id,
        notes=notes,
        created_by=user.id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "uq_retention_releases_subcontract_type" in str(e.orig).lower():
            raise RetentionReleaseStateError(
                f"Retention release type {release_type!r} already exists "
                f"on this subcontract"
            ) from e
        raise

    record_audit(
        db, action="Release_Retention", resource_type="retention_releases",
        resource_id=row.id, actor_user_id=user.id,
        project_id=sc.project_id,
        field_changes=field_diff({}, {
            "subcontract_id": str(sc.id),
            "release_type": release_type,
            "release_pct": str(pct),
            "amount_released": str(amount),
            "released_on": rel_date.isoformat(),
            "posted_actual_id": str(actual.id),
        }),
        metadata={
            "subcontract_reference": sc.reference,
            "release_type": release_type,
            "amount_released": str(amount),
        },
        request=request,
    )
    return row


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_releases(
    db: Session,
    *,
    subcontract_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
) -> list[RetentionRelease]:
    sc = db.get(Subcontract, subcontract_id)
    if sc is None:
        raise RetentionReleaseNotFoundError("Subcontract not found")
    if sc.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise RetentionReleaseNotFoundError("Subcontract not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and sc.project_id not in allowed:
            raise RetentionReleaseNotFoundError("Subcontract not found")
    return list(db.scalars(
        select(RetentionRelease)
        .where(RetentionRelease.subcontract_id == subcontract_id)
        .order_by(RetentionRelease.created_at.desc())
    ).all())


def serialise(r: RetentionRelease) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "tenant_id": str(r.tenant_id),
        "subcontract_id": str(r.subcontract_id),
        "release_type": r.release_type,
        "release_pct": str(r.release_pct),
        "amount_released": str(r.amount_released),
        "released_on": r.released_on.isoformat() if r.released_on else None,
        "released_by": str(r.released_by) if r.released_by else None,
        "posted_actual_id": (
            str(r.posted_actual_id) if r.posted_actual_id else None
        ),
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
