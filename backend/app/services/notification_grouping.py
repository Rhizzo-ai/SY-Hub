"""Notification lazy grouping — Prompt 1.7.

Read-time bucket-by-(notification_type, hour-bucket-of-created_at). When
the bucket has >= group_threshold_count entries within group_window_minutes,
collapse to a single summary entry carrying child IDs. Otherwise pass
through individual rows.

Used by GET /notifications/unread only. Full inbox returns ungrouped.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from app.models.notifications import Notification
from app.services import system_config as system_config_service


_DEFAULT_THRESHOLD = 3
_DEFAULT_WINDOW_MIN = 60


def _hour_bucket(ts: datetime, window_min: int) -> datetime:
    """Round timestamp DOWN to the nearest `window_min`-minute boundary."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    minutes = (ts.minute // window_min) * window_min
    return ts.replace(minute=minutes, second=0, microsecond=0)


def group_for_panel(
    notifications: Iterable[Notification],
    *,
    threshold: Optional[int] = None,
    window_minutes: Optional[int] = None,
) -> list[dict]:
    """Return a list of either:
      - {"kind": "single", "notification": <Notification>} OR
      - {"kind": "group", "notification_type": str,
         "count": int, "child_ids": [UUID, ...],
         "earliest_created_at": datetime, "latest_created_at": datetime}

    Order is preserved by latest member's created_at descending.
    """
    if threshold is None:
        threshold = int(system_config_service.get_or_default(
            "notification.group_threshold_count", _DEFAULT_THRESHOLD,
        ))
    if window_minutes is None:
        window_minutes = int(system_config_service.get_or_default(
            "notification.group_window_minutes", _DEFAULT_WINDOW_MIN,
        ))
    if threshold < 1:
        threshold = _DEFAULT_THRESHOLD
    if window_minutes < 1:
        window_minutes = _DEFAULT_WINDOW_MIN

    buckets: dict[tuple[str, datetime], list[Notification]] = {}
    order: list[tuple[str, datetime]] = []
    for n in notifications:
        b = _hour_bucket(n.created_at, window_minutes)
        key = (n.notification_type, b)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(n)

    out: list[dict] = []
    for key in order:
        items = buckets[key]
        if len(items) >= threshold:
            items_sorted = sorted(items, key=lambda x: x.created_at)
            out.append({
                "kind": "group",
                "notification_type": key[0],
                "count": len(items),
                "child_ids": [str(x.id) for x in items_sorted],
                "earliest_created_at": items_sorted[0].created_at,
                "latest_created_at": items_sorted[-1].created_at,
                "highest_priority": _highest_priority(items),
                "title_sample": items_sorted[-1].title,
            })
        else:
            for x in items:
                out.append({"kind": "single", "notification": x})

    out.sort(
        key=lambda e: (
            e["latest_created_at"]
            if e["kind"] == "group"
            else e["notification"].created_at
        ),
        reverse=True,
    )
    return out


_PRIO_ORDER = {"Low": 0, "Normal": 1, "High": 2, "Critical": 3}


def _highest_priority(items: Iterable[Notification]) -> str:
    return max((i.priority for i in items), key=lambda p: _PRIO_ORDER.get(p, 0))
