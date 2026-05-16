"""Actual attachments service — Prompt 2.5A / Chat 19A.

MVP: store uploaded files on the local filesystem under settings.actuals_attachments_dir.
Track 5 will migrate to S3 + signed URLs.

Whitelist: PDF, JPG/PNG, common office formats. Reject .exe etc.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import IO, Optional

from sqlalchemy.orm import Session

from app.auth.permissions import UserPermissions
from app.config import get_settings
from app.models.actuals import Actual, ActualAttachment
from app.models.user import User
from app.services.actual_errors import (
    AttachmentNotFoundError, AttachmentTooLargeError,
    AttachmentTypeNotAllowedError, ActualNotFoundError,
)
from app.services.audit import record_audit
from app.services.actuals import _load_actual, _log_change

log = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = frozenset({
    "application/pdf",
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv", "text/plain",
})


def _ensure_storage_dir() -> Path:
    p = Path(get_settings().actuals_attachments_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _safe_filename(name: str) -> str:
    # Strip path traversal etc. Keep extension intact.
    base = os.path.basename(name)
    # Replace unprintable chars with '_'
    out = "".join(ch if ch.isprintable() and ch not in "\\/\"\0" else "_" for ch in base)
    return out[:500]


def add_attachment(
    db: Session,
    *,
    actual_id: uuid.UUID,
    file_stream: IO[bytes],
    original_filename: str,
    content_type: str,
    source: str,
    user: User,
    perms: UserPermissions,
    request=None,
) -> ActualAttachment:
    a = _load_actual(db, actual_id, user, perms)

    if content_type not in ALLOWED_MIME_TYPES:
        raise AttachmentTypeNotAllowedError(
            f"content type {content_type!r} not allowed",
        )

    max_bytes = get_settings().actuals_attachment_max_bytes
    data = file_stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise AttachmentTooLargeError(
            f"file exceeds {max_bytes} bytes",
        )
    if len(data) == 0:
        raise AttachmentTooLargeError("empty file rejected")

    storage_dir = _ensure_storage_dir()
    sub_dir = storage_dir / str(a.id)
    sub_dir.mkdir(parents=True, exist_ok=True)
    new_id = uuid.uuid4()
    safe = _safe_filename(original_filename)
    file_path = sub_dir / f"{new_id}__{safe}"
    file_path.write_bytes(data)

    row = ActualAttachment(
        id=new_id,
        actual_id=a.id,
        file_path=str(file_path),
        file_type=content_type,
        file_size_bytes=len(data),
        original_filename=safe,
        source=source,
        uploaded_by_user_id=user.id,
    )
    db.add(row)
    db.flush()

    _log_change(
        db, actual_id=a.id, event_type="Attachment_Added",
        actor_user_id=user.id,
        payload={"attachment_id": str(row.id),
                 "filename": safe, "size": len(data)},
    )
    record_audit(
        db, action="Add_Attachment", resource_type="actual",
        resource_id=a.id, actor_user_id=user.id,
        project_id=a.project_id, entity_id=a.entity_id,
        metadata={"attachment_id": str(row.id), "filename": safe,
                  "size_bytes": len(data)},
        request=request,
    )
    return row


def remove_attachment(
    db: Session,
    *,
    actual_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
    request=None,
) -> None:
    a = _load_actual(db, actual_id, user, perms)
    att = db.get(ActualAttachment, attachment_id)
    if att is None or att.actual_id != a.id:
        raise AttachmentNotFoundError("Attachment not found")
    # Best-effort filesystem cleanup
    try:
        Path(att.file_path).unlink(missing_ok=True)
    except OSError:
        log.exception("Failed to delete attachment file %s", att.file_path)

    db.delete(att)
    db.flush()

    _log_change(
        db, actual_id=a.id, event_type="Attachment_Removed",
        actor_user_id=user.id,
        payload={"attachment_id": str(attachment_id),
                 "filename": att.original_filename},
    )
    record_audit(
        db, action="Remove_Attachment", resource_type="actual",
        resource_id=a.id, actor_user_id=user.id,
        project_id=a.project_id, entity_id=a.entity_id,
        metadata={"attachment_id": str(attachment_id),
                  "filename": att.original_filename},
        request=request,
    )


def list_attachments(
    db: Session,
    *,
    actual_id: uuid.UUID,
    user: User,
    perms: UserPermissions,
) -> list[ActualAttachment]:
    a = _load_actual(db, actual_id, user, perms)
    from sqlalchemy import select
    return list(db.scalars(
        select(ActualAttachment)
        .where(ActualAttachment.actual_id == a.id)
        .order_by(ActualAttachment.uploaded_at.desc())
    ).all())
