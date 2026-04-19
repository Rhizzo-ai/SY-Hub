"""Daily insurance expiry alerts.

Runs at 06:00 UTC every day. For each entity with non-null insurance dates,
compute days until expiry and emit an alert at thresholds 60, 30, 14, 7, 0.

Prompt 1.7 will replace the `_emit_alert` log-hook with a real notifications
row insert, scoped to director-role users with access to the entity.
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

ALERT_THRESHOLDS = [60, 30, 14, 7, 0]

_POLICIES = [
    ("EL", "el_insurance_expires"),
    ("PL", "pl_insurance_expires"),
    ("PI", "pi_insurance_expires"),
    ("All_Risks", "all_risks_insurance_expires"),
]


def _severity(days: int) -> str:
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
    """Return all current insurance alerts for a tenant.

    Excludes Struck_off entities. Includes any policy that is either already
    expired or expires within 60 days.
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
                    severity=_severity(days),
                )
            )
    # Sort: expired first, then closest-to-expiry
    alerts.sort(key=lambda a: (a.days_until_expiry, a.entity_name))
    return alerts


def _emit_alert(alert: InsuranceAlert, tenant_id: uuid.UUID) -> None:
    # TODO (Prompt 1.7): insert into `notifications` table scoped to directors.
    log.warning(
        "[INSURANCE_ALERT] tenant=%s entity=%s policy=%s expires=%s days=%d severity=%s",
        tenant_id,
        alert.entity_name,
        alert.policy,
        alert.expires_on.isoformat(),
        alert.days_until_expiry,
        alert.severity,
    )


def run_insurance_alert_sweep() -> int:
    """Sweep every tenant, emit alerts at defined thresholds. Returns count."""
    count = 0
    db = SessionLocal()
    try:
        tenants = db.scalars(select(Tenant)).all()
        for t in tenants:
            alerts = compute_insurance_alerts(db, t.id)
            for a in alerts:
                if a.days_until_expiry in ALERT_THRESHOLDS or a.days_until_expiry < 0:
                    _emit_alert(a, t.id)
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
