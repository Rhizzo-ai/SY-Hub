"""Planning expiry sweep — Prompt 1.5 Section E2 + Prompt 1.7 notification wire-up.

Daily 07:00 UTC scan of projects whose implementation_required=true,
actual_start_date IS NULL, status='Active', and planning_expiry_date is
set. Fires a notification on EXACT-day thresholds: 365, 180, 90, 30, 0
days remaining. Past expiry (days < 0): daily recurrence at the 0
threshold until start-on-site or status transition.

Prompt 1.7 retro-wire: dispatches one Deadline_Approaching notification
per recipient per qualifying project per day. Recipients:
  - project_lead_user_id (if set)
  - all directors with entity_scope='All' or scoped to primary_entity_id
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from uuid import UUID

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


def _recipients_for(db: Session, project: Project) -> set[UUID]:
    """Return UUIDs of users entitled to a planning-expiry alert for
    `project`: project_lead_user_id + directors scoped to its
    primary_entity_id (or 'All')."""
    from app.models.rbac import Role, UserRole, user_role_entities

    out: set[UUID] = set()
    if project.project_lead_user_id:
        out.add(project.project_lead_user_id)

    director_roles = db.scalars(
        select(Role).where(Role.code.in_(["director", "super_admin"]))
    ).all()
    director_role_ids = {r.id for r in director_roles}
    if not director_role_ids:
        return out
    all_user_roles = db.scalars(
        select(UserRole).where(
            UserRole.role_id.in_(director_role_ids),
            UserRole.status == "Active",
        )
    ).all()
    for ur in all_user_roles:
        if ur.entity_scope == "All":
            out.add(ur.user_id)
        elif ur.entity_scope == "Specific":
            rows = db.execute(
                select(user_role_entities.c.entity_id).where(
                    user_role_entities.c.user_role_id == ur.id,
                )
            ).all()
            if any(r[0] == project.primary_entity_id for r in rows):
                out.add(ur.user_id)
    return out


def planning_expiry_sweep(db: Session, *, today: Optional[date] = None) -> list[dict]:
    """Returns a list of notification payloads (for tests) AND, in the
    same pass, dispatches Deadline_Approaching notifications via the
    NotificationService (Prompt 1.7 retro-wire).
    """
    from app.services.notifications import safe_dispatch

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
        recipients = _recipients_for(db, p)
        payload = {
            "project_id": str(p.id),
            "project_code": p.project_code,
            "days_remaining": days,
            "expiry_date": p.planning_expiry_date.isoformat(),
            "type": "Deadline_Approaching",
            "recipient_user_ids": [str(u) for u in recipients],
        }
        payloads.append(payload)
        log.info(
            "planning_expiry_sweep: project=%s days=%d expiry=%s recipients=%d",
            p.project_code, days, p.planning_expiry_date, len(recipients),
        )

        priority = "Critical" if days < 0 else "High" if days <= 30 else "Normal"
        title = f"Planning expiry: {p.project_code} — {p.name}"
        if days < 0:
            body = (
                f"Planning permission for **{p.project_code}** expired "
                f"on {p.planning_expiry_date.isoformat()} "
                f"({abs(days)} days ago)."
            )
        elif days == 0:
            body = (
                f"Planning permission for **{p.project_code}** expires "
                f"TODAY ({p.planning_expiry_date.isoformat()})."
            )
        else:
            body = (
                f"Planning permission for **{p.project_code}** expires in "
                f"{days} days ({p.planning_expiry_date.isoformat()})."
            )
        for uid in recipients:
            safe_dispatch(
                db,
                recipient_user_id=uid,
                notification_type="Deadline_Approaching",
                title=title,
                body=body,
                priority=priority,
                related_resource_type="projects",
                related_resource_id=p.id,
                action_url=f"/projects/{p.id}",
                action_label="View project",
            )
    if payloads:
        db.commit()
    return payloads
