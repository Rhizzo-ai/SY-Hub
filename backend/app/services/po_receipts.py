"""PO Receipts service — Chat 24 §R4 (Prompt 2.5).

Captures the physical delivery of goods/services against a PO. Money
movements (commitment / actuals) are **not** affected by receipts —
the commitment column on budget_lines is owned by the R3 status-change
trigger and remains stable across receipt CUD.

Lifecycle invariants
--------------------
- PO must be in 'issued' or 'partially_receipted' to accept a receipt.
- Each receipt line targets a single po_line_id of the parent PO.
- `cumulative receipted_quantity` per po_line MUST never exceed
  `quantity`. The DB enforces this via the existing 0030 CHECK
  (`receipted_quantity <= quantity`) — the service surfaces a 422 with
  code `po/receipt-exceeds-ordered` before hitting that wall.
- After receipt insert:
    * if every line on the PO is_fully_receipted → status -> 'receipted'
    * else → status -> 'partially_receipted'
- received_date may not be in the future.
- received_date older than 30 days requires `pos.edit_issued`.
- Photos are file metadata only (no global documents table exists).
  Caller passes `photos=[{file_path, file_type, file_size_bytes,
  original_filename, caption?}, ...]` — typically via a separate
  upload helper in the router.
- Edit/Delete a receipt requires `pos.edit_issued`. Delete walks the
  DB trigger (cascade delete of receipt_lines fires the recompute
  trigger) and may flip the PO status back from 'receipted' to
  'partially_receipted' or from 'partially_receipted' to 'issued' if
  no receipts remain.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.permissions import UserPermissions
from app.models.notifications import Notification
from app.models.po_receipts import (
    PurchaseOrderReceipt, PurchaseOrderReceiptLine, PurchaseOrderReceiptPhoto,
)
from app.models.purchase_orders import PurchaseOrder, PurchaseOrderLine
from app.models.user import User
from app.services.audit import field_diff, record_audit
from app.services.budgets_reconciliation import recompute_for_po
from app.services.po_authz import PoNotFound, load_po_for_write


class ReceiptError(Exception):
    """Service-level receipt violation. Carries an optional machine code
    so the router can render a structured 4xx response."""

    def __init__(self, message: str, *, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code


ELIGIBLE_RECEIPT_STATUSES = frozenset({"issued", "partially_receipted"})
BACKDATE_GRACE_DAYS = 30


# ──────────────────────────────────────────────────────────────────────────
# Snapshot helpers (audit diffs)
# ──────────────────────────────────────────────────────────────────────────

def _snap_receipt(r: PurchaseOrderReceipt) -> dict[str, Any]:
    return {
        "received_date": r.received_date.isoformat() if r.received_date else None,
        "received_by": str(r.received_by),
        "delivery_note_reference": r.delivery_note_reference,
        "notes": r.notes,
        "line_count": len(r.lines or []),
        "photo_count": len(r.photos or []),
    }


# ──────────────────────────────────────────────────────────────────────────
# Validation primitives
# ──────────────────────────────────────────────────────────────────────────

def _validate_received_date(
    received_date: date, *, perms: UserPermissions,
) -> None:
    today = datetime.now(timezone.utc).date()
    if received_date > today:
        raise ReceiptError(
            "received_date cannot be in the future",
            code="po/receipt-future-date",
        )
    if received_date < (today - timedelta(days=BACKDATE_GRACE_DAYS)):
        if not perms.has("pos.edit_issued"):
            raise ReceiptError(
                f"received_date older than {BACKDATE_GRACE_DAYS} days "
                "requires pos.edit_issued",
                code="po/receipt-backdate-forbidden",
            )


def _load_po_lines_for_update(
    db: Session, po: PurchaseOrder, po_line_ids: list[uuid.UUID],
) -> dict[uuid.UUID, PurchaseOrderLine]:
    """Lock the affected PO lines and return them keyed by id."""
    rows = db.scalars(
        select(PurchaseOrderLine)
        .where(
            PurchaseOrderLine.purchase_order_id == po.id,
            PurchaseOrderLine.id.in_(po_line_ids),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    found = {r.id: r for r in rows}
    missing = [str(i) for i in po_line_ids if i not in found]
    if missing:
        raise ReceiptError(
            f"po_line_id not on this PO: {missing[0]}",
            code="po/receipt-line-mismatch",
        )
    return found


def _normalise_qty(value: Any) -> Decimal:
    try:
        qty = Decimal(str(value))
    except Exception as e:
        raise ReceiptError(
            f"quantity_received must be a number, got {value!r}",
            code="po/receipt-bad-quantity",
        ) from e
    if qty <= 0:
        raise ReceiptError(
            "quantity_received must be > 0",
            code="po/receipt-bad-quantity",
        )
    return qty.quantize(Decimal("0.0001"))


def _check_cumulative_within_ordered(
    line: PurchaseOrderLine, new_qty: Decimal,
) -> None:
    remaining = Decimal(line.quantity) - Decimal(line.receipted_quantity)
    if new_qty > remaining:
        raise ReceiptError(
            f"receipt exceeds ordered: line {line.line_number} "
            f"has {remaining} remaining, requested {new_qty}",
            code="po/receipt-exceeds-ordered",
        )


# ──────────────────────────────────────────────────────────────────────────
# Status transition (driven by line is_fully_receipted)
# ──────────────────────────────────────────────────────────────────────────

def _recompute_po_status_after_receipt_change(
    db: Session, po: PurchaseOrder, *, actor_user_id: uuid.UUID,
) -> Optional[str]:
    """Recompute and persist the post-receipt PO status. Returns the
    new status when it changes, else None.

    Called after receipt INSERT (rolling forward) and after receipt
    DELETE (rolling back). The DB trigger has already updated each
    line's receipted_quantity by the time we run.

    `actor_user_id` is the receipting user (the caller of create_receipt
    or delete_receipt). It is recorded on the Status_Change audit row —
    using `po.updated_by` here previously misattributed the status flip
    to whoever last edited the PO header (P0.2 audit-trail correctness).

    All PO lines are taken under `SELECT ... FOR UPDATE` before the
    all-fully-received check so that two concurrent receipts on
    different lines serialise the status flip (no double-fire of the
    "everything received" transition).
    """
    db.flush()
    db.refresh(po)
    lines = db.scalars(
        select(PurchaseOrderLine)
        .where(PurchaseOrderLine.purchase_order_id == po.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    has_any_receipt = any(Decimal(l.receipted_quantity) > 0 for l in lines)
    all_fully = lines and all(l.is_fully_receipted for l in lines)

    if all_fully:
        target = "receipted"
    elif has_any_receipt:
        target = "partially_receipted"
    else:
        # All quantities rolled back to 0 — return PO to 'issued'.
        target = "issued"

    if po.status == target:
        return None

    prev = po.status
    po.status = target
    db.flush()
    recompute_for_po(db, po.id)
    record_audit(
        db, action="Status_Change",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=actor_user_id,
        project_id=po.project_id,
        field_changes=[{"field": "status", "old": prev, "new": target}],
        metadata={"reason": "receipt_change", "from": prev, "to": target},
    )
    return target


# ──────────────────────────────────────────────────────────────────────────
# Notifications
# ──────────────────────────────────────────────────────────────────────────

def _notify_status_flip(
    db: Session, *, po: PurchaseOrder, new_status: str, actor: User,
) -> None:
    if new_status == "partially_receipted":
        nt, title = (
            "po.partial_receipt",
            f"PO {po.po_number} partially receipted",
        )
    elif new_status == "receipted":
        nt, title = (
            "po.fully_receipted",
            f"PO {po.po_number} fully receipted",
        )
    else:
        return
    # Notify the PO creator (if not the actor) — keeps the loop simple
    # for R4. R5/R6 can broaden this.
    if po.created_by and po.created_by != actor.id:
        db.add(Notification(
            recipient_user_id=po.created_by,
            notification_type=nt,
            priority="Normal",
            title=title[:255],
            body=f"PO {po.po_number} status changed to {new_status}.",
            related_resource_type="purchase_order",
            related_resource_id=po.id,
            action_url=f"/purchase-orders/{po.id}",
            action_label="View PO",
        ))


# ──────────────────────────────────────────────────────────────────────────
# Create
# ──────────────────────────────────────────────────────────────────────────

def create_receipt(
    db: Session, *, user: User, perms: UserPermissions,
    po_id: uuid.UUID, payload: dict[str, Any],
    request: Optional[Request] = None,
) -> PurchaseOrderReceipt:
    """Create a receipt (header + lines + optional photos) atomically."""
    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    if po.status not in ELIGIBLE_RECEIPT_STATUSES:
        raise ReceiptError(
            f"PO must be in 'issued' or 'partially_receipted' to receipt; "
            f"current status: {po.status}",
            code="po/receipt-wrong-status",
        )

    # received_date
    rd_raw = payload.get("received_date")
    if rd_raw is None:
        raise ReceiptError(
            "received_date is required",
            code="po/receipt-missing-field",
        )
    received_date = (
        rd_raw if isinstance(rd_raw, date)
        else datetime.fromisoformat(str(rd_raw)).date()
    )
    _validate_received_date(received_date, perms=perms)

    # lines
    line_payloads = list(payload.get("lines") or [])
    if not line_payloads:
        raise ReceiptError(
            "At least one receipt line is required",
            code="po/receipt-missing-lines",
        )
    po_line_ids = [uuid.UUID(str(lp["po_line_id"])) for lp in line_payloads]
    lines_by_id = _load_po_lines_for_update(db, po, po_line_ids)

    # Aggregate per-line so we can validate cumulative correctly when
    # the same po_line appears twice in the same receipt.
    qty_by_line: dict[uuid.UUID, Decimal] = {}
    for lp in line_payloads:
        lid = uuid.UUID(str(lp["po_line_id"]))
        q = _normalise_qty(lp.get("quantity_received"))
        qty_by_line[lid] = qty_by_line.get(lid, Decimal("0")) + q
    for lid, q in qty_by_line.items():
        _check_cumulative_within_ordered(lines_by_id[lid], q)

    # photos (optional)
    photo_payloads = list(payload.get("photos") or [])

    # ─── Persist ─────────────────────────────────────────────────────────
    receipt = PurchaseOrderReceipt(
        tenant_id=user.tenant_id,
        purchase_order_id=po.id,
        received_date=received_date,
        received_by=user.id,
        delivery_note_reference=(
            str(payload.get("delivery_note_reference"))[:100]
            if payload.get("delivery_note_reference") else None
        ),
        notes=(payload.get("notes") or None),
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(receipt)
    db.flush()  # need receipt.id for line FK

    for lp in line_payloads:
        db.add(PurchaseOrderReceiptLine(
            receipt_id=receipt.id,
            po_line_id=uuid.UUID(str(lp["po_line_id"])),
            quantity_received=_normalise_qty(lp.get("quantity_received")),
        ))

    seen_paths: set[str] = set()
    for pp in photo_payloads:
        fp = str(pp.get("file_path") or "").strip()
        if not fp:
            raise ReceiptError(
                "photo file_path is required",
                code="po/receipt-photo-missing-path",
            )
        if fp in seen_paths:
            raise ReceiptError(
                f"duplicate photo file_path in payload: {fp}",
                code="po/receipt-photo-duplicate",
            )
        seen_paths.add(fp)
        size = int(pp.get("file_size_bytes") or 0)
        if size <= 0:
            raise ReceiptError(
                "photo file_size_bytes must be > 0",
                code="po/receipt-photo-bad-size",
            )
        db.add(PurchaseOrderReceiptPhoto(
            receipt_id=receipt.id,
            file_path=fp,
            file_type=str(pp.get("file_type") or "application/octet-stream")[:100],
            file_size_bytes=size,
            original_filename=str(pp.get("original_filename") or "receipt")[:500],
            caption=(str(pp.get("caption"))[:500] if pp.get("caption") else None),
            uploaded_by=user.id,
        ))
    try:
        db.flush()
    except IntegrityError as e:
        # DB-level guard for the CHECK (receipted_quantity <= quantity)
        # in case the service guard above missed a race.
        raise ReceiptError(
            "DB rejected receipt (exceeded ordered quantity or unique violation)",
            code="po/receipt-db-violation",
        ) from e

    # Trigger has now run — recompute and persist any status flip.
    new_status = _recompute_po_status_after_receipt_change(
        db, po, actor_user_id=user.id,
    )

    # Audit
    record_audit(
        db, action="Receipt",
        resource_type="purchase_order_receipt",
        resource_id=receipt.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff({}, _snap_receipt(receipt)),
        metadata={
            "po_id": str(po.id),
            "po_number": po.po_number,
            "line_count": len(line_payloads),
            "photo_count": len(photo_payloads),
            "po_status_after": po.status,
        },
        request=request,
    )

    if new_status in ("partially_receipted", "receipted"):
        _notify_status_flip(db, po=po, new_status=new_status, actor=user)

    db.refresh(receipt)
    return receipt


# ──────────────────────────────────────────────────────────────────────────
# Read
# ──────────────────────────────────────────────────────────────────────────

def list_receipts(
    db: Session, *, user: User, perms: UserPermissions,
    po_id: uuid.UUID,
) -> list[PurchaseOrderReceipt]:
    po = load_po_for_write(db, po_id, user, perms)  # read-shape, no lock
    return list(db.scalars(
        select(PurchaseOrderReceipt)
        .where(PurchaseOrderReceipt.purchase_order_id == po.id)
        .order_by(PurchaseOrderReceipt.received_date.desc(),
                  PurchaseOrderReceipt.created_at.desc())
    ).all())


def get_receipt(
    db: Session, *, user: User, perms: UserPermissions,
    receipt_id: uuid.UUID,
) -> PurchaseOrderReceipt:
    receipt = db.get(PurchaseOrderReceipt, receipt_id)
    if receipt is None or receipt.tenant_id != user.tenant_id:
        raise PoNotFound("Receipt not found")
    # Enforce tenant + visibility via the parent PO.
    load_po_for_write(db, receipt.purchase_order_id, user, perms)
    return receipt


# ──────────────────────────────────────────────────────────────────────────
# Update (header annotations only)
# ──────────────────────────────────────────────────────────────────────────

EDITABLE_HEADER_FIELDS = frozenset({
    "delivery_note_reference", "notes", "received_date",
})


def update_receipt(
    db: Session, *, user: User, perms: UserPermissions,
    receipt_id: uuid.UUID, payload: dict[str, Any],
    request: Optional[Request] = None,
) -> PurchaseOrderReceipt:
    """Annotate an existing receipt. Requires `pos.edit_issued`."""
    if not perms.has("pos.edit_issued"):
        raise ReceiptError(
            "Editing a receipt requires pos.edit_issued",
            code="po/receipt-edit-forbidden",
        )
    receipt = get_receipt(db, user=user, perms=perms, receipt_id=receipt_id)
    before = _snap_receipt(receipt)

    touched: dict[str, Any] = {}
    if "delivery_note_reference" in payload:
        v = payload["delivery_note_reference"]
        receipt.delivery_note_reference = (str(v)[:100] if v else None)
        touched["delivery_note_reference"] = receipt.delivery_note_reference
    if "notes" in payload:
        receipt.notes = (payload["notes"] or None)
        touched["notes"] = receipt.notes
    if "received_date" in payload:
        rd_raw = payload["received_date"]
        new_rd = (
            rd_raw if isinstance(rd_raw, date)
            else datetime.fromisoformat(str(rd_raw)).date()
        )
        _validate_received_date(new_rd, perms=perms)
        receipt.received_date = new_rd
        touched["received_date"] = new_rd.isoformat()

    if not touched:
        return receipt

    receipt.updated_by = user.id
    db.flush()
    record_audit(
        db, action="Update",
        resource_type="purchase_order_receipt",
        resource_id=receipt.id,
        actor_user_id=user.id,
        project_id=db.get(PurchaseOrder, receipt.purchase_order_id).project_id,
        field_changes=field_diff(before, _snap_receipt(receipt)),
        metadata={"po_id": str(receipt.purchase_order_id)},
        request=request,
    )
    db.refresh(receipt)
    return receipt


# ──────────────────────────────────────────────────────────────────────────
# Delete
# ──────────────────────────────────────────────────────────────────────────

def delete_receipt(
    db: Session, *, user: User, perms: UserPermissions,
    receipt_id: uuid.UUID,
    request: Optional[Request] = None,
) -> dict[str, Any]:
    """Delete a receipt + cascade its lines/photos. Director-tier only."""
    if not perms.has("pos.edit_issued"):
        raise ReceiptError(
            "Deleting a receipt requires pos.edit_issued",
            code="po/receipt-delete-forbidden",
        )
    receipt = get_receipt(db, user=user, perms=perms, receipt_id=receipt_id)
    before = _snap_receipt(receipt)
    po = db.get(PurchaseOrder, receipt.purchase_order_id)

    record_audit(
        db, action="Delete",
        resource_type="purchase_order_receipt",
        resource_id=receipt.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, {}),
        metadata={
            "po_id": str(po.id), "po_number": po.po_number,
            "received_date": before["received_date"],
        },
        request=request,
    )
    db.delete(receipt)
    db.flush()  # cascades lines → recompute trigger fires

    new_status = _recompute_po_status_after_receipt_change(
        db, po, actor_user_id=user.id,
    )
    return {
        "deleted_id": str(receipt_id),
        "po_status_after": po.status,
        "status_changed_to": new_status,
    }


# ──────────────────────────────────────────────────────────────────────────
# Serialisation
# ──────────────────────────────────────────────────────────────────────────

def serialise(receipt: PurchaseOrderReceipt) -> dict[str, Any]:
    return {
        "id": str(receipt.id),
        "tenant_id": str(receipt.tenant_id),
        "purchase_order_id": str(receipt.purchase_order_id),
        "received_date": receipt.received_date.isoformat(),
        "received_by": str(receipt.received_by),
        "delivery_note_reference": receipt.delivery_note_reference,
        "notes": receipt.notes,
        "created_at": receipt.created_at.isoformat() if receipt.created_at else None,
        "created_by": str(receipt.created_by),
        "updated_at": receipt.updated_at.isoformat() if receipt.updated_at else None,
        "updated_by": str(receipt.updated_by),
        "lines": [
            {
                "id": str(l.id),
                "po_line_id": str(l.po_line_id),
                "quantity_received": str(l.quantity_received),
            }
            for l in (receipt.lines or [])
        ],
        "photos": [
            {
                "id": str(p.id),
                "file_path": p.file_path,
                "file_type": p.file_type,
                "file_size_bytes": int(p.file_size_bytes),
                "original_filename": p.original_filename,
                "caption": p.caption,
                "uploaded_by": str(p.uploaded_by),
                "uploaded_at": p.uploaded_at.isoformat() if p.uploaded_at else None,
            }
            for p in (receipt.photos or [])
        ],
    }
