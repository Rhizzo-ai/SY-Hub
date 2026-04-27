"""Daily planning-expiry sweep scheduler — Prompt 1.5 Section E2.

Daily 07:00 UTC run of `planning_expiry_sweep`. Notifications insertion
lands in Prompt 1.7; for now we only log the payloads.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db import SessionLocal
from app.scheduler import planning_expiry_sweep

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_planning_expiry_sweep() -> int:
    db = SessionLocal()
    try:
        payloads = planning_expiry_sweep(db)
        if payloads:
            log.info("Planning-expiry sweep: %d notification(s) queued", len(payloads))
        return len(payloads)
    finally:
        db.close()


def start_planning_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        run_planning_expiry_sweep,
        CronTrigger(hour=7, minute=0),
        id="planning_expiry_sweep",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    log.info("Planning-expiry scheduler started (daily 07:00 UTC).")


def stop_planning_expiry_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
