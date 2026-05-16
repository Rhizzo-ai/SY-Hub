"""Inbound webhooks router — Prompt 2.5A / Chat 19A.

Endpoint:
    POST /api/v1/inbound/postmark?secret=...   Postmark inbound webhook

Auth: shared secret in `?secret=` query string (compared with hmac.compare_digest).
Disabled in test mode by default (POSTMARK_INBOUND_ENABLED=false).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas.postmark import PostmarkInboundPayload
from app.services import postmark_webhook
from app.services.actual_errors import ActualError, PostmarkSignatureError

log = logging.getLogger(__name__)

router = APIRouter(tags=["inbound"])


@router.post("/inbound/postmark", status_code=202)
def postmark_inbound(
    payload: PostmarkInboundPayload,
    request: Request,
    secret: str = Query(default="", description="Shared inbound secret"),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.postmark_inbound_enabled:
        raise HTTPException(
            status_code=503,
            detail={"code": "postmark_disabled",
                    "message": "Postmark inbound is currently disabled."},
        )
    try:
        postmark_webhook.verify_secret(secret)
    except PostmarkSignatureError as exc:
        raise HTTPException(401, detail={"code": exc.code, "message": str(exc)})

    try:
        msg, jobs = postmark_webhook.handle_postmark_inbound(
            db, payload=payload,
        )
    except ActualError as exc:
        raise HTTPException(
            exc.http_status,
            detail={"code": exc.code, "message": str(exc)},
        )
    except Exception:
        log.exception("postmark_inbound: unexpected error")
        raise HTTPException(500, detail={"code": "inbound_failed",
                                         "message": "Internal error"})

    db.commit()
    return {
        "inbound_email_message_id": str(msg.id),
        "jobs_enqueued": [str(j.id) for j in jobs],
        "attachment_count": msg.attachment_count,
        "deduplicated": len(jobs) == 0 and msg.attachment_count > 0,
    }
