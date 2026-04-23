"""Planning expiry sweep — Prompt 1.5 Section E2.

Daily 07:00 UTC scan of projects whose implementation_required=true,
actual_start_date IS NULL, status='Active', and planning_expiry_date is
set. Fires a notification on EXACT-day thresholds: 365, 180, 90, 30, 0
days remaining. Past expiry (days < 0): daily recurrence at the 0
threshold until start-on-site or status transition.

TODO: once Prompt 1.7 lands the notifications table, replace the log
line below with a proper notification insert (one per recipient).
Recipients today: project_lead_user_id + all users whose user_role has
director role scoped to primary_entity_id.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.projects import Project


log = logging.getLogger("syhomes.scheduler.planning_expiry")
THRESHOLDS = {365, 180, 90, 30, 0}


def _should_fire(days_remaining: int) -> bool:
    """Fire at exact-day thresholds AND every day past expiry (daily
    after day 0)."""
    if days_remaining in THRESHOLDS:
        return True
    if days_remaining < 0:
        return True
    return False


def planning_expiry_sweep(db: Session, *, today: Optional[date] = None) -> list[dict]:
    """Returns a list of notification payloads (for tests + future insert)."""
    ref = today or date.today()
    q = select(Project).where(
        Project.implementation_required.is_(True),
        Project.actual_start_date.is_(None),
        Project.planning_expiry_date.isnot(None),
        Project.status == "Active",
    )
    payloads: list[dict] = []
    for p in db.scalars(q).all():
        days = (p.planning_expiry_date - ref).days
        if not _should_fire(days):
            continue
        payload = {
            "project_id": str(p.id),
            "project_code": p.project_code,
            "days_remaining": days,
            "expiry_date": p.planning_expiry_date.isoformat(),
            "type": "Deadline_Approaching",
            "recipients_hint": "project_lead + entity directors",
        }
        payloads.append(payload)
        log.info(
            "planning_expiry_sweep: project=%s days=%d expiry=%s",
            p.project_code, days, p.planning_expiry_date,
        )
    return payloads
