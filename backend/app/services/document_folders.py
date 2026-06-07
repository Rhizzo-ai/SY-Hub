"""Document folder engine service — Chat 45 §R2 (Build Pack 2.7-DOCS-BE).

Polymorphic logical folder tree. Mirrors services/supplier_documents.py
conventions 1:1:

  - `ValueError`   → router maps to 422.
  - `LookupError`  → router maps to 404.
  - `record_audit` AFTER `db.flush()`, never before.
  - Tenant-scoped queries throughout.

Audit action strings reused from `audit.AUDIT_ACTIONS` (no new strings):
  - Create  — folder creation.
  - Update  — folder rename / move (move metadata records the parent
              hop in `metadata.moved_from` / `metadata.moved_to`).
  - Archive / Restore — soft delete + unarchive.

Permission gates live in the router. Loop guard on `move_folder` walks
the new parent's ancestor chain (cheaper than walking descendants) and
rejects self / cycle moves with `ValueError`.

Storage stays physical-supplier-folder-only (rev-B layout
`Suppliers/{supplier_id}`). Logical folders are PURE METADATA — no
SharePoint folders are created when a logical folder is created.
Physical-storage path reorganisation is explicit out-of-scope (backlog).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document_folders import DocumentFolder, FOLDER_OWNER_TYPES
from app.models.supplier_documents import SupplierDocument
from app.models.suppliers import Supplier
from app.services.audit import field_diff, record_audit


_AUDIT_COLS: tuple[str, ...] = (
    "owner_type", "owner_id", "parent_id", "name", "is_archived",
)


def _snapshot(f: DocumentFolder) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in _AUDIT_COLS:
        val = getattr(f, col)
        if isinstance(val, uuid.UUID):
            val = str(val)
        out[col] = val
    return out


# ---------------------------------------------------------------------------
# Owner-existence guards
# ---------------------------------------------------------------------------

def _validate_owner_type(value: Any) -> str:
    if value not in FOLDER_OWNER_TYPES:
        raise ValueError(
            f"owner_type must be one of {FOLDER_OWNER_TYPES}, got {value!r}"
        )
    return value


def _verify_owner_exists(
    db: Session, tenant_id: uuid.UUID,
    owner_type: str, owner_id: uuid.UUID,
) -> None:
    """Validates owner row exists in tenant. Raises LookupError → 404."""
    if owner_type == "supplier":
        row = db.scalar(
            select(Supplier).where(
                Supplier.tenant_id == tenant_id,
                Supplier.id == owner_id,
            )
        )
        if row is None:
            raise LookupError(f"supplier {owner_id} not found in tenant")
        return
    # Defensive: should never reach this branch given FOLDER_OWNER_TYPES,
    # but keeps the helper safe for the eventual project/subcontract add.
    raise ValueError(f"owner_type {owner_type!r} not yet supported")


def _coerce_uuid(value: Any, *, field: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as e:
        raise ValueError(f"{field} not a uuid: {e}") from e


def _load_folder(
    db: Session, tenant_id: uuid.UUID, folder_id: uuid.UUID,
) -> DocumentFolder:
    row = db.scalar(
        select(DocumentFolder).where(
            DocumentFolder.tenant_id == tenant_id,
            DocumentFolder.id == folder_id,
        )
    )
    if row is None:
        raise LookupError(f"document_folder {folder_id} not found in tenant")
    return row


def get_folder(
    db: Session, tenant_id: uuid.UUID, folder_id: uuid.UUID,
) -> Optional[DocumentFolder]:
    return db.scalar(
        select(DocumentFolder).where(
            DocumentFolder.tenant_id == tenant_id,
            DocumentFolder.id == folder_id,
        )
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _name_clean(value: Any) -> str:
    if value is None:
        raise ValueError("name is required")
    if not isinstance(value, str):
        raise ValueError("name must be a string")
    name = value.strip()
    if not name:
        raise ValueError("name is required")
    if len(name) > 200:
        raise ValueError("name must be ≤ 200 characters")
    return name


def _file_counts_by_folder(
    db: Session, tenant_id: uuid.UUID,
    owner_type: str, owner_id: uuid.UUID,
) -> dict[uuid.UUID, int]:
    """Single grouped query — returns folder_id → live-doc-count map.

    Supplier-owned folders only; future owner types short-circuit to {}.
    """
    if owner_type != "supplier":
        return {}
    rows = db.execute(
        select(
            SupplierDocument.folder_id,
            func.count(SupplierDocument.id),
        ).where(
            SupplierDocument.tenant_id == tenant_id,
            SupplierDocument.supplier_id == owner_id,
            SupplierDocument.folder_id.is_not(None),
            SupplierDocument.is_archived.is_(False),
        ).group_by(SupplierDocument.folder_id)
    ).all()
    return {fid: int(n) for (fid, n) in rows}


# ---------------------------------------------------------------------------
# CRUD entry points
# ---------------------------------------------------------------------------

def create_folder(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    request: Optional[Request] = None,
) -> DocumentFolder:
    """Create a folder. Raises:

      ValueError:   owner_type unknown, name invalid, parent in different
                    owner, parent archived, sibling-name clash.
      LookupError:  owner or parent not found in tenant (router → 404).
    """
    owner_type = _validate_owner_type(payload.get("owner_type"))
    owner_id = _coerce_uuid(payload.get("owner_id"), field="owner_id")
    _verify_owner_exists(db, tenant_id, owner_type, owner_id)

    name = _name_clean(payload.get("name"))

    parent: Optional[DocumentFolder] = None
    parent_raw = payload.get("parent_id")
    if parent_raw not in (None, "", b""):
        parent_id = _coerce_uuid(parent_raw, field="parent_id")
        parent = _load_folder(db, tenant_id, parent_id)
        if parent.owner_type != owner_type or parent.owner_id != owner_id:
            raise ValueError("parent belongs to a different owner")
        if parent.is_archived:
            raise ValueError("parent folder is archived")

    row = DocumentFolder(
        tenant_id=tenant_id,
        owner_type=owner_type,
        owner_id=owner_id,
        parent_id=parent.id if parent else None,
        name=name,
        is_archived=False,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(row)
    # Use savepoint so an IntegrityError on the partial unique index
    # can be caught + re-raised cleanly without poisoning the session.
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as e:
        raise ValueError(
            f"a folder named {name!r} already exists here"
        ) from e

    record_audit(
        db, action="Create",
        resource_type="document_folder",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff({}, _snapshot(row)),
        metadata={
            "owner_type": owner_type,
            "owner_id": str(owner_id),
            "parent_id": str(parent.id) if parent else None,
            "name": name,
        },
        request=request,
    )
    return row


def list_folder_tree(
    db: Session,
    tenant_id: uuid.UUID,
    owner_type: str,
    owner_id: uuid.UUID,
    *,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Return the full folder tree for one owner as a list of root nodes.

    Each node is a serialised dict with a `children: [...]` list. File
    counts are computed in one grouped query (no N+1).
    """
    _validate_owner_type(owner_type)
    _verify_owner_exists(db, tenant_id, owner_type, owner_id)

    where = [
        DocumentFolder.tenant_id == tenant_id,
        DocumentFolder.owner_type == owner_type,
        DocumentFolder.owner_id == owner_id,
    ]
    if not include_archived:
        where.append(DocumentFolder.is_archived.is_(False))
    rows = list(db.scalars(
        select(DocumentFolder).where(and_(*where)).order_by(
            DocumentFolder.name.asc()
        )
    ).all())

    counts = _file_counts_by_folder(db, tenant_id, owner_type, owner_id)
    nodes: dict[uuid.UUID, dict[str, Any]] = {}
    for r in rows:
        node = serialise_folder(r, file_count=counts.get(r.id, 0))
        node["children"] = []
        nodes[r.id] = node

    roots: list[dict[str, Any]] = []
    for r in rows:
        node = nodes[r.id]
        if r.parent_id and r.parent_id in nodes:
            nodes[r.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def get_folder_detail(
    db: Session,
    tenant_id: uuid.UUID,
    folder_id: uuid.UUID,
) -> dict[str, Any]:
    """Return folder + immediate children + file_count."""
    row = _load_folder(db, tenant_id, folder_id)
    counts = _file_counts_by_folder(
        db, tenant_id, row.owner_type, row.owner_id,
    )
    children_rows = list(db.scalars(
        select(DocumentFolder).where(
            DocumentFolder.tenant_id == tenant_id,
            DocumentFolder.parent_id == row.id,
            DocumentFolder.is_archived.is_(False),
        ).order_by(DocumentFolder.name.asc())
    ).all())
    base = serialise_folder(row, file_count=counts.get(row.id, 0))
    base["children"] = [
        serialise_folder(c, file_count=counts.get(c.id, 0))
        for c in children_rows
    ]
    return base


def rename_folder(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    new_name: Any,
    *,
    request: Optional[Request] = None,
) -> DocumentFolder:
    row = _load_folder(db, tenant_id, folder_id)
    name = _name_clean(new_name)
    if row.name == name:
        return row
    before = _snapshot(row)
    row.name = name
    row.updated_by = user_id
    row.updated_at = datetime.now(timezone.utc)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as e:
        raise ValueError(
            f"a folder named {name!r} already exists here"
        ) from e
    after = _snapshot(row)
    record_audit(
        db, action="Update",
        resource_type="document_folder",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff(before, after),
        metadata={
            "owner_type": row.owner_type,
            "owner_id": str(row.owner_id),
        },
        request=request,
    )
    return row


def _is_ancestor(
    db: Session, tenant_id: uuid.UUID,
    candidate_id: uuid.UUID, of_folder_id: uuid.UUID,
) -> bool:
    """True if `candidate_id` appears in the ancestor chain of `of_folder_id`.

    Walks parent_id upwards; cheap because depth is usually small.
    Used for loop-guarding move_folder: a destination cannot be the
    folder itself OR any of its descendants. Equivalently, the folder
    must NOT be an ancestor of the destination.
    """
    cursor = of_folder_id
    seen: set[uuid.UUID] = set()
    while cursor is not None:
        if cursor in seen:
            # Defensive: corrupt cycle in data — bail out.
            return False
        seen.add(cursor)
        if cursor == candidate_id:
            return True
        row = db.scalar(
            select(DocumentFolder.parent_id).where(
                DocumentFolder.tenant_id == tenant_id,
                DocumentFolder.id == cursor,
            )
        )
        cursor = row
    return False


def move_folder(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    new_parent_id: Optional[uuid.UUID],
    *,
    request: Optional[Request] = None,
) -> DocumentFolder:
    """Move `folder_id` under `new_parent_id` (None = root).

    Raises ValueError on self/descendant moves, cross-owner targets,
    archived target, or sibling-name clash. Raises LookupError on
    missing rows.
    """
    row = _load_folder(db, tenant_id, folder_id)
    old_parent = row.parent_id

    new_parent: Optional[DocumentFolder] = None
    if new_parent_id is not None:
        new_parent = _load_folder(db, tenant_id, new_parent_id)
        if (
            new_parent.owner_type != row.owner_type
            or new_parent.owner_id != row.owner_id
        ):
            raise ValueError(
                "cannot move folder to a different owner"
            )
        if new_parent.is_archived:
            raise ValueError("destination folder is archived")
        # Loop guard: walk new_parent's ancestor chain. If `row.id`
        # appears anywhere in it (including new_parent itself), the
        # move would create a cycle.
        if _is_ancestor(db, tenant_id, row.id, new_parent.id):
            raise ValueError(
                "cannot move a folder into itself or one of its descendants"
            )

    if old_parent == (new_parent.id if new_parent else None):
        return row

    before = _snapshot(row)
    row.parent_id = new_parent.id if new_parent else None
    row.updated_by = user_id
    row.updated_at = datetime.now(timezone.utc)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as e:
        raise ValueError(
            f"a folder named {row.name!r} already exists in the destination"
        ) from e
    after = _snapshot(row)
    record_audit(
        db, action="Update",
        resource_type="document_folder",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff(before, after),
        metadata={
            "owner_type": row.owner_type,
            "owner_id": str(row.owner_id),
            "moved_from": str(old_parent) if old_parent else None,
            "moved_to": str(new_parent.id) if new_parent else None,
        },
        request=request,
    )
    return row


def _has_live_children(
    db: Session, tenant_id: uuid.UUID, folder_id: uuid.UUID,
) -> bool:
    """Any non-archived child folder under `folder_id`?"""
    return db.scalar(
        select(func.count(DocumentFolder.id)).where(
            DocumentFolder.tenant_id == tenant_id,
            DocumentFolder.parent_id == folder_id,
            DocumentFolder.is_archived.is_(False),
        )
    ) > 0


def _has_live_documents(
    db: Session, tenant_id: uuid.UUID, folder_id: uuid.UUID,
) -> bool:
    """Any non-archived supplier_documents row in `folder_id`?"""
    return db.scalar(
        select(func.count(SupplierDocument.id)).where(
            SupplierDocument.tenant_id == tenant_id,
            SupplierDocument.folder_id == folder_id,
            SupplierDocument.is_archived.is_(False),
        )
    ) > 0


def set_folder_archived(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    folder_id: uuid.UUID,
    *,
    archived: bool,
    request: Optional[Request] = None,
) -> DocumentFolder:
    """Idempotent archive/restore. Blocks archive when folder not empty;
    blocks restore when parent is archived.
    """
    row = _load_folder(db, tenant_id, folder_id)
    if row.is_archived == archived:
        return row

    if archived:
        if (
            _has_live_children(db, tenant_id, row.id)
            or _has_live_documents(db, tenant_id, row.id)
        ):
            raise ValueError(
                "folder is not empty: archive or move its contents first"
            )
    else:
        if row.parent_id is not None:
            parent = db.scalar(
                select(DocumentFolder).where(
                    DocumentFolder.tenant_id == tenant_id,
                    DocumentFolder.id == row.parent_id,
                )
            )
            if parent is not None and parent.is_archived:
                raise ValueError("parent folder is archived")

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
        resource_type="document_folder",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff(before, after),
        metadata={
            "owner_type": row.owner_type,
            "owner_id": str(row.owner_id),
        },
        request=request,
    )
    return row


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def serialise_folder(
    row: DocumentFolder, *, file_count: Optional[int] = None,
) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "owner_type": row.owner_type,
        "owner_id": str(row.owner_id),
        "parent_id": str(row.parent_id) if row.parent_id else None,
        "name": row.name,
        "is_archived": bool(row.is_archived),
        "archived_at": (
            row.archived_at.isoformat() if row.archived_at else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "file_count": file_count,
    }


# ---------------------------------------------------------------------------
# Permission helper — folder reads follow owner-surface view perms.
# Used by the router to gate GET tree + GET detail correctly across
# future owner types (project, subcontract) with zero endpoint change.
# ---------------------------------------------------------------------------

OWNER_VIEW_PERM: dict[str, str] = {
    "supplier": "supplier_documents.view",
}


def owner_view_perm(owner_type: str) -> str:
    """Resolve the view-permission code for a given owner_type.

    Used by the router for GET tree + GET detail endpoints. Future
    owner types (project, subcontract) extend this map — endpoints
    stay unchanged.

    Raises ValueError on unknown owner_type → router maps to 422.
    """
    try:
        return OWNER_VIEW_PERM[owner_type]
    except KeyError as e:
        raise ValueError(f"unknown owner_type {owner_type!r}") from e
