"""AI capture queue dispatcher — Prompt 2.5A / Chat 19A.

APScheduler-driven loop that drains the ai_capture_jobs queue. Each tick claims
ONE Queued job (via SELECT FOR UPDATE SKIP LOCKED) and processes it.

In test mode (APP_ENV=test) the scheduler is NOT started — tests invoke the
queue drain directly via `app.services.ai_capture.process_one_job(db)`. This
keeps tests deterministic and side-effect-free.

Cadence: every 30 seconds. Cheap when queue is empty (one SELECT).
"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.db import SessionLocal
from app.services.ai_capture import process_one_job


log = logging.getLogger("syhomes.scheduler.ai_capture")


def run_ai_capture_tick() -> dict:
    """Drain up to 5 jobs per tick. Returns a summary dict."""
    drained: list[str] = []
    db = SessionLocal()
    try:
        for _ in range(5):
            try:
                job_id = process_one_job(db)
            except Exception:
                log.exception("ai_capture_tick: process_one_job failed")
                db.rollback()
                break
            if job_id is None:
                db.commit()
                break
            drained.append(str(job_id))
            db.commit()
        return {"drained": drained, "count": len(drained)}
    finally:
        db.close()


_scheduler: BackgroundScheduler | None = None


def start_ai_capture_dispatcher() -> None:
    """Start the dispatcher. No-op in test mode."""
    global _scheduler
    if _scheduler is not None:
        return
    if os.environ.get("APP_ENV", "").lower() == "test":
        log.info("AI capture dispatcher disabled in APP_ENV=test.")
        return
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        run_ai_capture_tick,
        IntervalTrigger(seconds=30),
        id="ai_capture_tick",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    sched.start()
    _scheduler = sched
    log.info("AI capture dispatcher started (every 30s).")


def stop_ai_capture_dispatcher() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
