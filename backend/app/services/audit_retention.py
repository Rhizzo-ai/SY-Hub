"""Audit log retention / purge — Prompt 1.4 Section H.

The purge is OFF BY DEFAULT. It must never delete a row under 7 years old,
and it only deletes rows whose resource_type appears in an explicit
allow-list. Intended to run monthly at 02:00 UTC on the 1st; wiring into
a scheduler is deferred until the scheduler module lands (Prompt 1.6+).

Execution model (decision per spec H3):
We bypass the append-only trigger inside the purge transaction using
`ALTER TABLE audit_log DISABLE TRIGGER USER` → DELETE → `ENABLE TRIGGER
USER`, all inside one transaction so either both DDLs commit or both
roll back together. This requires the connecting role to OWN the
audit_log table (it does — Alembic creates it under the app user).
No superuser or schema changes required.

Rejected alternatives and why:
  - `SET session_replication_role = 'replica'` → requires superuser, which
    the app DB user rightly doesn't have.
  - `is_purgeable` boolean column → leaks retention concerns into the
    forensic schema; makes every read path carry the flag.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models.audit import AuditLog


log = logging.getLogger("syhomes.audit.retention")

# 7-year floor — hard, not configurable lower.
HARD_FLOOR_DAYS = 365 * 7


# --------------------------------------------------------------------------
# Configuration loader
# --------------------------------------------------------------------------

def _as_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> dict:
    """Read purge config from env. Kept minimal; a system_config table can
    supersede this in a later prompt without touching callers.
    """
    raw_allow = os.environ.get("AUDIT_PURGE_ALLOW_LIST", "").strip()
    allow_list = [s.strip() for s in raw_allow.split(",") if s.strip()]
    return {
        "enabled": _as_bool(os.environ.get("AUDIT_PURGE_ENABLED")),
        "dry_run": _as_bool(os.environ.get("AUDIT_PURGE_DRY_RUN", "1")),
        "allow_list": allow_list,
    }


# --------------------------------------------------------------------------
# Core purge routine
# --------------------------------------------------------------------------

def purge_old_audit_rows(
    db: Session,
    *,
    enabled: bool | None = None,
    dry_run: bool | None = None,
    allow_list: Iterable[str] | None = None,
    now: datetime | None = None,
) -> dict:
    """Purge audit_log rows older than the 7-year floor whose resource_type
    is in `allow_list`. Returns a result dict (never raises on empty work).

    All flags default to safe-off; pass explicit values in tests. In prod,
    the scheduler should call `load_config()` and pass the result.
    """
    cfg = {
        "enabled": enabled if enabled is not None else False,
        "dry_run": dry_run if dry_run is not None else True,
        "allow_list": list(allow_list) if allow_list is not None else [],
    }
    result = {
        "enabled": cfg["enabled"],
        "dry_run": cfg["dry_run"],
        "allow_list": cfg["allow_list"],
        "would_delete": 0,
        "deleted": 0,
        "skipped_reason": None,
    }
    if not cfg["enabled"]:
        result["skipped_reason"] = "audit.purge_enabled is false"
        log.info("audit purge SKIPPED: not enabled")
        return result
    if not cfg["allow_list"]:
        result["skipped_reason"] = "allow-list is empty"
        log.info("audit purge SKIPPED: allow-list empty")
        return result

    ref = now or datetime.now(timezone.utc)
    cutoff = ref - timedelta(days=HARD_FLOOR_DAYS)

    q = select(AuditLog.id).where(
        AuditLog.resource_type.in_(cfg["allow_list"]),
        AuditLog.created_at < cutoff,
    )
    ids = list(db.scalars(q).all())
    result["would_delete"] = len(ids)

    if cfg["dry_run"]:
        log.info(
            "audit purge DRY-RUN: would delete %d rows "
            "(resource_types=%s, cutoff=%s)",
            len(ids), cfg["allow_list"], cutoff.isoformat(),
        )
        return result
    if not ids:
        return result

    # Bypass the append-only trigger for the scope of THIS transaction.
    # The table owner (app DB user) has ALTER rights on user triggers.
    db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
    try:
        db.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
    finally:
        db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
    db.commit()
    result["deleted"] = len(ids)
    log.warning(
        "audit purge DELETED %d rows (resource_types=%s, cutoff=%s)",
        len(ids), cfg["allow_list"], cutoff.isoformat(),
    )
    return result
