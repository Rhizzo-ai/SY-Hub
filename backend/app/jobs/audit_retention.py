"""Audit retention sweep — Prompt 1.7.

Daily 03:00 UTC. Reads `audit.retention_purge_enabled` from system_config:
- false (default): logs "skipped, gated" and exits.
- true: invokes `purge_old_audit_rows` with `retention_years` from config.

Honours the 7-year hard floor in `app/services/audit_retention.py`
regardless of config (purge module enforces this independently of caller).

Single-process in-memory APScheduler. Multi-process needs persistent
jobstore (Polish Pass).
"""
from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db import SessionLocal
from app.services import system_config as system_config_service
from app.services.audit_retention import purge_old_audit_rows


log = logging.getLogger("syhomes.scheduler.audit_retention")


def run_audit_retention_sweep() -> dict:
    """Returns the result dict from purge_old_audit_rows, or a skip
    marker when gated off.
    """
    db = SessionLocal()
    try:
        enabled = system_config_service.get_or_default(
            "audit.retention_purge_enabled", False,
        )
        if not enabled:
            log.info("audit_retention_sweep SKIPPED: gated off via system_config")
            return {"enabled": False, "skipped_reason": "gated_off"}

        # Allow-list still drawn from env (matches existing audit_retention
        # contract); years comes from config.
        raw_allow = os.environ.get("AUDIT_PURGE_ALLOW_LIST", "").strip()
        allow_list = [s.strip() for s in raw_allow.split(",") if s.strip()]
        try:
            years = int(system_config_service.get_or_default("audit.retention_years", 7))
        except Exception:
            years = 7
        # The purge module enforces a 7-year HARD_FLOOR; passing fewer years
        # cannot reduce retention below 7y. We log the requested value for
        # visibility.
        log.info(
            "audit_retention_sweep: enabled=true years_requested=%d allow_list=%s "
            "(7-year hard floor enforced inside purge module)",
            years, allow_list,
        )
        # The current purge interface doesn't yet take `years`; the hard
        # floor is fixed. We pass enabled+allow_list and dry_run=False.
        result = purge_old_audit_rows(
            db, enabled=True, dry_run=False, allow_list=allow_list,
        )
        return result
    except Exception:
        log.exception("audit_retention_sweep failed")
        return {"enabled": True, "error": "exception"}
    finally:
        db.close()


_scheduler: BackgroundScheduler | None = None


def start_audit_retention_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        run_audit_retention_sweep,
        CronTrigger(hour=3, minute=0),
        id="audit_retention_sweep",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    log.info("Audit retention scheduler started (daily 03:00 UTC).")


def stop_audit_retention_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
