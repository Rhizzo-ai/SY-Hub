"""Suppliers service — tenant-scoped CRUD + archive lifecycle.

Chat 24 §R1 (Prompt 2.5).

Responsibility:
  - Validate uniqueness of supplier name (case-insensitive) within tenant.
  - Validate cis_status against the SUPPLIER_CIS_STATUSES tuple.
  - Validate default_vat_rate ∈ [0, 100].
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
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from fastapi import Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.suppliers import Supplier, SUPPLIER_CIS_STATUSES
from app.services.audit import field_diff, record_audit


# Columns we snapshot for audit diffing.
_AUDIT_COLS: tuple[str, ...] = (
    "name", "trading_name",
    "contact_name", "contact_email", "contact_phone",
    "address_line1", "address_line2", "city", "postcode", "country",
    "vat_number", "company_number", "cis_status",
    "bank_name", "bank_account_no", "bank_sort_code",
    "payment_terms_days", "default_vat_rate", "notes",
    "portal_enabled",
    "is_archived",
)


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

def _coerce_vat_rate(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"default_vat_rate not numeric: {e}") from e
    if d < 0 or d > 100:
        raise ValueError("default_vat_rate must be between 0 and 100")
    return d


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
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Supplier], int]:
    """Tenant-scoped paginated list. Returns (rows, total_unpaged)."""
    where = [Supplier.tenant_id == tenant_id]
    if not include_archived:
        where.append(Supplier.is_archived.is_(False))
    if q:
        like = f"%{q.lower()}%"
        where.append(or_(
            func.lower(Supplier.name).like(like),
            func.lower(func.coalesce(Supplier.trading_name, "")).like(like),
        ))
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
    vat = _coerce_vat_rate(payload.get("default_vat_rate"))
    terms = _validate_payment_terms(payload.get("payment_terms_days"))

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
        default_vat_rate=vat if vat is not None else Decimal("20.00"),
        notes=payload.get("notes") or None,
        portal_enabled=False,
        is_archived=False,
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

    if "default_vat_rate" in payload:
        row.default_vat_rate = _coerce_vat_rate(payload["default_vat_rate"])

    if "payment_terms_days" in payload:
        row.payment_terms_days = _validate_payment_terms(
            payload["payment_terms_days"]
        )

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
        "default_vat_rate": (
            str(row.default_vat_rate) if row.default_vat_rate is not None else None
        ),
        "notes": row.notes,
        "portal_enabled": bool(row.portal_enabled),
        "is_archived": bool(row.is_archived),
        "archived_at": (
            row.archived_at.isoformat() if row.archived_at is not None else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if include_sensitive:
        base.update({
            "vat_number": row.vat_number,
            "company_number": row.company_number,
            "bank_name": row.bank_name,
            "bank_account_no": row.bank_account_no,
            "bank_sort_code": row.bank_sort_code,
        })
    else:
        # Explicitly null-out sensitive keys so the response shape is
        # always deterministic — clients can rely on the keys being
        # present, just empty when ungranted.
        for k in SENSITIVE_RESPONSE_FIELDS:
            base[k] = None
    return base
