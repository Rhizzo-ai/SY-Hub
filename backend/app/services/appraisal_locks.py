"""Shared appraisal row-locking helper — P1.R3.

Single source of truth for the per-appraisal `SELECT ... FOR UPDATE`
row lock that serialises concurrent mutators of one appraisal.

History:
- P0.1 introduced this lock as a router-private helper
  (`appraisals.py::_lock_appraisal_for_update`) on the 13 mutating
  recompute sites.
- P1.R3 (Claude Code finding) — `appraisal_revisions.create_new_version`
  flips `source.is_current = False` without a row lock, allowing two
  concurrent new-version calls on the same Approved source to interleave
  past the partial unique index `uq_appraisals_current_per_project_scenario`.
  Service-layer code can't reach a router-private helper without
  inverting the dependency direction; extract here.

Scope:
- Locks the single appraisal row ONLY. Cost-line locks remain a
  concern of the router-side recompute path (where cost line edits
  share the same transaction). The governance race in P1.R3 turns on
  the source-row `is_current` flip, not the cost lines.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appraisals import Appraisal


def lock_appraisal_for_update(db: Session, appraisal_id: uuid.UUID) -> None:
    """`SELECT ... FOR UPDATE` on the appraisal row in the caller's
    open transaction. Concurrent callers serialise on this row before
    they reach any subsequent mutation.

    Reads (GETs) do NOT call this. Mutating handlers call it at the
    top of their work, BEFORE any flag flip or recompute.
    """
    db.execute(
        select(Appraisal.id)
        .where(Appraisal.id == appraisal_id)
        .with_for_update()
    ).all()
