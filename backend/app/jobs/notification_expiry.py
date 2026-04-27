"""Notification expiry sweep — Prompt 1.7.

Daily 03:00 UTC. Bulk-dismiss notifications past `expires_at`. One
summary audit row per non-empty run.

Single-process in-memory APScheduler. Multi-process production needs a
persistent jobstore (Polish Pass).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import update as sql_update

from app.db import SessionLocal
from app.models.notifications import Notification
from app.services.audit import record_audit


log = logging.getLogger("syhomes.scheduler.notification_expiry")


def run_notification_expiry_sweep() -> int:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        result = db.execute(
            sql_update(Notification)
            .where(
                Notification.expires_at.isnot(None),
                Notification.expires_at < now,
                Notification.is_dismissed.is_(False),
            )
            .values(is_dismissed=True, dismissed_at=now)
        )
        affected = result.rowcount or 0
        if affected > 0:
            record_audit(
                db, action="Update", resource_type="notifications",
                resource_id=uuid4(), actor_user_id=None,
                field_changes=[],
                metadata={
                    "kind": "expiry_sweep",
                    "rows_dismissed": affected,
                    "swept_at": now.isoformat(),
                },
            )
        db.commit()
        log.info("notification_expiry_sweep dismissed %d row(s)", affected)
        return affected
    except Exception:
        db.rollback()
        log.exception("notification_expiry_sweep failed")
        return 0
    finally:
        db.close()


_scheduler: BackgroundScheduler | None = None


def start_notification_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        run_notification_expiry_sweep,
        CronTrigger(hour=3, minute=0),
        id="notification_expiry_sweep",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    log.info("Notification expiry scheduler started (daily 03:00 UTC).")


def stop_notification_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
