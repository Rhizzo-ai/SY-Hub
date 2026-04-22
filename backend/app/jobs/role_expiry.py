"""Daily job to mark expired user_roles."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import update

from app.db import SessionLocal
from app.models.rbac import UserRole

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_role_expiry_sweep() -> int:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        stmt = (
            update(UserRole)
            .where(
                UserRole.status == "Active",
                UserRole.expires_at.is_not(None),
                UserRole.expires_at <= now,
            )
            .values(status="Expired")
        )
        result = db.execute(stmt)
        db.commit()
        rc = result.rowcount or 0
        if rc:
            log.info("Role-expiry sweep: marked %d user_roles as Expired", rc)
        return rc
    finally:
        db.close()


def start_role_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        run_role_expiry_sweep,
        CronTrigger(minute=0),  # hourly
        id="role_expiry_sweep",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    log.info("Role-expiry scheduler started (hourly).")


def stop_role_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
