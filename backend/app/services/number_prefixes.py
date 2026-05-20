"""Project number prefixes service — per-project, per-entity-type numbering.

Chat 24 §R1 (Prompt 2.5).

Responsibility for R1 (read + CRUD only — sequence allocation lives in
po_numbering, added in R2):
  - Validate the middle_prefix shape (1-8 chars, A-Z/0-9/dash, no
    leading/trailing dash). The DB CHECK is the ultimate enforcer; we
    pre-validate here for nice error messages.
  - Validate uniqueness within (project_id, entity_type, middle_prefix).
  - Enforce single-default invariant at the service layer too (the DB
    trigger demotes others; we surface that as a friendly description
    in the response).
  - Seed a null-middle is_default=true row for each entity_type on
    project create (helper `seed_default_prefixes`).
  - Emit audit_log rows for every CUD.

Sequence allocation (`next_sequence` increment with row-level lock) is
NOT in R1 — see app/services/po_numbering.py once R2 lands.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from fastapi import Request
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.number_prefixes import (
    ProjectNumberPrefix, PREFIX_ENTITY_TYPES,
)
from app.services.audit import field_diff, record_audit


_MIDDLE_RE = re.compile(r"^[A-Z0-9](?:[A-Z0-9-]{0,6}[A-Z0-9])?$")

_AUDIT_COLS: tuple[str, ...] = (
    "entity_type", "middle_prefix", "description",
    "is_default", "is_archived", "next_sequence",
)


def _snapshot(p: ProjectNumberPrefix) -> dict[str, Any]:
    return {col: getattr(p, col) for col in _AUDIT_COLS}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _normalise_middle(value: Any) -> Optional[str]:
    """Strip + uppercase, return None for empty. Does NOT validate shape."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    return s.upper()


def _validate_middle_shape(value: Optional[str]) -> None:
    if value is None:
        return
    if len(value) > 8:
        raise ValueError("middle_prefix must be ≤ 8 characters")
    if not _MIDDLE_RE.match(value):
        raise ValueError(
            "middle_prefix shape invalid — allowed: A-Z, 0-9, dash; "
            "no leading or trailing dash; 1-8 chars"
        )


def _validate_entity_type(value: Optional[str]) -> str:
    if value not in PREFIX_ENTITY_TYPES:
        raise ValueError(
            f"entity_type must be one of {PREFIX_ENTITY_TYPES}, got {value!r}"
        )
    return value


def _middle_collides(
    db: Session,
    project_id: uuid.UUID,
    entity_type: str,
    middle: Optional[str],
    *,
    exclude_id: Optional[uuid.UUID] = None,
) -> bool:
    """True iff another prefix row exists with same (project, entity_type, middle).

    NULL middles compare equal — there can only ever be one null-middle per
    (project, entity_type).
    """
    where = [
        ProjectNumberPrefix.project_id == project_id,
        ProjectNumberPrefix.entity_type == entity_type,
    ]
    if middle is None:
        where.append(ProjectNumberPrefix.middle_prefix.is_(None))
    else:
        where.append(ProjectNumberPrefix.middle_prefix == middle)
    if exclude_id is not None:
        where.append(ProjectNumberPrefix.id != exclude_id)
    return db.scalar(
        select(ProjectNumberPrefix.id).where(*where)
    ) is not None


# ---------------------------------------------------------------------------
# CRUD entry points
# ---------------------------------------------------------------------------

def list_prefixes(
    db: Session,
    project_id: uuid.UUID,
    *,
    entity_type: Optional[str] = None,
    include_archived: bool = False,
) -> list[ProjectNumberPrefix]:
    where = [ProjectNumberPrefix.project_id == project_id]
    if entity_type is not None:
        where.append(ProjectNumberPrefix.entity_type == entity_type)
    if not include_archived:
        where.append(ProjectNumberPrefix.is_archived.is_(False))
    return list(db.scalars(
        select(ProjectNumberPrefix)
        .where(and_(*where))
        .order_by(
            ProjectNumberPrefix.entity_type.asc(),
            ProjectNumberPrefix.is_default.desc(),
            ProjectNumberPrefix.middle_prefix.asc().nulls_first(),
        )
    ).all())


def get_prefix(
    db: Session, project_id: uuid.UUID, prefix_id: uuid.UUID,
) -> Optional[ProjectNumberPrefix]:
    return db.scalar(
        select(ProjectNumberPrefix).where(
            ProjectNumberPrefix.id == prefix_id,
            ProjectNumberPrefix.project_id == project_id,
        )
    )


def create_prefix(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    request: Optional[Request] = None,
) -> ProjectNumberPrefix:
    """Create a new prefix row.

    The DB trigger `trg_pnp_single_default` will demote any other
    is_default=true row in the same (project_id, entity_type) namespace.
    """
    entity_type = _validate_entity_type(payload.get("entity_type"))
    middle = _normalise_middle(payload.get("middle_prefix"))
    _validate_middle_shape(middle)

    if _middle_collides(db, project_id, entity_type, middle):
        label = "default (null-middle)" if middle is None else f"middle {middle!r}"
        raise ValueError(
            f"A prefix already exists for this project + {entity_type} + {label}"
        )

    row = ProjectNumberPrefix(
        project_id=project_id,
        entity_type=entity_type,
        middle_prefix=middle,
        description=payload.get("description") or None,
        is_default=bool(payload.get("is_default", False)),
        is_archived=False,
        next_sequence=1,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(row)
    db.flush()

    record_audit(
        db, action="Create",
        resource_type="project_number_prefix",
        resource_id=row.id,
        actor_user_id=user_id,
        project_id=project_id,
        field_changes=field_diff({}, _snapshot(row)),
        metadata={
            "entity_type": entity_type,
            "middle_prefix": middle,
        },
        request=request,
    )
    return row


def update_prefix(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    prefix_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    request: Optional[Request] = None,
) -> ProjectNumberPrefix:
    """Partial update.

    Notes:
      - `entity_type` is immutable post-create. Attempts to change it raise.
      - `middle_prefix` is editable only if no PO/Bill references this row;
        the reference-check is a R2 service-layer guard (po_numbering). For
        R1 we allow free edits since no PO/Bill tables exist yet.
      - `is_default=true` triggers the DB-level demotion of other defaults.
    """
    row = get_prefix(db, project_id, prefix_id)
    if row is None:
        raise LookupError(
            f"prefix {prefix_id} not found in project {project_id}"
        )

    if "entity_type" in payload and payload["entity_type"] != row.entity_type:
        raise ValueError("entity_type is immutable")

    before = _snapshot(row)

    if "middle_prefix" in payload:
        new_middle = _normalise_middle(payload["middle_prefix"])
        _validate_middle_shape(new_middle)
        if new_middle != row.middle_prefix:
            if _middle_collides(
                db, project_id, row.entity_type, new_middle,
                exclude_id=row.id,
            ):
                label = (
                    "default (null-middle)"
                    if new_middle is None
                    else f"middle {new_middle!r}"
                )
                raise ValueError(
                    f"A prefix already exists for this project + "
                    f"{row.entity_type} + {label}"
                )
            row.middle_prefix = new_middle

    if "description" in payload:
        row.description = payload["description"] or None

    if "is_default" in payload:
        row.is_default = bool(payload["is_default"])

    if "is_archived" in payload:
        row.is_archived = bool(payload["is_archived"])

    row.updated_by = user_id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    after = _snapshot(row)
    changes = field_diff(before, after)
    if changes:
        record_audit(
            db, action="Update",
            resource_type="project_number_prefix",
            resource_id=row.id,
            actor_user_id=user_id,
            project_id=project_id,
            field_changes=changes,
            metadata={
                "entity_type": row.entity_type,
                "middle_prefix": row.middle_prefix,
            },
            request=request,
        )
    return row


# ---------------------------------------------------------------------------
# Project-creation auto-seed
# ---------------------------------------------------------------------------

def seed_default_prefixes(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    request: Optional[Request] = None,
) -> list[ProjectNumberPrefix]:
    """Insert one null-middle is_default=true row per entity_type.

    Called once from the project-create handler. Idempotent — if a row
    already exists for a (project, entity_type, NULL middle), it is left
    alone and not re-audited.

    Returns the rows that were newly created (may be empty).
    """
    created: list[ProjectNumberPrefix] = []
    for et in PREFIX_ENTITY_TYPES:
        existing = db.scalar(
            select(ProjectNumberPrefix).where(
                ProjectNumberPrefix.project_id == project_id,
                ProjectNumberPrefix.entity_type == et,
                ProjectNumberPrefix.middle_prefix.is_(None),
            )
        )
        if existing is not None:
            continue
        row = ProjectNumberPrefix(
            project_id=project_id,
            entity_type=et,
            middle_prefix=None,
            description=f"Default {et.upper()} numbering",
            is_default=True,
            is_archived=False,
            next_sequence=1,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(row)
        db.flush()
        record_audit(
            db, action="Create",
            resource_type="project_number_prefix",
            resource_id=row.id,
            actor_user_id=user_id,
            project_id=project_id,
            field_changes=field_diff({}, _snapshot(row)),
            metadata={
                "entity_type": et,
                "middle_prefix": None,
                "kind": "auto_seed_on_project_create",
            },
            request=request,
        )
        created.append(row)
    return created


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def serialise(p: ProjectNumberPrefix) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "project_id": str(p.project_id),
        "entity_type": p.entity_type,
        "middle_prefix": p.middle_prefix,
        "description": p.description,
        "is_default": bool(p.is_default),
        "is_archived": bool(p.is_archived),
        "next_sequence": int(p.next_sequence),
        "preview_format": _preview(p),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _preview(p: ProjectNumberPrefix) -> str:
    """Return a human-readable sample of the next allocated number."""
    entity = "PO" if p.entity_type == "po" else "BILL"
    middle = f"-{p.middle_prefix}" if p.middle_prefix else ""
    return f"{entity}{middle}-{p.next_sequence:04d}"
