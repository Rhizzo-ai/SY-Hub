"""SystemConfig singleton service — Prompt 1.7.

Typed key/value access with in-memory caching.

- get(key)              → typed value (raises KeyError if missing)
- get_or_default(...)   → typed value or default
- set(key, value, uid)  → validates parse, audits, invalidates cache
- restore(key, uid)     → restores config_value to default_value, audits
- invalidate(key=None)  → clears cache (one key or all)

Cache lives in module-level dict; lazy-populated on first .get(). All
writes go through .set/.restore which both invalidate the relevant
cache entry. Single-process: cache is per-worker. Multi-worker
invalidation requires a pub/sub channel — Polish Pass.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.system_config import SystemConfig as SystemConfigModel
from app.services.audit import field_diff, record_audit


log = logging.getLogger("syhomes.system_config")


_cache: dict[str, Any] = {}
_cache_lock = threading.RLock()
_db_query_count: dict[str, int] = {}  # for tests/diagnostics only


# Sentinels & sentinels for missing-key handling
_MISSING = object()


# ---------------------------------------------------------------------------
# Build Pack 2.4C — Budget Approval Controls (Segregation of Duties)
#
# Editable, single global threshold (£) at/above which a budget's creator may
# not be the user who activates it. Stored as a `Decimal` value_type row in
# system_config (key/value pattern — no schema change). The in-code default
# below is the defensive fallback for when the row is absent (fresh DB
# pre-seed, or row deleted), mirroring the variance-band fallback pattern
# already in budgets.py (VARIANCE_AMBER_PCT / VARIANCE_RED_PCT).
# ---------------------------------------------------------------------------
BUDGET_SELF_APPROVAL_THRESHOLD_KEY = "budget.self_approval_threshold_gbp"
DEFAULT_BUDGET_SELF_APPROVAL_THRESHOLD_GBP = Decimal("10000.00")


def _parse(raw: str, value_type: str) -> Any:
    """Parse a stored string into its typed Python value.

    Raises ValueError on bad input — caller decides how to surface.
    """
    if value_type == "String":
        return raw
    if value_type == "Integer":
        return int(raw)
    if value_type == "Decimal":
        return Decimal(raw)
    if value_type == "Boolean":
        v = raw.strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"Invalid boolean: {raw!r}")
    if value_type == "JSON":
        return json.loads(raw)
    if value_type == "Date":
        return date.fromisoformat(raw)
    raise ValueError(f"Unknown value_type: {value_type!r}")


def _serialise(value: Any, value_type: str) -> str:
    """Serialise a typed Python value for storage. Validates parse round-trip."""
    if value_type == "String":
        if not isinstance(value, str):
            raise ValueError("Expected string")
        return value
    if value_type == "Integer":
        if isinstance(value, bool) or not isinstance(value, int):
            # bool is a subclass of int in Python — reject explicitly.
            try:
                return str(int(value))
            except Exception as e:
                raise ValueError(f"Expected integer: {e}")
        return str(value)
    if value_type == "Decimal":
        try:
            return str(Decimal(str(value)))
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"Expected decimal: {e}")
    if value_type == "Boolean":
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("true", "false"):
                return v
        raise ValueError("Expected boolean")
    if value_type == "JSON":
        # If the caller passed a string, treat it as a JSON document and
        # reject if it doesn't parse. Otherwise dump the Python object.
        if isinstance(value, str):
            try:
                json.loads(value)
            except (TypeError, ValueError) as e:
                raise ValueError(f"Not valid JSON: {e}")
            return value
        try:
            return json.dumps(value)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Not JSON-serialisable: {e}")
    if value_type == "Date":
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            # Validate parse round-trip.
            date.fromisoformat(value)
            return value
        raise ValueError("Expected ISO date string or date")
    raise ValueError(f"Unknown value_type: {value_type!r}")


def invalidate(key: Optional[str] = None) -> None:
    """Clear cache entry (specific key) or all entries (key=None).

    The DB-query counter is preserved across invalidations so callers
    can observe cumulative behaviour (test diagnostic only).
    """
    with _cache_lock:
        if key is None:
            _cache.clear()
        else:
            _cache.pop(key, None)


def _reset_query_counts() -> None:
    """Test-only helper. Clears the cumulative DB-hit counter."""
    with _cache_lock:
        _db_query_count.clear()


def _load_row(db: Session, key: str) -> Optional[SystemConfigModel]:
    _db_query_count[key] = _db_query_count.get(key, 0) + 1
    return db.scalar(
        select(SystemConfigModel).where(SystemConfigModel.config_key == key)
    )


def get(key: str, db: Optional[Session] = None) -> Any:
    """Return the typed value for `key`. Raises KeyError if not seeded."""
    with _cache_lock:
        cached = _cache.get(key, _MISSING)
        if cached is not _MISSING:
            return cached
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        row = db.scalar(
            select(SystemConfigModel).where(SystemConfigModel.config_key == key)
        )
        with _cache_lock:
            _db_query_count[key] = _db_query_count.get(key, 0) + 1
        if row is None:
            raise KeyError(f"system_config key not found: {key!r}")
        value = _parse(row.config_value, row.value_type)
        with _cache_lock:
            _cache[key] = value
        return value
    finally:
        if own_session:
            db.close()


def get_or_default(key: str, default: Any, db: Optional[Session] = None) -> Any:
    try:
        return get(key, db=db)
    except KeyError:
        return default


def set_value(
    db: Session,
    key: str,
    value: Any,
    user_id: Optional[UUID],
    *,
    request=None,
) -> SystemConfigModel:
    """Validate parse, update row, audit old+new, invalidate cache.

    Raises:
        KeyError: missing key.
        ValueError: bad parse for the declared value_type.
        PermissionError: row is_system_locked=true.
    """
    row = db.scalar(
        select(SystemConfigModel).where(SystemConfigModel.config_key == key)
    )
    if row is None:
        raise KeyError(f"system_config key not found: {key!r}")
    if row.is_system_locked:
        raise PermissionError(f"system_config key {key!r} is system-locked")

    old_value_raw = row.config_value
    new_value_raw = _serialise(value, row.value_type)
    if old_value_raw == new_value_raw:
        # No-op; do not audit.
        invalidate(key)
        return row

    obj = db.get(SystemConfigModel, row.id)
    obj.config_value = new_value_raw
    obj.last_changed_by_user_id = user_id
    obj.last_changed_at = datetime.now(timezone.utc)
    db.flush()

    record_audit(
        db, action="Update", resource_type="system_config",
        resource_id=obj.id, actor_user_id=user_id,
        field_changes=field_diff(
            {"config_value": old_value_raw},
            {"config_value": new_value_raw},
        ),
        metadata={"config_key": key, "value_type": row.value_type},
        request=request,
    )
    invalidate(key)
    return obj


def restore(
    db: Session,
    key: str,
    user_id: Optional[UUID],
    *,
    request=None,
) -> SystemConfigModel:
    """Reset config_value → default_value. Audits if it actually changes."""
    row = db.scalar(
        select(SystemConfigModel).where(SystemConfigModel.config_key == key)
    )
    if row is None:
        raise KeyError(f"system_config key not found: {key!r}")
    if row.is_system_locked:
        raise PermissionError(f"system_config key {key!r} is system-locked")

    if row.config_value == row.default_value:
        invalidate(key)
        return row

    obj = db.get(SystemConfigModel, row.id)
    old_value_raw = obj.config_value
    obj.config_value = obj.default_value
    obj.last_changed_by_user_id = user_id
    obj.last_changed_at = datetime.now(timezone.utc)
    db.flush()

    record_audit(
        db, action="Update", resource_type="system_config",
        resource_id=obj.id, actor_user_id=user_id,
        field_changes=field_diff(
            {"config_value": old_value_raw},
            {"config_value": obj.default_value},
        ),
        metadata={"config_key": key, "kind": "restore_default"},
        request=request,
    )
    invalidate(key)
    return obj


def list_all(db: Session) -> list[SystemConfigModel]:
    """Return every config row, ordered by category + key."""
    return list(db.scalars(
        select(SystemConfigModel).order_by(
            SystemConfigModel.category, SystemConfigModel.config_key,
        )
    ).all())


def get_budget_self_approval_threshold(db: Optional[Session] = None) -> Decimal:
    """Return the GBP threshold at/above which a budget's creator may not
    self-activate (segregation of duties — Build Pack 2.4C / Decision 1
    from the MD + Louise Track 2 review, 2026-05-28).

    Reads from `system_config` (key `budget.self_approval_threshold_gbp`,
    value_type `Decimal`); falls back to the in-code default
    `DEFAULT_BUDGET_SELF_APPROVAL_THRESHOLD_GBP` (£10,000.00) when the
    config row is absent. This mirrors the defensive fallback pattern
    already used for variance bands in budgets.py.

    Returns a `Decimal` (2dp). Comparison semantics at the call site are
    `total >= threshold` (`>=`, not `>`) — at exactly the threshold a
    separate approver is required.
    """
    value = get_or_default(
        BUDGET_SELF_APPROVAL_THRESHOLD_KEY,
        DEFAULT_BUDGET_SELF_APPROVAL_THRESHOLD_GBP,
        db=db,
    )
    # The row's value_type=Decimal => _parse() already returns a Decimal.
    # Defensive cast in case an unexpected type slipped through.
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _query_count_for(key: str) -> int:
    """Internal — returns DB hit count for a key. Test diagnostic only."""
    return _db_query_count.get(key, 0)
