"""Daily insurance expiry alerts.

Runs at 06:00 UTC every day. For each entity with non-null insurance dates,
compute days until expiry and emit an alert when days_until_expiry matches
one of 60, 30, 14, 7, 0, OR when the policy is already past expiry.

Prompt 1.7 will replace the `_emit_alert` log-hook with a real insert into
the `notifications` table scoped to director-role users with access to the
entity.
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
    """Emission hook — logs the alert today; Prompt 1.7 swaps in notifications.

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
