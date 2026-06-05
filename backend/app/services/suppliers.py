"""Suppliers service — tenant-scoped CRUD + archive lifecycle.

Chat 24 §R1 (Prompt 2.5) — initial supplier directory.
Chat 32 §R3 (Prompt 2.7) — subcontractor + CIS extension.
Chat 41 §R3.2 (Prompt 2.7-BE-rev-A) — Contact-Book rework:
  - `cis_subtype` + `default_vat_rate` validators / writes removed.
  - `trade_id` / `trade` resolved via `_resolve_trade` + `_UNSET` sentinel
    (grow-as-you-type via `services.trades.get_or_create_trade`).
  - CIS gates key off `Contractor` (was `Subcontractor`); see services/cis
    + services/subcontracts.
Chat 41 §R-eyeball-Step2A (Prompt 2.7-FE-revision) — `vat_registered`
  dropped entirely. "Has a VAT number" is the de-facto registered signal
  and Xero owns VAT logic; no need for a standalone boolean. Removed
  from model, audit cols, create/update paths and the serialised shape.

Responsibility:
  - Validate uniqueness of supplier name (case-insensitive) within tenant.
  - Validate cis_status against the SUPPLIER_CIS_STATUSES tuple.
  - Honour the archive lifecycle:
      * archive: is_archived=true, archived_at=NOW, archived_by=user.
      * unarchive: is_archived=false, archived_at=NULL, archived_by=NULL.
  - Emit audit_log rows for every CUD with field-level diff.
  - Redaction of banking PII in audit_log is handled by the audit service
    (SENSITIVE_FIELDS list includes bank_*).

The service is intentionally stateless — the router supplies the
authenticated user, tenant, and request for each call.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.suppliers import (
    Supplier, SUPPLIER_CIS_STATUSES, SUPPLIER_TYPES,
)
from app.services import trades as trades_svc
from app.services.audit import field_diff, record_audit


# Columns we snapshot for audit diffing.
_AUDIT_COLS: tuple[str, ...] = (
    "name", "trading_name",
    "contact_name", "contact_email", "contact_phone",
    "address_line1", "address_line2", "city", "postcode", "country",
    "vat_number", "company_number", "cis_status",
    "bank_name", "bank_account_no", "bank_sort_code",
    "payment_terms_days", "notes",
    "portal_enabled",
    "is_archived",
    # Chat 32 §R3 (Prompt 2.7) — subcontractor + CIS extension fields.
    # Chat 41 §R3.2 (Prompt 2.7-BE-rev-A) — `cis_subtype` + `default_vat_rate`
    # dropped; `trade_id` added.
    "supplier_type", "cis_registered", "utr", "current_cis_status",
    "trade_id",
)


# Sentinel used by `_resolve_trade` to distinguish "key absent in payload"
# (leave row.trade_id untouched on update) from "key present but null/empty"
# (clear row.trade_id to NULL). NEVER use this as a stored value.
class _Unset:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only.
        return "<_UNSET>"


_UNSET: Any = _Unset()


def _snapshot(s: Supplier) -> dict[str, Any]:
    """Return a dict snapshot of audit-tracked columns for field_diff."""
    out: dict[str, Any] = {}
    for col in _AUDIT_COLS:
        v = getattr(s, col)
        if isinstance(v, Decimal):
            v = str(v)
        out[col] = v
    return out


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_cis(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    if value not in SUPPLIER_CIS_STATUSES:
        raise ValueError(
            f"cis_status must be one of {SUPPLIER_CIS_STATUSES}, got {value!r}"
        )
    return value


def _validate_payment_terms(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"payment_terms_days not int: {e}") from e
    if n < 0:
        raise ValueError("payment_terms_days must be ≥ 0")
    return n


# ---------------------------------------------------------------------------
# Chat 32 §R3.1 (Prompt 2.7) — subcontractor field validators.
# Chat 41 §R3.2 — `cis_subtype` validator removed; `supplier_type` enum
# now carries the 4-value contact-type label.
# ---------------------------------------------------------------------------

def _validate_supplier_type(value: Any) -> str:
    if value is None or value == "":
        return "Supplier"
    if value not in SUPPLIER_TYPES:
        raise ValueError(
            f"supplier_type must be one of {SUPPLIER_TYPES}, got {value!r}"
        )
    return value


def _validate_utr(value: Any) -> Optional[str]:
    """UK UTR — strip whitespace, must be exactly 10 digits."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("utr must be a string")
    # Strip whitespace (leading/trailing AND internal spaces).
    cleaned = "".join(value.split())
    if not cleaned.isdigit() or len(cleaned) != 10:
        raise ValueError("utr must be exactly 10 digits")
    return cleaned


def _coerce_trade_id(value: Any) -> uuid.UUID:
    """Accept a UUID or a UUID-shaped string. Raise ValueError on bad input."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError) as e:
        raise ValueError(f"trade_id not a valid UUID: {value!r}") from e


def _resolve_trade(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    request: Optional[Request] = None,
) -> Any:
    """Resolve the trade reference on a supplier create/update payload.

    Returns one of:
      - a UUID (existing or newly-created trade id) → caller assigns it,
      - None → caller clears row.trade_id to NULL (explicit unset),
      - `_UNSET` → caller leaves row.trade_id untouched (key absent).

    Priority:
      1. `trade_id` (UUID) — if present and non-empty, validate the trade
         exists in the tenant. ValueError if not.
      2. `trade` (name string) — if present and non-empty, get-or-create.
      3. Either key present but explicitly null/empty → clear (None).
      4. Neither key present → `_UNSET` (no change).
    """
    has_id = "trade_id" in payload
    has_name = "trade" in payload
    if not has_id and not has_name:
        return _UNSET

    tid_raw = payload.get("trade_id") if has_id else None
    tname_raw = payload.get("trade") if has_name else None

    # If trade_id is provided and non-empty, it wins (explicit).
    if has_id and tid_raw not in (None, ""):
        tid = _coerce_trade_id(tid_raw)
        found = trades_svc.get_trade(db, tenant_id, tid)
        if found is None:
            raise ValueError(f"trade_id {tid} not found in tenant")
        return found.id

    # Else if a name is provided and non-empty, grow-as-you-type.
    if has_name and isinstance(tname_raw, str) and tname_raw.strip():
        trade = trades_svc.get_or_create_trade(
            db, tenant_id, user_id, tname_raw, request=request,
        )
        return trade.id

    # Either present but explicitly null/empty → clear.
    return None


def _name_collides(
    db: Session, tenant_id: uuid.UUID, name: str,
    *, exclude_id: Optional[uuid.UUID] = None,
) -> bool:
    """Return True iff a non-self supplier in this tenant already has this
    case-insensitive name (matches the ux_suppliers_tenant_name_ci index).
    """
    q = select(Supplier.id).where(
        Supplier.tenant_id == tenant_id,
        func.lower(Supplier.name) == name.lower(),
    )
    if exclude_id is not None:
        q = q.where(Supplier.id != exclude_id)
    return db.scalar(q) is not None


# ---------------------------------------------------------------------------
# CRUD entry points
# ---------------------------------------------------------------------------

def list_suppliers(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    q: Optional[str] = None,
    include_archived: bool = False,
    supplier_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Supplier], int]:
    """Tenant-scoped paginated list. Returns (rows, total_unpaged).

    `supplier_type` (Chat 41 §R4.2) accepts one of the 4 contact-type
    labels: Contractor / Supplier / Consultant / Other.
    """
    where = [Supplier.tenant_id == tenant_id]
    if not include_archived:
        where.append(Supplier.is_archived.is_(False))
    if q:
        like = f"%{q.lower()}%"
        where.append(or_(
            func.lower(Supplier.name).like(like),
            func.lower(func.coalesce(Supplier.trading_name, "")).like(like),
        ))
    if supplier_type is not None:
        # Validate against the app-level enum tuple (DB enum will also
        # reject, but we want a clean ValueError before hitting SQL).
        if supplier_type not in SUPPLIER_TYPES:
            raise ValueError(
                f"supplier_type must be one of {SUPPLIER_TYPES}, "
                f"got {supplier_type!r}"
            )
        where.append(Supplier.supplier_type == supplier_type)
    base = select(Supplier).where(and_(*where))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(db.scalars(
        base.order_by(Supplier.name.asc()).limit(limit).offset(offset)
    ).all())
    return rows, int(total)


def get_supplier(
    db: Session, tenant_id: uuid.UUID, supplier_id: uuid.UUID,
) -> Optional[Supplier]:
    return db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == tenant_id,
            Supplier.id == supplier_id,
        )
    )


def create_supplier(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    request: Optional[Request] = None,
) -> Supplier:
    """Create a new supplier row. Raises ValueError on validation failure."""
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    if len(name) > 200:
        raise ValueError("name must be ≤ 200 characters")
    if _name_collides(db, tenant_id, name):
        raise ValueError(f"Supplier name {name!r} already exists in this tenant")

    cis = _validate_cis(payload.get("cis_status"))
    terms = _validate_payment_terms(payload.get("payment_terms_days"))

    # Chat 41 §R3.2 — supplier_type now drives the CIS gate via "Contractor".
    stype = _validate_supplier_type(payload.get("supplier_type"))
    utr = _validate_utr(payload.get("utr"))
    cis_registered_raw = payload.get("cis_registered", False)
    cis_registered = bool(cis_registered_raw) if cis_registered_raw is not None else False
    # current_cis_status is service-maintained. NEW Contractor (CIS
    # subcontractor) rows default to 'Unverified'; other types stay NULL.
    current_cis_status = "Unverified" if stype == "Contractor" else None

    # Trade resolution — on create the _UNSET sentinel collapses to None.
    resolved_trade = _resolve_trade(
        db, tenant_id, user_id, payload, request=request,
    )
    trade_id = None if resolved_trade is _UNSET else resolved_trade

    row = Supplier(
        tenant_id=tenant_id,
        name=name,
        trading_name=payload.get("trading_name") or None,
        contact_name=payload.get("contact_name") or None,
        contact_email=payload.get("contact_email") or None,
        contact_phone=payload.get("contact_phone") or None,
        address_line1=payload.get("address_line1") or None,
        address_line2=payload.get("address_line2") or None,
        city=payload.get("city") or None,
        postcode=payload.get("postcode") or None,
        country=payload.get("country") or "United Kingdom",
        vat_number=payload.get("vat_number") or None,
        company_number=payload.get("company_number") or None,
        cis_status=cis,
        bank_name=payload.get("bank_name") or None,
        bank_account_no=payload.get("bank_account_no") or None,
        bank_sort_code=payload.get("bank_sort_code") or None,
        payment_terms_days=terms if terms is not None else 30,
        notes=payload.get("notes") or None,
        portal_enabled=False,
        is_archived=False,
        supplier_type=stype,
        cis_registered=cis_registered,
        utr=utr,
        current_cis_status=current_cis_status,
        trade_id=trade_id,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(row)
    db.flush()

    record_audit(
        db, action="Create",
        resource_type="supplier",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff({}, _snapshot(row)),
        metadata={"name": row.name},
        request=request,
    )
    return row


def update_supplier(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    supplier_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    allow_sensitive: bool,
    request: Optional[Request] = None,
) -> Supplier:
    """Partial update. Fields not in payload are left untouched.

    `allow_sensitive` controls whether the caller may modify the
    `vat_number`, `company_number`, `bank_*` columns. The router gates
    this on `suppliers.view_sensitive`; without it those keys (if
    present) are silently dropped.

    Raises:
        LookupError: supplier not found in this tenant.
        ValueError: validation failure (duplicate name, bad cis, etc.).
    """
    row = get_supplier(db, tenant_id, supplier_id)
    if row is None:
        raise LookupError(f"supplier {supplier_id} not found in tenant")

    before = _snapshot(row)

    if "name" in payload:
        name = (payload["name"] or "").strip()
        if not name:
            raise ValueError("name cannot be empty")
        if _name_collides(db, tenant_id, name, exclude_id=row.id):
            raise ValueError(
                f"Supplier name {name!r} already exists in this tenant"
            )
        row.name = name

    _safe_keys = (
        "trading_name", "contact_name", "contact_email", "contact_phone",
        "address_line1", "address_line2", "city", "postcode", "country",
        "notes",
    )
    for k in _safe_keys:
        if k in payload:
            setattr(row, k, payload[k] or None)

    if "cis_status" in payload:
        row.cis_status = _validate_cis(payload["cis_status"])

    # Chat 32 §R3.1 (Prompt 2.7) / Chat 41 §R3.2 — supplier_type updates.
    if "supplier_type" in payload:
        row.supplier_type = _validate_supplier_type(payload["supplier_type"])
    if "cis_registered" in payload:
        row.cis_registered = bool(payload["cis_registered"])
    if "utr" in payload:
        row.utr = _validate_utr(payload["utr"])
    # current_cis_status is NOT settable via update payload — it is
    # owned by services/cis.record_verification() exclusively. Silently
    # ignore the key if a client tries to set it.

    if "payment_terms_days" in payload:
        row.payment_terms_days = _validate_payment_terms(
            payload["payment_terms_days"]
        )

    # Trade resolution. Use the _UNSET sentinel to distinguish "key
    # absent" (leave untouched) from "explicitly null/empty" (clear).
    resolved_trade = _resolve_trade(
        db, tenant_id, user_id, payload, request=request,
    )
    if resolved_trade is not _UNSET:
        row.trade_id = resolved_trade

    if allow_sensitive:
        _sensitive_keys = (
            "vat_number", "company_number",
            "bank_name", "bank_account_no", "bank_sort_code",
        )
        for k in _sensitive_keys:
            if k in payload:
                setattr(row, k, payload[k] or None)

    row.updated_by = user_id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    after = _snapshot(row)
    changes = field_diff(before, after)
    if changes:
        record_audit(
            db, action="Update",
            resource_type="supplier",
            resource_id=row.id,
            actor_user_id=user_id,
            field_changes=changes,
            metadata={"name": row.name},
            request=request,
        )
    return row


def set_archived(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    supplier_id: uuid.UUID,
    *,
    archived: bool,
    request: Optional[Request] = None,
) -> Supplier:
    """Toggle the archive flag. Idempotent — no audit row if no change.

    Raises:
        LookupError: supplier not found.
    """
    row = get_supplier(db, tenant_id, supplier_id)
    if row is None:
        raise LookupError(f"supplier {supplier_id} not found in tenant")

    if row.is_archived == archived:
        return row  # no-op

    before = _snapshot(row)
    row.is_archived = archived
    if archived:
        row.archived_at = datetime.now(timezone.utc)
        row.archived_by = user_id
    else:
        row.archived_at = None
        row.archived_by = None
    row.updated_by = user_id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    after = _snapshot(row)
    record_audit(
        db,
        action="Archive" if archived else "Restore",
        resource_type="supplier",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff(before, after),
        metadata={"name": row.name},
        request=request,
    )
    return row


# ---------------------------------------------------------------------------
# Hard delete — Chat 41 §R-eyeball-2 (Prompt 2.7-FE-revision)
# ---------------------------------------------------------------------------

class SupplierHasLinkedRecords(Exception):
    """Raised when a hard delete is attempted but the supplier still has
    linked rows. Carries a `kinds` list describing which relations
    blocked (purchase_orders, actuals, subcontracts, cis_verifications,
    supplier_documents) so the router can surface a helpful 409 message.
    """
    def __init__(self, kinds: list[str]):
        self.kinds = kinds
        super().__init__(", ".join(kinds))


# (table, supplier_fk_column, label) triples that block a hard delete.
# Listed as raw SQL so we don't have to import every linked model —
# and so future tables that grow a supplier FK are obvious in one place.
# CIS verif's and supplier_documents have CASCADE FKs but we still 409
# on them so operators don't surprise-cascade audit-bearing data.
_LINKED_RECORD_TABLES: tuple[tuple[str, str, str], ...] = (
    ("purchase_orders",                "supplier_id",      "purchase_orders"),
    ("actuals",                        "supplier_id",      "actuals"),
    # subcontracts use `subcontractor_id` for the supplier FK.
    ("subcontracts",                   "subcontractor_id", "subcontracts"),
    ("subcontractor_cis_verifications","supplier_id",      "cis_verifications"),
    ("supplier_documents",             "supplier_id",      "supplier_documents"),
)


def delete_supplier(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    supplier_id: uuid.UUID,
    *,
    request: Optional[Request] = None,
) -> dict[str, Any]:
    """Hard-delete a supplier IFF no linked records exist.

    Raises:
        LookupError: supplier not found.
        SupplierHasLinkedRecords: at least one linked row exists; carries
            the list of relation kinds so the router can 409 with detail.

    Returns:
        A `{"id": "<uuid>", "name": "<...>"}` dict for audit confirmation.
    """
    from sqlalchemy import text

    row = get_supplier(db, tenant_id, supplier_id)
    if row is None:
        raise LookupError(f"supplier {supplier_id} not found in tenant")

    found: list[str] = []
    for table, fk, label in _LINKED_RECORD_TABLES:
        exists = db.execute(
            text(f"SELECT 1 FROM {table} WHERE {fk} = :sid LIMIT 1"),
            {"sid": str(supplier_id)},
        ).first()
        if exists:
            found.append(label)
    if found:
        raise SupplierHasLinkedRecords(found)

    before = _snapshot(row)
    snapshot_name = row.name

    # Record the audit row BEFORE the DELETE so the FK on the supplier row
    # we're deleting doesn't fire. The audit table uses resource_id +
    # resource_type strings (no FK back to suppliers), so this is safe.
    record_audit(
        db,
        action="Delete",
        resource_type="supplier",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff(before, {}),
        metadata={"name": snapshot_name},
        request=request,
    )
    db.delete(row)
    db.flush()
    return {"id": str(supplier_id), "name": snapshot_name}


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

# Fields that require `suppliers.view_sensitive` to be returned to the
# client. The router applies this filter when projecting to the response
# schema.
SENSITIVE_RESPONSE_FIELDS: frozenset[str] = frozenset({
    "vat_number",
    "company_number",
    "bank_name",
    "bank_account_no",
    "bank_sort_code",
    # Chat 32 §R4.1 (Prompt 2.7) — UTR is sensitive PII for sole traders.
    "utr",
})


def serialise(
    row: Supplier, *, include_sensitive: bool,
) -> dict[str, Any]:
    """Convert a Supplier ORM row to a JSON-safe dict for response payloads."""
    base: dict[str, Any] = {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "name": row.name,
        "trading_name": row.trading_name,
        "contact_name": row.contact_name,
        "contact_email": row.contact_email,
        "contact_phone": row.contact_phone,
        "address_line1": row.address_line1,
        "address_line2": row.address_line2,
        "city": row.city,
        "postcode": row.postcode,
        "country": row.country,
        "cis_status": row.cis_status,
        "payment_terms_days": row.payment_terms_days,
        "notes": row.notes,
        "portal_enabled": bool(row.portal_enabled),
        "is_archived": bool(row.is_archived),
        "archived_at": (
            row.archived_at.isoformat() if row.archived_at is not None else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        # Chat 32 §R4.1 / Chat 41 §R3.2 — contact-type + CIS surface.
        "supplier_type": row.supplier_type,
        "cis_registered": bool(row.cis_registered),
        "current_cis_status": row.current_cis_status,
        # Chat 41 §R3.2 — trade managed-vocabulary reference (joined
        # eagerly on read). `vat_registered` was added in 0040 and
        # removed in 0041 — Xero is the source of truth for VAT.
        "trade_id": str(row.trade_id) if row.trade_id else None,
        # Null-safe: row.trade is None when trade_id is NULL.
        "trade": row.trade.name if row.trade is not None else None,
    }
    if include_sensitive:
        base.update({
            "vat_number": row.vat_number,
            "company_number": row.company_number,
            "bank_name": row.bank_name,
            "bank_account_no": row.bank_account_no,
            "bank_sort_code": row.bank_sort_code,
            "utr": row.utr,
        })
    else:
        # Explicitly null-out sensitive keys so the response shape is
        # always deterministic — clients can rely on the keys being
        # present, just empty when ungranted.
        for k in SENSITIVE_RESPONSE_FIELDS:
            base[k] = None
    return base
