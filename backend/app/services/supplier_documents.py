"""Supplier compliance documents service — Chat 32 §R3.3 (Prompt 2.7).

Mirrors services/suppliers.py 1:1 conventions:
  - `ValueError` for validation failures.
  - `LookupError` for missing rows (router maps to 404).
  - `_snapshot(d)` + `record_audit(...)` for every CUD.
  - Tenant-scoped queries.

Expiry is STORED ONLY — no scanning, no flagging side-effects (LD2).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.supplier_documents import (
    SupplierDocument, SUPPLIER_DOC_TYPES,
)
from app.models.suppliers import Supplier
from app.services.audit import field_diff, record_audit


_AUDIT_COLS: tuple[str, ...] = (
    "supplier_id", "doc_type", "title", "file_ref",
    "issued_on", "expires_on", "notes", "is_archived",
)


def _snapshot(d: SupplierDocument) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in _AUDIT_COLS:
        val = getattr(d, col)
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        elif isinstance(val, uuid.UUID):
            val = str(val)
        out[col] = val
    return out


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _validate_doc_type(value: Any) -> str:
    if value not in SUPPLIER_DOC_TYPES:
        raise ValueError(
            f"doc_type must be one of {SUPPLIER_DOC_TYPES}, got {value!r}"
        )
    return value


def _coerce_date(value: Any, *, field: str) -> Optional[date]:
    if value is None or value == "":
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


# ---------------------------------------------------------------------------
# CRUD entry points
# ---------------------------------------------------------------------------

def list_documents(
    db: Session,
    tenant_id: uuid.UUID,
    supplier_id: uuid.UUID,
    *,
    include_archived: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[SupplierDocument], int]:
    """Tenant-scoped + supplier-scoped paginated list.

    Excludes archived rows by default. Raises `LookupError` if the
    supplier is not visible to this tenant.
    """
    _load_supplier(db, tenant_id, supplier_id)
    where = [
        SupplierDocument.tenant_id == tenant_id,
        SupplierDocument.supplier_id == supplier_id,
    ]
    if not include_archived:
        where.append(SupplierDocument.is_archived.is_(False))
    base = select(SupplierDocument).where(and_(*where))
    from sqlalchemy import func as _func
    total = db.scalar(select(_func.count()).select_from(base.subquery())) or 0
    rows = list(db.scalars(
        base.order_by(
            SupplierDocument.doc_type.asc(),
            SupplierDocument.created_at.desc(),
        ).limit(limit).offset(offset)
    ).all())
    return rows, int(total)


def get_document(
    db: Session, tenant_id: uuid.UUID, document_id: uuid.UUID,
) -> Optional[SupplierDocument]:
    return db.scalar(
        select(SupplierDocument).where(
            SupplierDocument.tenant_id == tenant_id,
            SupplierDocument.id == document_id,
        )
    )


def create_document(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    request: Optional[Request] = None,
) -> SupplierDocument:
    """Create a new supplier document. Raises:

        ValueError:  validation failure (missing supplier_id, bad
                     doc_type, malformed dates).
        LookupError: supplier not in this tenant.
    """
    supplier_id_raw = payload.get("supplier_id")
    if not supplier_id_raw:
        raise ValueError("supplier_id is required")
    try:
        supplier_id = uuid.UUID(str(supplier_id_raw))
    except (ValueError, TypeError) as e:
        raise ValueError(f"supplier_id not a uuid: {e}") from e
    # Verify tenant scope. Cross-tenant supplier → LookupError → router 404.
    _load_supplier(db, tenant_id, supplier_id)

    doc_type = _validate_doc_type(payload.get("doc_type"))
    title = (payload.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    if len(title) > 200:
        raise ValueError("title must be ≤ 200 characters")

    issued = _coerce_date(payload.get("issued_on"), field="issued_on")
    expires = _coerce_date(payload.get("expires_on"), field="expires_on")

    row = SupplierDocument(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        doc_type=doc_type,
        title=title,
        file_ref=(payload.get("file_ref") or None),
        issued_on=issued,
        expires_on=expires,
        notes=(payload.get("notes") or None),
        is_archived=False,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(row)
    db.flush()

    record_audit(
        db, action="Create",
        resource_type="supplier_document",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff({}, _snapshot(row)),
        metadata={
            "supplier_id": str(supplier_id),
            "doc_type": doc_type,
            "title": title,
        },
        request=request,
    )
    return row


def update_document(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    request: Optional[Request] = None,
) -> SupplierDocument:
    """Partial update. Raises:

        LookupError: document not found in tenant.
        ValueError:  validation failure.
    """
    row = get_document(db, tenant_id, document_id)
    if row is None:
        raise LookupError(f"supplier_document {document_id} not found in tenant")

    before = _snapshot(row)

    if "title" in payload:
        t = (payload["title"] or "").strip()
        if not t:
            raise ValueError("title cannot be empty")
        if len(t) > 200:
            raise ValueError("title must be ≤ 200 characters")
        row.title = t
    if "doc_type" in payload:
        row.doc_type = _validate_doc_type(payload["doc_type"])
    if "file_ref" in payload:
        row.file_ref = payload["file_ref"] or None
    if "issued_on" in payload:
        row.issued_on = _coerce_date(payload["issued_on"], field="issued_on")
    if "expires_on" in payload:
        row.expires_on = _coerce_date(payload["expires_on"], field="expires_on")
    if "notes" in payload:
        row.notes = payload["notes"] or None

    row.updated_by = user_id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    after = _snapshot(row)
    changes = field_diff(before, after)
    if changes:
        record_audit(
            db, action="Update",
            resource_type="supplier_document",
            resource_id=row.id,
            actor_user_id=user_id,
            field_changes=changes,
            metadata={
                "supplier_id": str(row.supplier_id),
                "doc_type": row.doc_type,
            },
            request=request,
        )
    return row


def set_archived(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    archived: bool,
    request: Optional[Request] = None,
) -> SupplierDocument:
    """Idempotent archive toggle. Raises `LookupError` on missing row."""
    row = get_document(db, tenant_id, document_id)
    if row is None:
        raise LookupError(f"supplier_document {document_id} not found in tenant")

    if row.is_archived == archived:
        return row

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
        resource_type="supplier_document",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff(before, after),
        metadata={
            "supplier_id": str(row.supplier_id),
            "doc_type": row.doc_type,
        },
        request=request,
    )
    return row


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

# Fields gated behind supplier_documents.view_sensitive.
SENSITIVE_RESPONSE_FIELDS: frozenset[str] = frozenset({
    "file_ref",
    "notes",
})


def serialise(
    row: SupplierDocument, *, include_sensitive: bool,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "supplier_id": str(row.supplier_id),
        "doc_type": row.doc_type,
        "title": row.title,
        "issued_on": row.issued_on.isoformat() if row.issued_on else None,
        "expires_on": row.expires_on.isoformat() if row.expires_on else None,
        "is_archived": bool(row.is_archived),
        "archived_at": (
            row.archived_at.isoformat() if row.archived_at else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if include_sensitive:
        base["file_ref"] = row.file_ref
        base["notes"] = row.notes
    else:
        for k in SENSITIVE_RESPONSE_FIELDS:
            base[k] = None
    return base
