"""Purchase Order numbering — Chat 24 §R2 (Prompt 2.5).

Atomic next-sequence allocation against `project_number_prefixes`.

Numbering format: `{ENTITY}-{middle?}-{NNNN}`
  - ENTITY  = 'PO' (uppercase, fixed by entity_type='po')
  - middle  = optional, uppercase alphanumeric+dash, 1-8 chars
  - NNNN    = 4-digit zero-padded sequence (>= 0001)

Allocation invariants:
  - Resolves the default prefix when caller doesn't specify one.
  - Locks the chosen prefix row FOR UPDATE before reading next_sequence
    so concurrent PO creates can't collide.
  - Persists the increment (next_sequence += 1) in the same transaction.
  - The actual po_number is also persisted on the PO row, plus
    po_number_prefix_id + po_sequence for forensic reconstruction.

External numbers (po_number set by the caller, no prefix lookup) are
also supported via `format_external_number` for the
"override-numbering" path on issue. R2's POST endpoint uses
`allocate_next_number` only — the external/manual path will land in R4
or R5 alongside the issue endpoint.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.number_prefixes import ProjectNumberPrefix


class NumberingError(Exception):
    """Raised when the numbering allocation cannot proceed (missing default
    prefix, archived prefix, or wrong entity_type).
    """


def _format(po_prefix: ProjectNumberPrefix, sequence: int) -> str:
    middle = f"-{po_prefix.middle_prefix}" if po_prefix.middle_prefix else ""
    return f"PO{middle}-{sequence:04d}"


def resolve_prefix(
    db: Session,
    project_id: uuid.UUID,
    *,
    prefix_id: Optional[uuid.UUID] = None,
) -> ProjectNumberPrefix:
    """Return the prefix row to use for this allocation.

    If `prefix_id` is provided, it must exist, belong to `project_id`,
    have entity_type='po' and not be archived.

    Otherwise the project's default po prefix is used (the
    is_default=true row, of which there is at most one per project +
    entity_type via the DB trigger).
    """
    if prefix_id is not None:
        row = db.scalar(
            select(ProjectNumberPrefix).where(
                ProjectNumberPrefix.id == prefix_id,
                ProjectNumberPrefix.project_id == project_id,
            )
        )
        if row is None:
            raise NumberingError("Number prefix not found for this project")
        if row.entity_type != "po":
            raise NumberingError(
                f"Number prefix is for {row.entity_type!r}, not 'po'"
            )
        if row.is_archived:
            raise NumberingError("Number prefix is archived")
        return row

    row = db.scalar(
        select(ProjectNumberPrefix).where(
            ProjectNumberPrefix.project_id == project_id,
            ProjectNumberPrefix.entity_type == "po",
            ProjectNumberPrefix.is_default.is_(True),
            ProjectNumberPrefix.is_archived.is_(False),
        )
    )
    if row is None:
        raise NumberingError(
            "Project has no default 'po' number prefix configured"
        )
    return row


def allocate_next_number(
    db: Session,
    project_id: uuid.UUID,
    *,
    prefix_id: Optional[uuid.UUID] = None,
) -> tuple[str, ProjectNumberPrefix, int]:
    """Lock the resolved prefix row, read+increment next_sequence, and
    return the formatted po_number along with the prefix + raw sequence.

    The caller is expected to immediately persist a PurchaseOrder row
    with these values — failure to do so wastes a sequence (gap), which
    is allowed by the spec (sequences are monotonic, not gap-free).

    Concurrency:
      The SELECT ... FOR UPDATE on the prefix row serialises concurrent
      allocations within the same (project, prefix) namespace. Other
      prefix rows remain insertable in parallel.
    """
    # Resolve first (no lock) to get the id, then lock the specific row.
    resolved = resolve_prefix(db, project_id, prefix_id=prefix_id)
    locked = db.scalar(
        select(ProjectNumberPrefix)
        .where(ProjectNumberPrefix.id == resolved.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        # Vanished between resolve + lock — treat as missing.
        raise NumberingError("Number prefix vanished mid-allocation")

    seq = int(locked.next_sequence)
    if seq < 1:
        # CHECK constraint pins it >= 1, defensive.
        raise NumberingError(
            f"Number prefix next_sequence is invalid ({seq})"
        )
    locked.next_sequence = seq + 1
    db.flush()
    return _format(locked, seq), locked, seq
