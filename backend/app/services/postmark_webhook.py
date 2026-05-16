"""Postmark inbound webhook handling — Prompt 2.5A / Chat 19A.

Security: we authenticate inbound webhooks via a shared secret in the URL
query string (`?secret=...`). Postmark supports basic-auth too but the
shared-secret model is simpler to implement and rotates atomically via env
var. The secret is compared with `hmac.compare_digest`.

Disabled in test mode by default (POSTMARK_INBOUND_ENABLED=false).
"""
from __future__ import annotations

import base64
import hmac
import logging
import os
import uuid
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.actuals import AICaptureJob, InboundEmailMessage
from app.services.actual_errors import PostmarkSignatureError
from app.services.ai_capture import enqueue_capture_job

log = logging.getLogger(__name__)

# Mime types we'll bother running through AI extraction. Other attachments are
# stored (so the operator can review) but no job is enqueued.
EXTRACTABLE_MIME_TYPES = frozenset({
    "application/pdf",
    "image/jpeg", "image/png", "image/gif", "image/webp",
})


def verify_secret(provided: Optional[str]) -> None:
    """Constant-time compare against POSTMARK_INBOUND_SECRET.

    Raises PostmarkSignatureError on mismatch.
    """
    expected = get_settings().postmark_inbound_secret
    if not expected:
        raise PostmarkSignatureError("POSTMARK_INBOUND_SECRET not configured")
    if not provided:
        raise PostmarkSignatureError("missing secret query parameter")
    if not hmac.compare_digest(expected.encode(), provided.encode()):
        raise PostmarkSignatureError("secret mismatch")


def _ensure_inbound_dir() -> Path:
    p = Path(get_settings().ai_capture_inbound_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _parse_received_at(raw: Optional[str]) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def handle_postmark_inbound(
    db: Session,
    *,
    payload,  # PostmarkInboundPayload
) -> tuple[InboundEmailMessage, list[AICaptureJob]]:
    """Process a Postmark inbound payload.

    Idempotent on `MessageID`: returns the existing row + empty jobs list if
    seen before. Otherwise stores the message, writes attachments to disk,
    and enqueues one AI capture job per extractable attachment.
    """
    # Idempotency check
    existing = db.scalar(
        select(InboundEmailMessage).where(
            InboundEmailMessage.postmark_message_id == payload.MessageID
        )
    )
    if existing is not None:
        log.info("postmark inbound dedup: MessageID=%s already stored",
                 payload.MessageID)
        return existing, []

    inbound_dir = _ensure_inbound_dir()
    msg_subdir = inbound_dir / payload.MessageID.replace("/", "_")
    msg_subdir.mkdir(parents=True, exist_ok=True)

    msg = InboundEmailMessage(
        postmark_message_id=payload.MessageID,
        from_email=payload.From,
        to_email=payload.To or "",
        subject=(payload.Subject or "")[:998],
        received_at=_parse_received_at(payload.Date),
        raw_email_path=str(msg_subdir),
        attachment_count=len(payload.Attachments),
    )
    db.add(msg)
    db.flush()

    jobs: list[AICaptureJob] = []
    for idx, att in enumerate(payload.Attachments):
        # Decode base64
        try:
            content = base64.b64decode(att.Content)
        except Exception:
            log.warning("failed to decode attachment %s of message %s",
                        att.Name, payload.MessageID)
            continue
        safe_name = att.Name.replace("/", "_")[:200]
        file_path = msg_subdir / f"{idx:03d}__{safe_name}"
        file_path.write_bytes(content)

        if att.ContentType in EXTRACTABLE_MIME_TYPES:
            job = enqueue_capture_job(
                db,
                inbound_email_message_id=msg.id,
                attachment_path=str(file_path),
            )
            jobs.append(job)
        else:
            log.info("postmark inbound: skipping non-extractable attachment %s (%s)",
                     att.Name, att.ContentType)

    db.flush()
    return msg, jobs
