"""Appraisal revisions service — Prompt 2.3 Checkpoint 2 (Phase B.3).

One operation: `create_new_version` — the canonical Approved/Rejected → new
Draft clone path. Runs in a single DB transaction with strict ordering to
satisfy the partial unique `uq_appraisals_current_per_project_scenario`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.appraisals import Appraisal
from app.models.appraisal_governance import AppraisalRevision
from app.services import appraisal_calc
from app.services.appraisal_versioning import (
    clone_as_new_version, mark_superseded,
)


class RevisionError(Exception):
    """Business-rule error with code + message + http_status."""

    def __init__(self, code: str, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def create_new_version(
    db: Session,
    source: Appraisal,
    *,
    revision_reason: str,
    summary_of_changes: str,
    actor_user_id: uuid.UUID,
) -> tuple[Appraisal, AppraisalRevision]:
    """Clone source into a new Draft and record a revisions row.

    Preconditions:
    - source.status IN {Approved, Rejected}.
    - source.is_current == True.

    Atomicity:
    1. source.is_current = False  (flush) — partial unique gate.
    2. If source was Approved → mark_superseded(source) (Rejected stays Rejected).
    3. clone_as_new_version(source) with status='Draft', is_current=False.
    4. new.is_current = True (flush).
    5. INSERT appraisal_revisions row.
    6. appraisal_calc.recompute(new) — populates delta_* via recompute hook.

    Caller handles commit + audit log.
    """
    if source.status not in ("Approved", "Rejected"):
        raise RevisionError(
            code="APPRAISAL_NOT_VERSIONABLE",
            message=(
                f"Cannot create new version from status "
                f"{source.status!r}. Only Approved or Rejected may spawn "
                f"a new version."
            ),
            http_status=409,
        )
    if not source.is_current:
        raise RevisionError(
            code="SOURCE_NOT_CURRENT",
            message=(
                "Cannot create new version from a non-current appraisal. "
                "Only the latest version may be versioned."
            ),
            http_status=400,
        )
    summary = (summary_of_changes or "").strip()
    if len(summary) < 10:
        raise RevisionError(
            code="SUMMARY_TOO_SHORT",
            message="summary_of_changes must be at least 10 characters.",
            http_status=400,
        )

    was_approved = source.status == "Approved"

    # 1. flip source is_current = false FIRST.
    source.is_current = False
    db.flush()

    # 2. mark_superseded (only for Approved path).
    if was_approved:
        mark_superseded(source)
        db.flush()

    # 3. clone — new row starts is_current=False (per clone helper).
    new = clone_as_new_version(db, source, created_by_user_id=actor_user_id)

    # 4. flip new is_current = true.
    new.is_current = True
    db.flush()

    # 5. insert revision row.
    rev = AppraisalRevision(
        from_version=source.version_number,
        to_version=new.version_number,
        appraisal_id_from=source.id,
        appraisal_id_to=new.id,
        revision_reason=revision_reason,
        summary_of_changes=summary,
        delta_gdv=Decimal(0),
        delta_total_cost=Decimal(0),
        delta_profit=Decimal(0),
        revised_by_user_id=actor_user_id,
    )
    db.add(rev)
    db.flush()

    # 6. recompute — this also populates the deltas via recompute_revision_deltas.
    appraisal_calc.recompute(db, new)

    return new, rev
