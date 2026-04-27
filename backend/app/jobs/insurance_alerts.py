"""Daily insurance expiry alerts.

Runs at 06:00 UTC every day. For each entity with non-null insurance dates,
compute days until expiry and emit an alert when days_until_expiry matches
one of 60, 30, 14, 7, 0, OR when the policy is already past expiry.

Prompt 1.7 retro-wired `_emit_alert` to dispatch a real
Insurance_Expiry notification (priority High, or Critical when the
policy has already expired or expires today) to every director with
view access to the entity in question.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import date
from typing import List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Entity, Tenant
from app.schemas.entity import InsuranceAlert

log = logging.getLogger(__name__)

# Days-to-expiry thresholds that trigger an alert event.
ALERT_THRESHOLDS: tuple[int, ...] = (60, 30, 14, 7, 0)

# Map threshold days → severity label emitted to _emit_alert / notifications.
THRESHOLD_LABELS: dict[int, str] = {
    60: "60_day",
    30: "30_day",
    14: "14_day",
    7: "7_day",
    0: "0_day",
}
EXPIRED_LABEL = "expired"

_POLICIES = [
    ("EL", "el_insurance_expires"),
    ("PL", "pl_insurance_expires"),
    ("PI", "pi_insurance_expires"),
    ("All_Risks", "all_risks_insurance_expires"),
]


def _ui_severity(days: int) -> str:
    """Display-side bucket used by the preview endpoint."""
    if days < 0:
        return "expired"
    if days <= 14:
        return "critical"
    if days <= 60:
        return "warning"
    return "upcoming"


def compute_insurance_alerts(
    db: Session,
    tenant_id: uuid.UUID,
) -> List[InsuranceAlert]:
    """Return all current insurance alerts for a tenant (<=60 days / expired).

    This is used by the /api/meta/insurance-alerts preview endpoint. It is
    INTENTIONALLY broader than the scheduled sweep — it shows the full set of
    upcoming alerts to directors in the UI dashboard.
    """
    today = date.today()
    ents = db.scalars(
        select(Entity).where(
            Entity.tenant_id == tenant_id,
            Entity.status != "Struck_off",
        )
    ).all()

    alerts: List[InsuranceAlert] = []
    for ent in ents:
        for code, attr in _POLICIES:
            expires = getattr(ent, attr)
            if expires is None:
                continue
            days = (expires - today).days
            if days > 60:
                continue
            alerts.append(
                InsuranceAlert(
                    entity_id=ent.id,
                    entity_name=ent.name,
                    policy=code,
                    expires_on=expires,
                    days_until_expiry=days,
                    severity=_ui_severity(days),
                )
            )
    alerts.sort(key=lambda a: (a.days_until_expiry, a.entity_name))
    return alerts


def _emit_alert(
    alert: InsuranceAlert,
    tenant_id: uuid.UUID,
    severity: str,
) -> None:
    """Emission hook — logs the alert AND dispatches a notification to
    every director with view access to the entity (Prompt 1.7 retro-wire).

    `severity` is one of {"60_day", "30_day", "14_day", "7_day", "0_day", "expired"}.
    Tests monkey-patch this function to capture invocations.
    """
    log.warning(
        "[INSURANCE_ALERT] tenant=%s entity=%s policy=%s expires=%s "
        "days=%d severity=%s",
        tenant_id,
        alert.entity_name,
        alert.policy,
        alert.expires_on.isoformat(),
        alert.days_until_expiry,
        severity,
    )
    # Notification dispatch (Prompt 1.7 retro-wire). Best-effort — never
    # blocks the underlying alert loop.
    try:
        _dispatch_insurance_alert(alert, tenant_id, severity)
    except Exception:
        log.exception("insurance alert notification dispatch failed")


def _dispatch_insurance_alert(
    alert: InsuranceAlert,
    tenant_id: uuid.UUID,
    severity: str,
) -> None:
    """Dispatch one Insurance_Expiry notification per director with
    `entities.view` access to the entity in question.

    Priority:
      - Critical when policy is already expired (severity='expired') or
        same-day (0_day).
      - High otherwise.
    """
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.rbac import Role, UserRole, user_role_entities
    from app.models.user import User
    from app.services.notifications import safe_dispatch

    priority = "Critical" if severity in ("expired", "0_day") else "High"
    title = f"Insurance expiring: {alert.entity_name} — {alert.policy}"
    body = (
        f"{alert.policy} insurance for **{alert.entity_name}** "
        f"{'has expired' if alert.days_until_expiry < 0 else f'expires in {alert.days_until_expiry} days'} "
        f"({alert.expires_on.isoformat()})."
    )
    db = SessionLocal()
    try:
        # Director users with access to this entity:
        # - role_scope='All' on a director role
        # - or role_scope='Specific' with the entity in user_role_entities
        director_roles = db.scalars(
            select(Role).where(Role.code.in_(["director", "super_admin"]))
        ).all()
        if not director_roles:
            return
        director_role_ids = {r.id for r in director_roles}
        all_user_roles = db.scalars(
            select(UserRole).where(
                UserRole.role_id.in_(director_role_ids),
                UserRole.status == "Active",
            )
        ).all()
        recipient_ids: set = set()
        for ur in all_user_roles:
            if ur.entity_scope == "All":
                recipient_ids.add(ur.user_id)
            elif ur.entity_scope == "Specific":
                rows = db.execute(
                    select(user_role_entities.c.entity_id).where(
                        user_role_entities.c.user_role_id == ur.id,
                    )
                ).all()
                if any(r[0] == alert.entity_id for r in rows):
                    recipient_ids.add(ur.user_id)
        for uid in recipient_ids:
            safe_dispatch(
                db,
                recipient_user_id=uid,
                notification_type="Insurance_Expiry",
                title=title,
                body=body,
                priority=priority,
                related_resource_type="entities",
                related_resource_id=alert.entity_id,
                action_url=f"/entities/{alert.entity_id}",
                action_label="View entity",
            )
        db.commit()
    finally:
        db.close()


def run_insurance_alert_sweep() -> int:
    """Scheduled daily sweep — emit alerts at exact thresholds + for any expired policy.

    Returns the number of alerts emitted (for visibility / monitoring).
    """
    count = 0
    db = SessionLocal()
    try:
        tenants = db.scalars(select(Tenant)).all()
        for t in tenants:
            today = date.today()
            ents = db.scalars(
                select(Entity).where(
                    Entity.tenant_id == t.id,
                    Entity.status != "Struck_off",
                )
            ).all()
            for ent in ents:
                for code, attr in _POLICIES:
                    expires = getattr(ent, attr)
                    if expires is None:
                        continue
                    days = (expires - today).days
                    severity: str | None = None
                    if days < 0:
                        severity = EXPIRED_LABEL
                    elif days in THRESHOLD_LABELS:
                        severity = THRESHOLD_LABELS[days]
                    if severity is None:
                        continue
                    alert = InsuranceAlert(
                        entity_id=ent.id,
                        entity_name=ent.name,
                        policy=code,
                        expires_on=expires,
                        days_until_expiry=days,
                        severity=_ui_severity(days),
                    )
                    _emit_alert(alert, t.id, severity)
                    count += 1
        log.info("Insurance alert sweep complete: %d alerts emitted", count)
    finally:
        db.close()
    return count


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    hour = int(os.environ.get("INSURANCE_ALERT_HOUR_UTC", "6"))
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        run_insurance_alert_sweep,
        CronTrigger(hour=hour, minute=0),
        id="insurance_alert_sweep",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    log.info("Insurance alert scheduler started (daily at %02d:00 UTC)", hour)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
