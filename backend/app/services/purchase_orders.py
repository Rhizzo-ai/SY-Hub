"""Purchase Orders service — Chat 24 §R2 (Prompt 2.5).

Core CRUD + state transitions for the PurchaseOrder entity. Approval
flows and receipt handling are deferred to R3 / R4 — only the
"submit + auto-issue or pending_approval", "issue from approved",
"void", and "close" transitions are implemented here.

Every CUD emits an audit_log row with a field-level diff via the
shared `field_diff` / `record_audit` utilities.

Pricing fields (`unit_rate`, `net_amount`, `vat_amount`,
`gross_amount`, `subtotal_amount`, `vat_amount`, `total_amount`) are
visible only to callers with `pos.view_sensitive`. The router applies
that gate at serialisation; this module returns full data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from fastapi import Request
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from app.auth.permissions import UserPermissions
from app.models.budgets import Budget, BudgetLine
from app.models.purchase_orders import (
    PurchaseOrder,
    PurchaseOrderLine,
    HEADER_ANNOTATION_FIELDS,
    TERMINAL_PO_STATUSES,
)
from app.models.suppliers import Supplier
from app.models.user import User
from app.services import po_numbering, po_transitions
from app.services.audit import field_diff, record_audit
from app.services.budgets_reconciliation import recompute_for_po
from app.services.po_authz import (
    EditPermission,
    PoNotFound,
    check_can_edit_fields,
    edit_tier_for,
    load_po_for_read,
    load_po_for_write,
    visible_project_ids,
)


# Columns we snapshot for audit diffing of the header.
_PO_AUDIT_COLS: tuple[str, ...] = (
    "po_number", "supplier_id", "budget_id", "status",
    "issue_date", "required_by_date", "delivery_address", "delivery_notes",
    "subtotal_amount", "vat_amount", "total_amount", "currency",
    "approval_required", "approval_reason", "external_reference", "notes",
    "submitted_at", "submitted_by",
    "approved_at", "approved_by",
    "issued_at", "issued_by",
    "closed_at", "closed_by", "closed_reason",
    "voided_at", "voided_by", "voided_reason",
)

_LINE_AUDIT_COLS: tuple[str, ...] = (
    "budget_line_id", "cost_code", "line_number", "description",
    "quantity", "unit", "unit_rate",
    "net_amount", "vat_rate", "vat_amount", "gross_amount",
    "notes",
)


def _snap_po(po: PurchaseOrder) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in _PO_AUDIT_COLS:
        v = getattr(po, col)
        if isinstance(v, Decimal):
            v = str(v)
        out[col] = v
    return out


def _snap_line(line: PurchaseOrderLine) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in _LINE_AUDIT_COLS:
        v = getattr(line, col)
        if isinstance(v, Decimal):
            v = str(v)
        out[col] = v
    return out


# ─────────────────────────────────────────────────────────────────────────
# Validation helpers
# ─────────────────────────────────────────────────────────────────────────

def _q(v: Any) -> Decimal:
    """Coerce-to-Decimal helper; lets the spec values flow straight through."""
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"not numeric: {v!r}") from e


def _compute_line_totals(
    line_payload: dict[str, Any],
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Return (quantity, unit_rate, vat_rate, net_amount, vat_amount, gross).

    All values quantized to the column's scale (4 / 4 / 2 / 2 / 2 / 2).
    """
    qty = _q(line_payload.get("quantity"))
    if qty <= 0:
        raise ValueError("Line quantity must be > 0")
    rate = _q(line_payload.get("unit_rate"))
    if rate < 0:
        raise ValueError("Line unit_rate must be >= 0")
    vat_rate = _q(line_payload.get("vat_rate", Decimal("20.00")))
    if vat_rate < 0 or vat_rate > 100:
        raise ValueError("Line vat_rate must be between 0 and 100")
    net = (qty * rate).quantize(Decimal("0.01"))
    vat_amt = (net * vat_rate / Decimal("100")).quantize(Decimal("0.01"))
    gross = (net + vat_amt).quantize(Decimal("0.01"))
    return (
        qty.quantize(Decimal("0.0001")),
        rate.quantize(Decimal("0.0001")),
        vat_rate.quantize(Decimal("0.01")),
        net, vat_amt, gross,
    )


def _validate_supplier(
    db: Session, tenant_id: uuid.UUID, supplier_id: uuid.UUID,
) -> Supplier:
    s = db.scalar(
        select(Supplier).where(
            Supplier.id == supplier_id,
            Supplier.tenant_id == tenant_id,
        )
    )
    if s is None:
        raise ValueError(f"Supplier {supplier_id} not found in tenant")
    if s.is_archived:
        raise ValueError("Cannot use an archived supplier on a new PO")
    return s


def _validate_budget(
    db: Session, project_id: uuid.UUID, budget_id: uuid.UUID,
) -> Budget:
    b = db.scalar(
        select(Budget).where(
            Budget.id == budget_id,
            Budget.project_id == project_id,
        )
    )
    if b is None:
        raise ValueError(
            f"Budget {budget_id} not found for project {project_id}"
        )
    # Build pack G2.5 (D7): POs must be raised against an Active budget.
    # Draft / Locked / Superseded / Closed all reject.
    if b.status != "Active":
        raise ValueError(
            f"Cannot create a PO against a {b.status} budget — "
            f"only Active budgets accept new POs (po/budget-not-active)"
        )
    return b


def _validate_budget_lines(
    db: Session, budget_id: uuid.UUID, line_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, BudgetLine]:
    """Ensure every line_id belongs to `budget_id`. Returns id -> BudgetLine."""
    ids = list({lid for lid in line_ids})
    if not ids:
        return {}
    rows = db.scalars(
        select(BudgetLine).where(
            BudgetLine.budget_id == budget_id,
            BudgetLine.id.in_(ids),
        )
    ).all()
    found = {b.id: b for b in rows}
    missing = [str(i) for i in ids if i not in found]
    if missing:
        raise ValueError(
            f"Budget line(s) {missing} do not belong to budget {budget_id}"
        )
    return found


# ─────────────────────────────────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────────────────────────────────

def create_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    project_id: uuid.UUID,
    payload: dict[str, Any],
    request: Optional[Request] = None,
) -> PurchaseOrder:
    """Create a Draft PO with one or more lines.

    Required payload:
      - supplier_id   (uuid)
      - budget_id     (uuid)
      - lines         (list of line dicts)

    Optional payload:
      - po_number_prefix_id (uuid; defaults to project default)
      - external_po_number  (str; overrides auto-numbering — caller must
                              be authorised to do so; for R2 we always
                              auto-allocate)
      - issue_date          (date)
      - required_by_date    (date)
      - delivery_address    (text)
      - delivery_notes      (text)
      - external_reference  (str)
      - approval_required   (bool, default false)
      - approval_reason     (text)
      - notes               (text)

    Each line dict must contain:
      - budget_line_id (uuid)
      - description    (text)
      - quantity       (decimal)
      - unit_rate      (decimal)
      - cost_code      (str, required by schema; from the budget_line)
      - vat_rate       (decimal, default 20.00)
      - unit           (str, optional)
      - notes          (str, optional)
      - line_number    (int, defaults to position)
    """
    from app.models.projects import Project
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("Project not found")
    # Pattern α: ensure visibility.
    from app.services.budgets import _scope_check_project
    from app.services.budget_errors import BudgetNotFoundError
    try:
        _scope_check_project(db, project, user, perms)
    except BudgetNotFoundError as e:
        raise PoNotFound(str(e)) from e
    # Project doesn't carry tenant_id directly (it's derived via
    # primary_entity); existing convention is to guard with hasattr.
    if hasattr(project, "tenant_id") and project.tenant_id != user.tenant_id:
        raise PoNotFound("Project not found")

    if "supplier_id" not in payload:
        raise ValueError("supplier_id is required")
    if "budget_id" not in payload:
        raise ValueError("budget_id is required")
    if not payload.get("lines"):
        raise ValueError("At least one line is required")

    supplier = _validate_supplier(
        db, user.tenant_id, uuid.UUID(str(payload["supplier_id"]))
    )
    budget = _validate_budget(
        db, project_id, uuid.UUID(str(payload["budget_id"]))
    )

    # Pack 3.5 — optional bidirectional package link. Validate it
    # exists, lives in the same tenant, and points at the same project.
    # On the AWARD path the package is guaranteed valid; this guard
    # protects the standalone path (callers passing `package_id` via
    # POCreate).
    package_id_raw = payload.get("package_id")
    package_id: Optional[uuid.UUID] = None
    if package_id_raw is not None:
        try:
            package_id = uuid.UUID(str(package_id_raw))
        except (TypeError, ValueError) as e:
            raise ValueError(f"package_id is not a valid UUID: {e}") from e
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

    line_payloads = list(payload["lines"])
    budget_line_ids = [
        uuid.UUID(str(lp["budget_line_id"])) for lp in line_payloads
    ]
    blines = _validate_budget_lines(db, budget.id, budget_line_ids)

    # Compute totals + line aggregates.
    subtotal = Decimal("0")
    vat_total = Decimal("0")
    gross_total = Decimal("0")
    prepared_lines: list[dict[str, Any]] = []
    for idx, lp in enumerate(line_payloads, start=1):
        bline = blines[uuid.UUID(str(lp["budget_line_id"]))]
        qty, rate, vat_rate, net, vat_amt, gross = _compute_line_totals(lp)
        prepared_lines.append({
            "budget_line_id": bline.id,
            "cost_code": str(lp.get("cost_code") or "")[:20] or _budget_line_cost_code(db, bline),
            "line_number": int(lp.get("line_number", idx)),
            "description": str(lp.get("description") or "").strip()[:5000] or "(unlabelled)",
            "quantity": qty,
            "unit": (lp.get("unit") or None),
            "unit_rate": rate,
            "vat_rate": vat_rate,
            "net_amount": net,
            "vat_amount": vat_amt,
            "gross_amount": gross,
            "notes": (lp.get("notes") or None),
        })
        subtotal += net
        vat_total += vat_amt
        gross_total += gross

    # Allocate the next po_number under a row-lock.
    prefix_id_raw = payload.get("po_number_prefix_id")
    prefix_id = uuid.UUID(str(prefix_id_raw)) if prefix_id_raw else None
    po_number, prefix_row, seq = po_numbering.allocate_next_number(
        db, project_id, prefix_id=prefix_id,
    )

    po = PurchaseOrder(
        tenant_id=user.tenant_id,
        project_id=project_id,
        po_number=po_number,
        po_number_prefix_id=prefix_row.id,
        po_sequence=seq,
        supplier_id=supplier.id,
        budget_id=budget.id,
        package_id=package_id,  # Pack 3.5
        status="draft",
        issue_date=payload.get("issue_date"),
        required_by_date=payload.get("required_by_date"),
        delivery_address=payload.get("delivery_address"),
        delivery_notes=payload.get("delivery_notes"),
        subtotal_amount=subtotal.quantize(Decimal("0.01")),
        vat_amount=vat_total.quantize(Decimal("0.01")),
        total_amount=gross_total.quantize(Decimal("0.01")),
        currency="GBP",
        approval_required=bool(payload.get("approval_required", False)),
        approval_reason=payload.get("approval_reason"),
        external_reference=payload.get("external_reference"),
        notes=payload.get("notes"),
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(po)
    db.flush()  # need po.id for line FKs

    for lp in prepared_lines:
        line = PurchaseOrderLine(
            purchase_order_id=po.id,
            created_by=user.id,
            updated_by=user.id,
            **lp,
        )
        db.add(line)
    db.flush()
    # Re-read header — the DB trigger may have re-summed totals from
    # lines (this is idempotent — our pre-computed totals match).
    db.refresh(po)

    record_audit(
        db, action="Create",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=project_id,
        field_changes=field_diff({}, _snap_po(po)),
        metadata={
            "po_number": po.po_number,
            "supplier_id": str(po.supplier_id),
            "line_count": len(prepared_lines),
            "total_amount": str(po.total_amount),
        },
        request=request,
    )
    return po


def _budget_line_cost_code(db: Session, bline: BudgetLine) -> str:
    """Fallback cost_code derivation from the budget_line's cost_code FK.

    Looks up the cost_code.code via a single targeted SELECT — used only
    when the caller didn't supply `cost_code` explicitly. Trimmed to 20
    chars (schema cap).
    """
    from app.models.cost_codes import CostCode
    cc = db.get(CostCode, bline.cost_code_id)
    code = (getattr(cc, "code", None) or "")[:20]
    return code or "UNKNOWN"


# ─────────────────────────────────────────────────────────────────────────
# Update
# ─────────────────────────────────────────────────────────────────────────

# Fields the API exposes for PATCH (header only; line edits are a
# separate endpoint — out of R2 scope).
_PATCHABLE_HEADER_FIELDS: tuple[str, ...] = (
    "supplier_id", "budget_id",
    "issue_date", "required_by_date",
    "delivery_address", "delivery_notes",
    "external_reference", "notes",
    "approval_required", "approval_reason",
)


def update_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    payload: dict[str, Any],
    request: Optional[Request] = None,
) -> PurchaseOrder:
    """Partial header update.

    The edit-tier guard (`po_authz.check_can_edit_fields`) determines
    which fields are accepted:
      - FULL tier (draft / approved): any patchable header field.
      - HEADER_ANNOTATION_ONLY (issued / receipted): notes,
        delivery_notes, external_reference only.
      - READ_ONLY: 403 if any field present.
    """
    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)

    # Restrict the payload to known patchable fields.
    fields = [k for k in payload.keys() if k in _PATCHABLE_HEADER_FIELDS]
    extras = [k for k in payload.keys() if k not in _PATCHABLE_HEADER_FIELDS]
    if extras:
        raise ValueError(
            f"Fields not patchable via this endpoint: {extras}"
        )

    tier, disallowed = check_can_edit_fields(po, perms, fields)
    if disallowed:
        # Raise 403 with full problem-detail (router maps to HTTPException).
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail={
                "type": "po_edit_forbidden",
                "title": "Field(s) not editable in this status",
                "po_status": po.status,
                "fields_attempted": fields,
                "disallowed_fields": disallowed,
                "allowed_fields": (
                    sorted(HEADER_ANNOTATION_FIELDS)
                    if tier is EditPermission.HEADER_ANNOTATION_ONLY
                    else list(_PATCHABLE_HEADER_FIELDS)
                ),
            },
        )

    before = _snap_po(po)

    # Apply each field with the appropriate validator.
    if "supplier_id" in payload:
        new_sid = uuid.UUID(str(payload["supplier_id"]))
        if new_sid != po.supplier_id:
            _validate_supplier(db, user.tenant_id, new_sid)
            po.supplier_id = new_sid

    if "budget_id" in payload:
        new_bid = uuid.UUID(str(payload["budget_id"]))
        if new_bid != po.budget_id:
            _validate_budget(db, po.project_id, new_bid)
            po.budget_id = new_bid

    for k in ("issue_date", "required_by_date"):
        if k in payload:
            setattr(po, k, payload[k] or None)

    for k in ("delivery_address", "delivery_notes",
              "external_reference", "notes", "approval_reason"):
        if k in payload:
            setattr(po, k, payload[k] or None)

    if "approval_required" in payload:
        po.approval_required = bool(payload["approval_required"])

    po.updated_by = user.id
    po.updated_at = datetime.now(timezone.utc)
    db.flush()

    after = _snap_po(po)
    changes = field_diff(before, after)
    if changes:
        record_audit(
            db, action="Update",
            resource_type="purchase_order",
            resource_id=po.id,
            actor_user_id=user.id,
            project_id=po.project_id,
            field_changes=changes,
            metadata={"po_number": po.po_number, "edit_tier": tier.value},
            request=request,
        )
    return po


# ─────────────────────────────────────────────────────────────────────────
# Delete (draft only)
# ─────────────────────────────────────────────────────────────────────────

def delete_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    request: Optional[Request] = None,
) -> None:
    """Hard-delete a Draft PO.

    Only Draft status is deletable. All other statuses must be voided
    (or closed if receipted) — see `void_po` / `close_po`.
    """
    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    if po.status != "draft":
        raise ValueError(
            f"Only draft POs may be deleted; current status={po.status!r}. "
            f"Use void or close instead."
        )

    before = _snap_po(po)
    record_audit(
        db, action="Delete",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, {}),
        metadata={"po_number": po.po_number},
        request=request,
    )
    db.delete(po)
    db.flush()


# ─────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────

def submit_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    request: Optional[Request] = None,
) -> PurchaseOrder:
    """Submit a Draft PO.

    Branches on `po.approval_required`:
      - true  -> pending_approval (records submit stamp)
      - false -> issued           (auto-issues; records submit + issue stamps)
    """
    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    before = _snap_po(po)
    target = po_transitions.submit(po, user.id)
    po.updated_by = user.id
    po.updated_at = datetime.now(timezone.utc)
    db.flush()
    # Chat 39 §R2 A1: PG trigger updated committed_value; Python is the
    # sole writer of committed_not_invoiced — recompute touched lines.
    recompute_for_po(db, po.id)
    after = _snap_po(po)
    # Pick the action verb appropriate to the resulting status.
    action = "Submit" if target == "pending_approval" else "Status_Change"
    record_audit(
        db, action=action,
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, after),
        metadata={
            "po_number": po.po_number,
            "new_status": target,
            "auto_issued": target == "issued",
        },
        request=request,
    )
    return po


def issue_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    request: Optional[Request] = None,
) -> PurchaseOrder:
    """Issue an Approved PO (approved -> issued)."""
    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    before = _snap_po(po)
    po_transitions.issue(po, user.id)
    po.updated_by = user.id
    po.updated_at = datetime.now(timezone.utc)
    db.flush()
    recompute_for_po(db, po.id)
    after = _snap_po(po)
    record_audit(
        db, action="Status_Change",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, after),
        metadata={"po_number": po.po_number, "new_status": "issued"},
        request=request,
    )
    return po


def void_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    reason: str,
    request: Optional[Request] = None,
) -> PurchaseOrder:
    """Void a PO with a required reason."""
    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    before = _snap_po(po)
    po_transitions.void(po, user.id, reason)
    po.updated_by = user.id
    po.updated_at = datetime.now(timezone.utc)
    db.flush()
    recompute_for_po(db, po.id)
    after = _snap_po(po)
    record_audit(
        db, action="Void",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, after),
        metadata={
            "po_number": po.po_number,
            "new_status": "voided",
            "reason": reason.strip(),
        },
        request=request,
    )
    return po


def close_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    reason: Optional[str] = None,
    request: Optional[Request] = None,
) -> PurchaseOrder:
    """Close a PO (issued / receipted -> closed)."""
    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    before = _snap_po(po)
    po_transitions.close(po, user.id, reason)
    po.updated_by = user.id
    po.updated_at = datetime.now(timezone.utc)
    db.flush()
    recompute_for_po(db, po.id)
    after = _snap_po(po)
    record_audit(
        db, action="Status_Change",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, after),
        metadata={
            "po_number": po.po_number,
            "new_status": "closed",
            "reason": (reason or "").strip() or None,
        },
        request=request,
    )
    return po


# ─────────────────────────────────────────────────────────────────────────
# List / Get
# ─────────────────────────────────────────────────────────────────────────

def list_pos(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    project_id: Optional[uuid.UUID] = None,
    supplier_id: Optional[uuid.UUID] = None,
    budget_line_id: Optional[uuid.UUID] = None,
    budget_id: Optional[uuid.UUID] = None,
    status_in: Optional[Iterable[str]] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PurchaseOrder], int]:
    """Tenant-scoped paginated list with Pattern α visibility.

    Returns (rows, total_unpaged).

    Optional `budget_line_id` / `budget_id` filters JOIN
    purchase_order_lines and return DISTINCT POs (a PO touching multiple
    lines under the same budget is returned ONCE).
    """
    stmt = select(PurchaseOrder).where(
        PurchaseOrder.tenant_id == user.tenant_id
    )
    if project_id is not None:
        stmt = stmt.where(PurchaseOrder.project_id == project_id)
    elif not perms.is_super_admin:
        allowed = visible_project_ids(db, user.id, user.tenant_id)
        if allowed is None:
            pass  # unrestricted
        elif not allowed:
            return [], 0
        else:
            stmt = stmt.where(PurchaseOrder.project_id.in_(allowed))

    if supplier_id is not None:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    if status_in is not None:
        statuses = [s for s in status_in if s]
        if statuses:
            stmt = stmt.where(PurchaseOrder.status.in_(statuses))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(PurchaseOrder.po_number).like(like)
        )

    # JOIN purchase_order_lines for budget_line_id / budget_id filters.
    # SELECT DISTINCT so a PO touching multiple lines under the same
    # filter target appears once.
    if budget_line_id is not None or budget_id is not None:
        stmt = stmt.join(
            PurchaseOrderLine,
            PurchaseOrderLine.purchase_order_id == PurchaseOrder.id,
        )
        if budget_line_id is not None:
            stmt = stmt.where(PurchaseOrderLine.budget_line_id == budget_line_id)
        if budget_id is not None:
            stmt = stmt.join(
                BudgetLine, BudgetLine.id == PurchaseOrderLine.budget_line_id,
            ).where(BudgetLine.budget_id == budget_id)
        stmt = stmt.distinct()

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(
        stmt.order_by(PurchaseOrder.created_at.desc())
        .limit(min(limit, 1000))
        .offset(max(offset, 0))
    ).all())
    return rows, int(total)


def get_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
) -> PurchaseOrder:
    """Load a PO with lines for response. Raises PoNotFound on miss."""
    po = load_po_for_read(db, po_id, user, perms)
    # Force lines load (selectinload at query time would be slightly
    # cheaper but load_po_for_read uses db.get; one extra query here is
    # acceptable for the read path).
    _ = list(po.lines)
    return po


# ─────────────────────────────────────────────────────────────────────────
# Serialisation
# ─────────────────────────────────────────────────────────────────────────

# Fields gated behind `pos.view_sensitive` (pricing).
_HEADER_SENSITIVE: frozenset[str] = frozenset({
    "subtotal_amount", "vat_amount", "total_amount",
})

_LINE_SENSITIVE: frozenset[str] = frozenset({
    "unit_rate", "net_amount", "vat_amount", "gross_amount",
})


def _ser_line(line: PurchaseOrderLine, *, include_sensitive: bool) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": str(line.id),
        "budget_line_id": str(line.budget_line_id),
        "cost_code": line.cost_code,
        "line_number": int(line.line_number),
        "description": line.description,
        "quantity": str(line.quantity),
        "unit": line.unit,
        "vat_rate": str(line.vat_rate),
        "receipted_quantity": str(line.receipted_quantity),
        "is_fully_receipted": bool(line.is_fully_receipted),
        "notes": line.notes,
    }
    if include_sensitive:
        base.update({
            "unit_rate": str(line.unit_rate),
            "net_amount": str(line.net_amount),
            "vat_amount": str(line.vat_amount),
            "gross_amount": str(line.gross_amount),
        })
    else:
        for k in _LINE_SENSITIVE:
            base[k] = None
    return base


def serialise(
    po: PurchaseOrder, *, include_sensitive: bool,
) -> dict[str, Any]:
    """JSON-safe header + lines projection."""
    base: dict[str, Any] = {
        "id": str(po.id),
        "tenant_id": str(po.tenant_id),
        "project_id": str(po.project_id),
        "po_number": po.po_number,
        "po_number_prefix_id": (
            str(po.po_number_prefix_id)
            if po.po_number_prefix_id is not None else None
        ),
        "po_sequence": po.po_sequence,
        "supplier_id": str(po.supplier_id),
        "budget_id": str(po.budget_id),
        # Pack 3.5 — bidirectional package link (NULL on standalone POs).
        "package_id": (
            str(po.package_id) if po.package_id is not None else None
        ),
        "status": po.status,
        "issue_date": (
            po.issue_date.isoformat() if po.issue_date else None
        ),
        "required_by_date": (
            po.required_by_date.isoformat() if po.required_by_date else None
        ),
        "delivery_address": po.delivery_address,
        "delivery_notes": po.delivery_notes,
        "currency": po.currency,
        "approval_required": bool(po.approval_required),
        "approval_reason": po.approval_reason,
        "external_reference": po.external_reference,
        "notes": po.notes,
        "submitted_at": po.submitted_at.isoformat() if po.submitted_at else None,
        "submitted_by": str(po.submitted_by) if po.submitted_by else None,
        "approved_at": po.approved_at.isoformat() if po.approved_at else None,
        "approved_by": str(po.approved_by) if po.approved_by else None,
        "issued_at": po.issued_at.isoformat() if po.issued_at else None,
        "issued_by": str(po.issued_by) if po.issued_by else None,
        "closed_at": po.closed_at.isoformat() if po.closed_at else None,
        "closed_by": str(po.closed_by) if po.closed_by else None,
        "closed_reason": po.closed_reason,
        "voided_at": po.voided_at.isoformat() if po.voided_at else None,
        "voided_by": str(po.voided_by) if po.voided_by else None,
        "voided_reason": po.voided_reason,
        "created_at": po.created_at.isoformat() if po.created_at else None,
        "updated_at": po.updated_at.isoformat() if po.updated_at else None,
        "lines": [
            _ser_line(line, include_sensitive=include_sensitive)
            for line in sorted(po.lines, key=lambda ln: ln.line_number)
        ],
    }
    if include_sensitive:
        base["subtotal_amount"] = str(po.subtotal_amount)
        base["vat_amount"] = str(po.vat_amount)
        base["total_amount"] = str(po.total_amount)
    else:
        for k in _HEADER_SENSITIVE:
            base[k] = None
    # Edit tier surfaced in every response so UI can adapt without
    # re-deriving it from `status`.
    base["edit_tier"] = edit_tier_for(po).value
    return base
