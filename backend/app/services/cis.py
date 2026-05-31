"""CIS verifications service — Chat 32 §R3.2 (Prompt 2.7).

Records HMRC CIS verifications for subcontractor suppliers. Verifications
are APPEND-ONLY — corrections create a new row, never UPDATE/DELETE.

The denormalised `suppliers.current_cis_status` cache is repointed by
this module on every successful insert. No other code path may write
that field.

Conventions:
  - `ValueError` for validation failures.
  - `LookupError` for missing supplier (router maps to 404).
  - `_snapshot(s)` + `record_audit(...)` mirrors services/suppliers.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cis import (
    SubcontractorCISVerification, CIS_MATCH_STATUSES,
)
from app.models.suppliers import Supplier
from app.services.audit import field_diff, record_audit


# Columns we snapshot for audit diffing on the verification row itself.
_AUDIT_COLS: tuple[str, ...] = (
    "supplier_id", "verification_number", "match_status",
    "tax_rate_pct", "verified_on", "expires_on", "notes",
)


def _snapshot(v: SubcontractorCISVerification) -> dict[str, Any]:
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
# Validators
# ---------------------------------------------------------------------------

def _validate_match_status(value: Any) -> str:
    if value not in CIS_MATCH_STATUSES:
        raise ValueError(
            f"match_status must be one of {CIS_MATCH_STATUSES}, "
            f"got {value!r}"
        )
    return value


def _coerce_tax_rate(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"tax_rate_pct not numeric: {e}") from e
    if d < 0 or d > 100:
        raise ValueError("tax_rate_pct must be between 0 and 100")
    return d


def _coerce_date(value: Any, *, field: str, required: bool) -> Optional[date]:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field} is required")
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as e:
            raise ValueError(f"{field} not ISO date: {e}") from e
    raise ValueError(f"{field} not a date: {value!r}")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _load_supplier(
    db: Session, tenant_id: uuid.UUID, supplier_id: uuid.UUID,
) -> Supplier:
    s = db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == tenant_id,
            Supplier.id == supplier_id,
        )
    )
    if s is None:
        raise LookupError(f"supplier {supplier_id} not found in tenant")
    return s


def list_verifications(
    db: Session, tenant_id: uuid.UUID, supplier_id: uuid.UUID,
) -> list[SubcontractorCISVerification]:
    """Newest first by `verified_on`, tie-break by `created_at`.

    Raises `LookupError` if the supplier is not visible to this tenant.
    """
    _load_supplier(db, tenant_id, supplier_id)
    return list(db.scalars(
        select(SubcontractorCISVerification).where(
            SubcontractorCISVerification.tenant_id == tenant_id,
            SubcontractorCISVerification.supplier_id == supplier_id,
        ).order_by(
            SubcontractorCISVerification.verified_on.desc(),
            SubcontractorCISVerification.created_at.desc(),
        )
    ).all())


def get_current_verification(
    db: Session, tenant_id: uuid.UUID, supplier_id: uuid.UUID,
) -> Optional[SubcontractorCISVerification]:
    """Latest verification by `verified_on`, or None.

    Raises `LookupError` if the supplier is not visible to this tenant.
    """
    _load_supplier(db, tenant_id, supplier_id)
    return db.scalar(
        select(SubcontractorCISVerification).where(
            SubcontractorCISVerification.tenant_id == tenant_id,
            SubcontractorCISVerification.supplier_id == supplier_id,
        ).order_by(
            SubcontractorCISVerification.verified_on.desc(),
            SubcontractorCISVerification.created_at.desc(),
        ).limit(1)
    )


# ---------------------------------------------------------------------------
# Writes — append-only
# ---------------------------------------------------------------------------

def record_verification(
    db: Session,
    tenant_id: uuid.UUID,
    supplier_id: uuid.UUID,
    *,
    verification_number: Optional[str],
    match_status: str,
    tax_rate_pct: Any,
    verified_on: Any,
    expires_on: Any,
    notes: Optional[str],
    actor_id: uuid.UUID,
    request: Optional[Request] = None,
) -> SubcontractorCISVerification:
    """Append a new verification row and update the cached
    `supplier.current_cis_status`.

    Raises:
        LookupError: supplier not found in this tenant.
        ValueError:  validation failure (wrong supplier_type, bad
                     match_status, bad tax_rate, bad dates).
    """
    supplier = _load_supplier(db, tenant_id, supplier_id)
    if supplier.supplier_type != "Subcontractor":
        raise ValueError(
            "CIS verification only valid for subcontractors"
        )

    ms = _validate_match_status(match_status)
    rate = _coerce_tax_rate(tax_rate_pct)
    vdate = _coerce_date(verified_on, field="verified_on", required=True)
    edate = _coerce_date(expires_on, field="expires_on", required=False)

    row = SubcontractorCISVerification(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        verification_number=(verification_number or None),
        match_status=ms,
        tax_rate_pct=rate,
        verified_on=vdate,
        expires_on=edate,
        notes=(notes or None),
        created_by=actor_id,
    )
    db.add(row)
    db.flush()

    # Repoint denormalised cache. This is the ONLY writer of this field.
    supplier.current_cis_status = ms
    supplier.updated_by = actor_id
    supplier.updated_at = datetime.now(timezone.utc)
    db.flush()

    record_audit(
        db, action="Create",
        resource_type="cis_verification",
        resource_id=row.id,
        actor_user_id=actor_id,
        field_changes=field_diff({}, _snapshot(row)),
        metadata={
            "supplier_id": str(supplier_id),
            "match_status": ms,
        },
        request=request,
    )
    return row


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

# Fields gated behind cis.view_sensitive (per Build Pack §R4.2 test #17).
SENSITIVE_RESPONSE_FIELDS: frozenset[str] = frozenset({
    "verification_number",
})


def serialise(
    row: SubcontractorCISVerification, *, include_sensitive: bool,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "supplier_id": str(row.supplier_id),
        "match_status": row.match_status,
        "tax_rate_pct": (
            str(row.tax_rate_pct) if row.tax_rate_pct is not None else None
        ),
        "verified_on": row.verified_on.isoformat() if row.verified_on else None,
        "expires_on": row.expires_on.isoformat() if row.expires_on else None,
        "notes": row.notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "created_by": str(row.created_by) if row.created_by else None,
    }
    if include_sensitive:
        base["verification_number"] = row.verification_number
    else:
        base["verification_number"] = None
    return base
