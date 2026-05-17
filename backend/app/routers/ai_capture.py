"""AI capture admin router — Prompt 2.5A / Chat 19A.

All endpoints require `actuals.admin` permission (sensitive).

Endpoints:
    GET    /api/v1/ai-capture-jobs                     list (status filter)
    GET    /api/v1/ai-capture-jobs/{job_id}            detail
    POST   /api/v1/ai-capture-jobs/{job_id}/promote    -> Completed + create Draft actual
    POST   /api/v1/ai-capture-jobs/{job_id}/discard    -> Discarded
    POST   /api/v1/ai-capture-jobs/{job_id}/retry      Failed -> Queued
"""
from __future__ import annotations

import uuid
from datetime import date as date_type, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.actuals import AICaptureJob
from app.models.user import User
from app.schemas.actuals import (
    DiscardCaptureRequest, PromoteCaptureToActualRequest, RetryCaptureRequest,
)
from app.services import ai_capture as cap_svc
from app.services.actual_errors import ActualError

router = APIRouter(tags=["ai-capture"])


def _serialise_job(j: AICaptureJob) -> dict[str, Any]:
    return {
        "id": str(j.id),
        "inbound_email_message_id": str(j.inbound_email_message_id),
        "attachment_path": j.attachment_path,
        "status": j.status,
        "attempts": j.attempts,
        "last_attempted_at": (
            j.last_attempted_at.isoformat() if j.last_attempted_at else None
        ),
        "last_error_message": j.last_error_message,
        "extracted_data": j.extracted_data,
        "confidence_scores": j.confidence_scores,
        "suggested_entity_id": str(j.suggested_entity_id) if j.suggested_entity_id else None,
        "suggested_project_id": str(j.suggested_project_id) if j.suggested_project_id else None,
        "suggested_cost_code_id": (
            str(j.suggested_cost_code_id) if j.suggested_cost_code_id else None
        ),
        "target_actual_id": str(j.target_actual_id) if j.target_actual_id else None,
        "model_used": j.model_used,
        "prompt_tokens": j.prompt_tokens,
        "completion_tokens": j.completion_tokens,
        "cost_pence": j.cost_pence,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "updated_at": j.updated_at.isoformat() if j.updated_at else None,
    }


def _raise_for(exc: ActualError):
    raise HTTPException(
        exc.http_status,
        detail={"code": exc.code, "message": str(exc), "details": exc.details},
    )


@router.get("/ai-capture-jobs")
def list_capture_jobs(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.admin")),
    db: Session = Depends(get_db),
):
    rows, total = cap_svc.list_capture_jobs(
        db, status=status, limit=limit, offset=offset,
    )
    return {
        "items": [_serialise_job(j) for j in rows],
        "count": len(rows),
        "total": total,
    }


@router.get("/ai-capture-jobs/stats")
def get_capture_stats(
    from_date: Optional[date_type] = Query(
        default=None, description="ISO date YYYY-MM-DD, inclusive"
    ),
    to_date: Optional[date_type] = Query(
        default=None, description="ISO date YYYY-MM-DD, inclusive"
    ),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("ai_capture.view_costs")),
    db: Session = Depends(get_db),
):
    """Aggregated AI capture statistics for a date range — Chat 20 §R1.3 (B38).

    All monetary fields are returned as integer pence to avoid float
    round-tripping. Frontend renders as £ via /100 division.

    Date bucketing uses Europe/London tz (NOT UTC) so the day boundaries
    match what Louise expects in the dashboard (L10).

    NOTE: This route MUST be declared before `/ai-capture-jobs/{job_id}`,
    otherwise FastAPI matches "stats" as a UUID job_id and 422s before
    the perm dep / body even run.
    """
    today = datetime.now(timezone.utc).astimezone().date()
    if to_date is None:
        to_date = today
    if from_date is None:
        from_date = to_date - timedelta(days=29)  # inclusive 30-day window

    if from_date > to_date:
        raise HTTPException(422, detail={
            "code": "invalid_date_range",
            "message": "from_date must be <= to_date",
        })
    if to_date > today:
        raise HTTPException(422, detail={
            "code": "future_date",
            "message": "to_date cannot be in the future",
        })

    return cap_svc.compute_capture_stats(
        db, from_date=from_date, to_date=to_date,
    )


@router.get("/ai-capture-jobs/{job_id}")
def get_capture_job(
    job_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.admin")),
    db: Session = Depends(get_db),
):
    job = db.get(AICaptureJob, job_id)
    if job is None:
        raise HTTPException(404, detail={"code": "capture_job_not_found",
                                         "message": "Capture job not found"})
    return _serialise_job(job)


@router.post("/ai-capture-jobs/{job_id}/promote")
def promote_job(
    job_id: uuid.UUID,
    body: PromoteCaptureToActualRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.admin")),
    db: Session = Depends(get_db),
):
    try:
        job, actual = cap_svc.promote_capture_to_actual(
            db, job_id=job_id, payload=body, user=current, perms=perms,
            request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(job)
    db.refresh(actual)
    return {
        "job": _serialise_job(job),
        "actual_id": str(actual.id),
        "actual_status": actual.status,
    }


@router.post("/ai-capture-jobs/{job_id}/discard")
def discard_job(
    job_id: uuid.UUID,
    body: DiscardCaptureRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.admin")),
    db: Session = Depends(get_db),
):
    try:
        job = cap_svc.discard_capture(
            db, job_id=job_id, reason=body.reason,
            user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(job)
    return _serialise_job(job)


@router.post("/ai-capture-jobs/{job_id}/retry")
def retry_job(
    job_id: uuid.UUID,
    body: RetryCaptureRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.admin")),
    db: Session = Depends(get_db),
):
    try:
        job = cap_svc.retry_capture(
            db, job_id=job_id, user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(job)
    return _serialise_job(job)



# ---------------------------------------------------------------------
# 6. Attachment download — Chat 19C §R5.1 C1
# ---------------------------------------------------------------------
#
# Streams the file bytes referenced by job.attachment_path. Used by the
# AI Capture Review surface (AttachmentPreview component) so reviewers
# can see the source document inline before promoting / discarding the
# job.
#
# Gated on `actuals.admin` to match the other 5 endpoints in this router
# (sensitive surface — extraction artefacts may contain supplier PII).
# Inline disposition; MIME inferred from the file extension, with a safe
# fallback to application/octet-stream. 404 if job is missing, 410 if the
# attachment file no longer exists on disk (i.e. row references a dead
# path — surfaced to the operator rather than swallowed).

_ATTACHMENT_MIME_BY_EXT: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


@router.get("/ai-capture-jobs/{job_id}/attachment")
def download_capture_attachment(
    job_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.admin")),
    db: Session = Depends(get_db),
):
    job = db.get(AICaptureJob, job_id)
    if job is None:
        raise HTTPException(404, "Capture job not found")
    path = Path(job.attachment_path)
    if not path.exists():
        raise HTTPException(410, "Attachment file no longer exists on disk")
    mime = _ATTACHMENT_MIME_BY_EXT.get(
        path.suffix.lower(), "application/octet-stream",
    )
    return FileResponse(path, media_type=mime, filename=path.name)
