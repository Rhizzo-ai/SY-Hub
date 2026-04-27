"""Notifications router — Prompt 1.7.

All routes mount under /api/v1/notifications (v1 prefix set at include
time in server.py).

Endpoints:
- GET    /                        Inbox (own only). Pagination + filters.
- GET    /unread                  Bell-panel data, lazy-grouped (50 cap).
- GET    /unread-count            {count: int} — polled every 30s by frontend.
- PATCH  /{id}/read               Mark single as read (own only).
- PATCH  /{id}/dismiss            Mark single as dismissed (own only).
- POST   /mark-all-read           Bulk; one summary audit.

NB: No POST /. Notifications are created internally via
NotificationService.dispatch().
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, select, update as sql_update
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.models.notifications import (
    Notification, NOTIFICATION_PRIORITIES, NOTIFICATION_TYPES,
)
from app.models.user import User
from app.services.audit import record_audit
from app.services.notification_grouping import group_for_panel


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _serialise(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "recipient_user_id": str(n.recipient_user_id),
        "notification_type": n.notification_type,
        "priority": n.priority,
        "title": n.title,
        "body": n.body,
        "related_resource_type": n.related_resource_type,
        "related_resource_id":
            str(n.related_resource_id) if n.related_resource_id else None,
        "action_url": n.action_url,
        "action_label": n.action_label,
        "is_read": n.is_read,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "is_dismissed": n.is_dismissed,
        "dismissed_at": n.dismissed_at.isoformat() if n.dismissed_at else None,
        "email_sent": n.email_sent,
        "email_sent_at": n.email_sent_at.isoformat() if n.email_sent_at else None,
        "sms_sent": n.sms_sent,
        "expires_at": n.expires_at.isoformat() if n.expires_at else None,
        "created_at": n.created_at.isoformat(),
    }


def _serialise_panel(entry: dict) -> dict:
    if entry["kind"] == "group":
        return {
            "kind": "group",
            "notification_type": entry["notification_type"],
            "count": entry["count"],
            "child_ids": entry["child_ids"],
            "earliest_created_at": entry["earliest_created_at"].isoformat(),
            "latest_created_at": entry["latest_created_at"].isoformat(),
            "highest_priority": entry["highest_priority"],
            "title_sample": entry["title_sample"],
        }
    return {"kind": "single", "notification": _serialise(entry["notification"])}


@router.get("")
def list_inbox(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    type: Optional[list[str]] = Query(None),
    priority: Optional[list[str]] = Query(None),
    is_read: Optional[bool] = None,
    is_dismissed: Optional[bool] = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(Notification).where(Notification.recipient_user_id == current.id)
    if type:
        for t in type:
            if t not in NOTIFICATION_TYPES:
                raise HTTPException(400, f"Invalid notification_type: {t}")
        q = q.where(Notification.notification_type.in_(type))
    if priority:
        for p in priority:
            if p not in NOTIFICATION_PRIORITIES:
                raise HTTPException(400, f"Invalid priority: {p}")
        q = q.where(Notification.priority.in_(priority))
    if is_read is not None:
        q = q.where(Notification.is_read.is_(is_read))
    if is_dismissed is not None:
        q = q.where(Notification.is_dismissed.is_(is_dismissed))

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(
        q.order_by(Notification.created_at.desc())
         .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_serialise(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/unread")
def list_unread_panel(
    limit: int = Query(50, ge=1, le=200),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(Notification)
        .where(
            Notification.recipient_user_id == current.id,
            Notification.is_read.is_(False),
            Notification.is_dismissed.is_(False),
        )
        .order_by(Notification.created_at.desc())
        .limit(limit)
    ).all()
    grouped = group_for_panel(rows)
    return {
        "items": [_serialise_panel(e) for e in grouped],
        "raw_count": len(rows),
    }


@router.get("/unread-count")
def unread_count(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Polled every 30s by the frontend bell.

    DELIBERATELY not rate-limited. The rate limiter in
    `app/services/rate_limit.py` is a per-endpoint opt-in helper invoked
    only by login + password-reset routes; it is NOT a global middleware
    and the `LIMITS` dict does not register this path. If a future change
    introduces a blanket middleware, add an explicit exemption here AND
    update `backend/README.md` § "Rate limiting and the bell endpoint".

    Verified by `tests/test_notifications.py
    ::TestPolling::test_polling_does_not_trip_rate_limiter`.
    """
    cnt = db.scalar(
        select(func.count()).select_from(Notification).where(
            Notification.recipient_user_id == current.id,
            Notification.is_read.is_(False),
            Notification.is_dismissed.is_(False),
        )
    ) or 0
    return {"count": int(cnt)}


def _own_or_403(db: Session, notif_id: UUID, user_id: UUID) -> Notification:
    n = db.get(Notification, notif_id)
    if n is None:
        raise HTTPException(404, "Notification not found")
    if n.recipient_user_id != user_id:
        raise HTTPException(403, "Not your notification")
    return n


@router.patch("/{notif_id}/read")
def mark_read(
    notif_id: UUID,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = _own_or_403(db, notif_id, current.id)
    if not n.is_read:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
        record_audit(
            db, action="Update", resource_type="notifications",
            resource_id=n.id, actor_user_id=current.id,
            field_changes=[
                {"field": "is_read", "old": False, "new": True},
            ],
            metadata={"kind": "mark_read"},
            request=request,
        )
        db.commit()
        db.refresh(n)
    return _serialise(n)


@router.patch("/{notif_id}/dismiss")
def dismiss(
    notif_id: UUID,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = _own_or_403(db, notif_id, current.id)
    if not n.is_dismissed:
        n.is_dismissed = True
        n.dismissed_at = datetime.now(timezone.utc)
        record_audit(
            db, action="Update", resource_type="notifications",
            resource_id=n.id, actor_user_id=current.id,
            field_changes=[
                {"field": "is_dismissed", "old": False, "new": True},
            ],
            metadata={"kind": "dismiss"},
            request=request,
        )
        db.commit()
        db.refresh(n)
    return _serialise(n)


@router.post("/mark-all-read")
def mark_all_read(
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    result = db.execute(
        sql_update(Notification)
        .where(
            Notification.recipient_user_id == current.id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True, read_at=now)
    )
    affected = result.rowcount or 0
    if affected > 0:
        record_audit(
            db, action="Update", resource_type="notifications",
            resource_id=uuid4(),
            actor_user_id=current.id,
            field_changes=[],
            metadata={"kind": "mark_all_read", "rows_updated": affected},
            request=request,
        )
    db.commit()
    return {"rows_updated": affected}
