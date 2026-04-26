"""NotificationService — Prompt 1.7.

Synchronous, single-process dispatch:

1. If `expires_at` not provided, default to created_at + auto_expire_days.
2. Insert row.
3. Priority High|Critical → call ConsoleEmailProvider; stamp email_sent.
4. SMS branch is no-op (logs `# TODO[SMS]`); sms_sent stays false.
5. record_audit Create.

No queue, no worker. Multi-channel + queue are explicit Polish Pass items.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.notifications import (
    Notification,
    NOTIFICATION_PRIORITIES,
    NOTIFICATION_TYPES,
)
from app.services import system_config as system_config_service
from app.services.audit import record_audit
from app.services.email import get_email_provider


log = logging.getLogger("syhomes.notifications")


# Email provider is resolved lazily so tests can swap it via env.
_DEFAULT_AUTO_EXPIRE_DAYS = 30


def _default_expires_at() -> datetime:
    days = system_config_service.get_or_default(
        "notification.auto_expire_days", _DEFAULT_AUTO_EXPIRE_DAYS,
    )
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = _DEFAULT_AUTO_EXPIRE_DAYS
    return datetime.now(timezone.utc) + timedelta(days=days)


def dispatch(
    db: Session,
    *,
    recipient_user_id: UUID,
    notification_type: str,
    title: str,
    body: str,
    priority: str = "Normal",
    related_resource_type: Optional[str] = None,
    related_resource_id: Optional[UUID] = None,
    action_url: Optional[str] = None,
    action_label: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    request=None,
    actor_user_id: Optional[UUID] = None,
) -> Notification:
    """Insert a notification row, optionally email, audit Create.

    `actor_user_id` is the user who CAUSED the notification (e.g.
    super_admin who overrode a stage). It's only used for the audit row;
    if omitted, recipient_user_id is used.
    """
    if notification_type not in NOTIFICATION_TYPES:
        raise ValueError(f"Invalid notification_type: {notification_type!r}")
    if priority not in NOTIFICATION_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority!r}")

    if expires_at is None:
        expires_at = _default_expires_at()

    n = Notification(
        recipient_user_id=recipient_user_id,
        notification_type=notification_type,
        priority=priority,
        title=title,
        body=body,
        related_resource_type=related_resource_type,
        related_resource_id=related_resource_id,
        action_url=action_url,
        action_label=action_label,
        expires_at=expires_at,
    )
    db.add(n)
    db.flush()

    # Email channel — High and Critical only.
    if priority in ("High", "Critical"):
        try:
            from app.models.user import User
            user = db.get(User, recipient_user_id)
            to_address = user.email if user else None
            if to_address:
                provider = get_email_provider()
                # Use a minimal plain-text body; rich templates → Polish Pass.
                full_body = body
                if action_url:
                    full_body = f"{body}\n\nAction: {action_url}"
                provider.send(
                    to=to_address,
                    subject=f"[{priority}] {title}",
                    html=f"<pre>{full_body}</pre>",
                    text=full_body,
                    template_id="notification_email",
                )
                n.email_sent = True
                n.email_sent_at = datetime.now(timezone.utc)
        except Exception:
            log.exception(
                "notification email failed (notification_id=%s); "
                "row persisted without email", n.id,
            )

    # SMS channel — scaffold only.
    log.debug(
        "# TODO[SMS]: phone verification + Twilio integration deferred "
        "(notification_id=%s, type=%s, priority=%s)",
        n.id, notification_type, priority,
    )

    record_audit(
        db, action="Create", resource_type="notifications",
        resource_id=n.id,
        actor_user_id=actor_user_id or recipient_user_id,
        metadata={
            "notification_type": notification_type,
            "priority": priority,
            "recipient_user_id": str(recipient_user_id),
            "email_sent": bool(n.email_sent),
        },
        request=request,
    )
    return n


def safe_dispatch(*args, **kwargs) -> Optional[Notification]:
    """Dispatch wrapper that NEVER raises into the calling business path.

    Used by retro-wired sites (planning expiry sweep, stage override,
    auth events). A notification failure must not bring down the
    triggering write — log and continue.
    """
    try:
        return dispatch(*args, **kwargs)
    except Exception:
        log.exception("safe_dispatch swallowed exception")
        return None
