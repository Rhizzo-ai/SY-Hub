"""Subcontracts service — Chat 34 §R3 (Prompt 2.8a).

Subcontracts wrap a subcontractor (LD2). A subcontract may optionally
link a Purchase Order on the same project + subcontractor (LD1;
warn-not-block sum reconciliation).

State machine:
  Draft → Active → Completed
  Draft|Active|Completed → Terminated (terminal)

Audit pattern: service-layer (`record_audit` + `field_diff`) — matches
the 2.5/2.6/2.7 Track-2 cohort.

Numbering: race-safe under the parent project row lock. Mirrors the
BCR `_next_reference` pattern (BCR-NNNN) rather than the PO prefix
table — subcontract refs are project-scoped sequential `SC-NNNN`.

The contract sum invariant (LD4):
  current_contract_sum = original_contract_sum + Σ approved variations
                         folded into the sum (`WithinContractSum`).
Variations approved as `BudgetChange` do NOT alter the contract sum;
they hit the budget via 2.6 `create_bcr(...)` instead.
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
from app.models.projects import Project
from app.models.purchase_orders import PurchaseOrder
from app.models.rbac import UserRole, user_role_projects
from app.models.subcontracts import (
    Subcontract,
    SUBCONTRACT_STATUSES,
    TERMINAL_SUBCONTRACT_STATUSES,
)
from app.models.suppliers import Supplier
from app.models.user import User
from app.services.audit import field_diff, record_audit


# ----------------------------------------------------------------------
# Errors (mirrors the budget_errors / supplier_errors pattern)
# ----------------------------------------------------------------------

class SubcontractNotFoundError(Exception):
    """Raised when a subcontract cannot be found OR is out-of-tenant."""


class SubcontractStateError(Exception):
    """Raised on illegal state transition or business rule violation."""


# ----------------------------------------------------------------------
# Audit snapshot columns
# ----------------------------------------------------------------------

_AUDIT_COLS: tuple[str, ...] = (
    "project_id", "subcontractor_id", "purchase_order_id",
    "reference", "title", "scope_description",
    "status", "original_contract_sum", "current_contract_sum",
    "retention_pct", "cis_applies",
    "start_on", "end_on", "signed_at", "signed_by",
    "po_reconciliation_note",
)


def _snapshot(s: Subcontract) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in _AUDIT_COLS:
        v = getattr(s, col)
        if isinstance(v, Decimal):
            v = str(v)
        out[col] = v
    return out


# ----------------------------------------------------------------------
# Tenant / project scoping (Pattern α replica)
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
    """Raise SubcontractNotFoundError if `project` is not visible."""
    if hasattr(project, "tenant_id") and project.tenant_id != user.tenant_id:
        raise SubcontractNotFoundError("Subcontract not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and project.id not in allowed:
            raise SubcontractNotFoundError("Subcontract not found")


# ----------------------------------------------------------------------
# Numbering — race-safe sequential SC-NNNN within a project.
# ----------------------------------------------------------------------

def _next_reference(db: Session, project_id: uuid.UUID) -> str:
    """Race-safe under parent project row lock held by the caller, OR
    under the unique (project_id, reference) constraint on retry.
    """
    count = db.scalar(
        select(func.count(Subcontract.id)).where(
            Subcontract.project_id == project_id
        )
    ) or 0
    return f"SC-{count + 1:04d}"


# ----------------------------------------------------------------------
# Decimal helpers
# ----------------------------------------------------------------------

def _coerce_decimal(v: Any, *, field: str) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"{field} not numeric: {e}") from e


def _quantize2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"))


# ----------------------------------------------------------------------
# Serialisation
# ----------------------------------------------------------------------

def serialise(s: Subcontract, *, with_sensitive: bool = True) -> dict[str, Any]:
    """Return a JSON-safe representation of a subcontract.

    `with_sensitive=False` nulls contract-sum fields for callers lacking
    `subcontracts.view_sensitive`.
    """
    base: dict[str, Any] = {
        "id": str(s.id),
        "tenant_id": str(s.tenant_id),
        "project_id": str(s.project_id),
        "subcontractor_id": str(s.subcontractor_id),
        "purchase_order_id": (
            str(s.purchase_order_id) if s.purchase_order_id else None
        ),
        # Pack 3.5 — bidirectional package link (NULL on standalone SCs).
        "package_id": (
            str(s.package_id) if s.package_id else None
        ),
        # Pack 3.5 — package.reference enrichment for read-only display.
        "package_reference": (
            s.package.reference
            if s.package_id is not None and s.package is not None
            else None
        ),
        "reference": s.reference,
        "title": s.title,
        "scope_description": s.scope_description,
        "status": s.status,
        "retention_pct": str(s.retention_pct) if s.retention_pct is not None else None,
        "cis_applies": s.cis_applies,
        "start_on": s.start_on.isoformat() if s.start_on else None,
        "end_on": s.end_on.isoformat() if s.end_on else None,
        "signed_at": s.signed_at.isoformat() if s.signed_at else None,
        "signed_by": str(s.signed_by) if s.signed_by else None,
        "po_reconciliation_note": s.po_reconciliation_note,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "created_by": str(s.created_by) if s.created_by else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }
    if with_sensitive:
        base["original_contract_sum"] = str(s.original_contract_sum)
        base["current_contract_sum"] = str(s.current_contract_sum)
    else:
        base["original_contract_sum"] = None
        base["current_contract_sum"] = None
    return base


# ----------------------------------------------------------------------
# Load helpers
# ----------------------------------------------------------------------

def _load_for_read(
    db: Session, sc_id: uuid.UUID, user: User, perms: UserPermissions,
) -> Subcontract:
    s = db.scalar(
        select(Subcontract).where(Subcontract.id == sc_id).options(
            selectinload(Subcontract.variations),
        )
    )
    if s is None:
        raise SubcontractNotFoundError("Subcontract not found")
    project = db.get(Project, s.project_id)
    if project is None:
        raise SubcontractNotFoundError("Subcontract not found")
    _scope_check_project(db, project, user, perms)
    if s.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise SubcontractNotFoundError("Subcontract not found")
    return s


def _load_for_write(
    db: Session, sc_id: uuid.UUID, user: User, perms: UserPermissions,
    *, lock_for_update: bool = True,
) -> Subcontract:
    s = db.get(Subcontract, sc_id)
    if s is None:
        raise SubcontractNotFoundError("Subcontract not found")
    project = db.get(Project, s.project_id)
    if project is None:
        raise SubcontractNotFoundError("Subcontract not found")
    _scope_check_project(db, project, user, perms)
    if s.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise SubcontractNotFoundError("Subcontract not found")
    if lock_for_update:
        s = db.scalar(
            select(Subcontract).where(Subcontract.id == sc_id)
            .with_for_update()
        )
        if s is None:
            raise SubcontractNotFoundError("Subcontract not found")
    return s


# ----------------------------------------------------------------------
# Create
# ----------------------------------------------------------------------

def create_subcontract(
    db: Session,
    *,
    project_id: uuid.UUID,
    subcontractor_id: uuid.UUID,
    title: str,
    user: User,
    perms: UserPermissions,
    purchase_order_id: Optional[uuid.UUID] = None,
    package_id: Optional[uuid.UUID] = None,  # Pack 3.5
    scope_description: Optional[str] = None,
    original_contract_sum: Any = 0,
    retention_pct: Any = 0,
    cis_applies: bool = True,
    start_on: Optional[date] = None,
    end_on: Optional[date] = None,
    request: Optional[Request] = None,
) -> Subcontract:
    """Create a Draft subcontract. Validates LD1 + LD2."""
    if not title or not title.strip():
        raise ValueError("title is required")
    title = title.strip()

    project = db.get(Project, project_id)
    if project is None:
        raise SubcontractNotFoundError("Project not found")
    _scope_check_project(db, project, user, perms)

    # Lock the project row to serialise SC-NNNN allocation.
    db.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    )

    # LD2 — contractor (CIS subcontractor) type guard.
    supplier = db.get(Supplier, subcontractor_id)
    if supplier is None:
        raise ValueError("Contractor not found")
    if supplier.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise ValueError("Contractor not found")
    if supplier.supplier_type != "Contractor":
        raise ValueError(
            f"Counterparty must be a Contractor (got "
            f"supplier_type={supplier.supplier_type!r}). LD2."
        )

    # Pack 3.5 — optional package link. Validate same tenant + project.
    if package_id is not None:
        try:
            package_id = uuid.UUID(str(package_id))
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"package_id is not a valid UUID: {e}"
            ) from e
        from app.models.packages import Package
        pkg = db.get(Package, package_id)
        if pkg is None:
            raise ValueError(f"package_id {package_id} not found")
        if pkg.tenant_id != user.tenant_id and not perms.is_super_admin:
            raise ValueError(f"package_id {package_id} not found")
        if pkg.project_id != project_id:
            raise ValueError(
                f"package_id {package_id} belongs to a different project"
            )

    ocs = _quantize2(_coerce_decimal(
        original_contract_sum, field="original_contract_sum"
    ))
    if ocs < 0:
        raise ValueError("original_contract_sum must be ≥ 0")
    ret = _quantize2(_coerce_decimal(retention_pct, field="retention_pct"))
    if ret < 0 or ret > 100:
        raise ValueError("retention_pct must be between 0 and 100")

    po_note: Optional[str] = None
    if purchase_order_id is not None:
        po = db.get(PurchaseOrder, purchase_order_id)
        if po is None:
            raise ValueError("purchase_order_id not found")
        if po.tenant_id != user.tenant_id and not perms.is_super_admin:
            raise ValueError("purchase_order_id not found")
        if po.project_id != project_id:
            raise ValueError(
                "purchase_order belongs to a different project. LD1."
            )
        if po.supplier_id != subcontractor_id:
            raise ValueError(
                "purchase_order is for a different subcontractor. LD1."
            )
        # LD1 — warn-not-block sum reconciliation.
        po_total = _quantize2(_coerce_decimal(
            po.total_amount or 0, field="po.total_amount"
        ))
        if po_total != ocs:
            po_note = (
                f"PO total ({po_total}) does not match contract sum "
                f"({ocs}) at subcontract creation. LD1 warn-not-block."
            )

    reference = _next_reference(db, project_id)

    s = Subcontract(
        tenant_id=user.tenant_id,
        project_id=project_id,
        subcontractor_id=subcontractor_id,
        purchase_order_id=purchase_order_id,
        package_id=package_id,  # Pack 3.5
        reference=reference,
        title=title,
        scope_description=(
            scope_description.strip()
            if isinstance(scope_description, str) and scope_description.strip()
            else None
        ),
        status="Draft",
        original_contract_sum=ocs,
        current_contract_sum=ocs,
        retention_pct=ret,
        cis_applies=bool(cis_applies),
        start_on=start_on,
        end_on=end_on,
        po_reconciliation_note=po_note,
        created_by=user.id,
    )
    db.add(s)
    db.flush()

    record_audit(
        db, action="Create", resource_type="subcontracts",
        resource_id=s.id, actor_user_id=user.id,
        project_id=project_id,
        field_changes=field_diff({}, _snapshot(s)),
        metadata={"reference": s.reference},
        request=request,
    )
    return s


# ----------------------------------------------------------------------
# Update (Draft / Active per field)
# ----------------------------------------------------------------------

_UPDATE_FIELDS_DRAFT = frozenset({
    "title", "scope_description", "original_contract_sum",
    "retention_pct", "cis_applies", "start_on", "end_on",
    "signed_at", "signed_by",
    "purchase_order_id",
})
# When Active, scope-shape changes are blocked; lifecycle fields stay editable.
_UPDATE_FIELDS_ACTIVE = frozenset({
    "title", "start_on", "end_on", "signed_at", "signed_by",
})


def update_subcontract(
    db: Session, sc_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    payload: dict[str, Any], request: Optional[Request] = None,
) -> Subcontract:
    s = _load_for_write(db, sc_id, user, perms)
    if s.status in TERMINAL_SUBCONTRACT_STATUSES:
        raise SubcontractStateError(
            f"Cannot edit a {s.status} subcontract"
        )

    allowed = (
        _UPDATE_FIELDS_DRAFT if s.status == "Draft"
        else _UPDATE_FIELDS_ACTIVE
    )
    bad = set(payload.keys()) - allowed
    if bad:
        raise SubcontractStateError(
            f"Fields not editable in status={s.status}: {sorted(bad)}"
        )

    before = _snapshot(s)

    if "title" in payload:
        t = payload["title"]
        if not isinstance(t, str) or not t.strip():
            raise ValueError("title is required")
        s.title = t.strip()
    if "scope_description" in payload:
        v = payload["scope_description"]
        s.scope_description = (
            v.strip() if isinstance(v, str) and v.strip() else None
        )
    if "original_contract_sum" in payload:
        ocs = _quantize2(_coerce_decimal(
            payload["original_contract_sum"], field="original_contract_sum",
        ))
        if ocs < 0:
            raise ValueError("original_contract_sum must be ≥ 0")
        # Keep the delta against current_contract_sum stable: when not yet
        # Active, current_contract_sum tracks original (no variations yet).
        if s.status == "Draft":
            s.original_contract_sum = ocs
            s.current_contract_sum = ocs
        else:
            s.original_contract_sum = ocs
    if "retention_pct" in payload:
        r = _quantize2(_coerce_decimal(
            payload["retention_pct"], field="retention_pct",
        ))
        if r < 0 or r > 100:
            raise ValueError("retention_pct must be between 0 and 100")
        s.retention_pct = r
    if "cis_applies" in payload:
        s.cis_applies = bool(payload["cis_applies"])
    if "start_on" in payload:
        s.start_on = payload["start_on"]
    if "end_on" in payload:
        s.end_on = payload["end_on"]
    if "signed_at" in payload:
        s.signed_at = payload["signed_at"]
    if "signed_by" in payload:
        s.signed_by = payload["signed_by"]
    if "purchase_order_id" in payload:
        # Re-validate LD1 if (un)linking a PO.
        new_po_id = payload["purchase_order_id"]
        po_note: Optional[str] = None
        if new_po_id is not None:
            po = db.get(PurchaseOrder, new_po_id)
            if po is None:
                raise ValueError("purchase_order_id not found")
            if po.tenant_id != user.tenant_id and not perms.is_super_admin:
                raise ValueError("purchase_order_id not found")
            if po.project_id != s.project_id:
                raise ValueError(
                    "purchase_order belongs to a different project. LD1."
                )
            if po.supplier_id != s.subcontractor_id:
                raise ValueError(
                    "purchase_order is for a different subcontractor. LD1."
                )
            po_total = _quantize2(_coerce_decimal(
                po.total_amount or 0, field="po.total_amount"
            ))
            if po_total != _quantize2(s.current_contract_sum):
                po_note = (
                    f"PO total ({po_total}) does not match contract sum "
                    f"({s.current_contract_sum}). LD1 warn-not-block."
                )
        s.purchase_order_id = new_po_id
        s.po_reconciliation_note = po_note

    db.flush()
    changes = field_diff(before, _snapshot(s))
    if changes:
        record_audit(
            db, action="Update", resource_type="subcontracts",
            resource_id=s.id, actor_user_id=user.id,
            project_id=s.project_id,
            field_changes=changes,
            metadata={"reference": s.reference},
            request=request,
        )
    return s


# ----------------------------------------------------------------------
# State transitions
# ----------------------------------------------------------------------

def _transition(
    db: Session, s: Subcontract, *, new_status: str,
    user: User, request: Optional[Request],
    extra_metadata: Optional[dict] = None,
) -> Subcontract:
    old = s.status
    s.status = new_status
    db.flush()
    record_audit(
        db, action="Status_Change", resource_type="subcontracts",
        resource_id=s.id, actor_user_id=user.id,
        project_id=s.project_id,
        field_changes=[{"field": "status", "old": old, "new": new_status}],
        metadata={"reference": s.reference, **(extra_metadata or {})},
        request=request,
    )
    return s


def activate_subcontract(
    db: Session, sc_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> Subcontract:
    s = _load_for_write(db, sc_id, user, perms)
    if s.status != "Draft":
        raise SubcontractStateError(
            f"Can only activate a Draft subcontract; current={s.status}"
        )
    if s.signed_at is None:
        raise SubcontractStateError(
            "Cannot activate an unsigned subcontract (set signed_at first)"
        )
    return _transition(db, s, new_status="Active", user=user, request=request)


def complete_subcontract(
    db: Session, sc_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> Subcontract:
    s = _load_for_write(db, sc_id, user, perms)
    if s.status != "Active":
        raise SubcontractStateError(
            f"Can only complete an Active subcontract; current={s.status}"
        )
    return _transition(
        db, s, new_status="Completed", user=user, request=request,
    )


def terminate_subcontract(
    db: Session, sc_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> Subcontract:
    s = _load_for_write(db, sc_id, user, perms)
    if s.status in TERMINAL_SUBCONTRACT_STATUSES:
        raise SubcontractStateError(
            f"Subcontract is already terminal ({s.status})"
        )
    return _transition(
        db, s, new_status="Terminated", user=user, request=request,
    )


# ----------------------------------------------------------------------
# Read helpers
# ----------------------------------------------------------------------

def get_subcontract(
    db: Session, sc_id: uuid.UUID, *, user: User, perms: UserPermissions,
) -> Subcontract:
    return _load_for_read(db, sc_id, user, perms)


def list_subcontracts(
    db: Session, *, user: User, perms: UserPermissions,
    project_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> list[Subcontract]:
    if status is not None and status not in SUBCONTRACT_STATUSES:
        raise ValueError(
            f"status must be one of {SUBCONTRACT_STATUSES}; got {status!r}"
        )
    q = select(Subcontract).where(Subcontract.tenant_id == user.tenant_id)
    if project_id is not None:
        q = q.where(Subcontract.project_id == project_id)
    if status is not None:
        q = q.where(Subcontract.status == status)
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None:
            if not allowed:
                return []
            q = q.where(Subcontract.project_id.in_(allowed))
    q = q.order_by(Subcontract.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(q).all())
