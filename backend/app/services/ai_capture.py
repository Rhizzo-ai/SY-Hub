"""AI capture pipeline — Prompt 2.5A / Chat 19A.

Flow:
    Postmark webhook -> inbound_email_message + ai_capture_jobs (Queued)
    APScheduler dispatcher -> claim Queued jobs -> Extracting
    Anthropic Claude call (or stub for tests) -> Awaiting_Review
    Operator promotes -> Completed (target_actual_id set)
    Operator discards or N retry failures -> Discarded / Failed

`AI_CAPTURE_MODEL='test-stub'` short-circuits to deterministic fixture output
(no live network call). Any other value is treated as an Anthropic model id.

MODEL CONFIG NOTE: When running against live Anthropic, callers must set
`ANTHROPIC_API_KEY` and either choose a vision-capable Claude model (e.g.
claude-3-5-sonnet-20241022) or accept that PDF binary attachments will be
rejected. Test path uses stub so no key required.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.auth.permissions import UserPermissions
from app.config import get_settings
from app.models.actuals import AICaptureJob, Actual, InboundEmailMessage
from app.models.user import User
from app.services.actual_errors import (
    CaptureJobNotFoundError, CaptureJobNotReadyError,
)
from app.services.audit import record_audit

log = logging.getLogger(__name__)

TERMINAL_CAPTURE_STATUSES = ("Completed", "Failed", "Discarded")

# Test stub returns this deterministic payload regardless of attachment content.
STUB_EXTRACTION = {
    "supplier_name": "Acme Supplies Ltd",
    "supplier_invoice_ref": "INV-STUB-001",
    "invoice_date": "2026-04-01",
    "description": "Stub: extraction unavailable in test mode",
    "net_amount": "100.00",
    "vat_amount": "20.00",
    "gross_amount": "120.00",
    "vat_rate_pct": "20.00",
}
STUB_CONFIDENCE = {
    "supplier_name": 0.95,
    "supplier_invoice_ref": 0.90,
    "invoice_date": 0.85,
    "net_amount": 0.99,
    "vat_amount": 0.99,
    "gross_amount": 0.99,
    "overall": 0.95,
}


# ---------- Pipeline entrypoints -------------------------------------

def enqueue_capture_job(
    db: Session,
    *,
    inbound_email_message_id: uuid.UUID,
    attachment_path: str,
) -> AICaptureJob:
    job = AICaptureJob(
        inbound_email_message_id=inbound_email_message_id,
        attachment_path=attachment_path,
        status="Queued",
    )
    db.add(job)
    db.flush()
    return job


def _claim_queued_job(db: Session) -> Optional[AICaptureJob]:
    """Atomically claim ONE Queued job and mark it Extracting.

    Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple dispatcher invocations
    don't grab the same row. Returns None when the queue is empty.
    """
    row = db.scalar(
        select(AICaptureJob)
        .where(AICaptureJob.status == "Queued")
        .order_by(AICaptureJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if row is None:
        return None
    row.status = "Extracting"
    row.attempts = (row.attempts or 0) + 1
    row.last_attempted_at = datetime.now(timezone.utc)
    db.flush()
    return row


def _extract_stub(job: AICaptureJob) -> dict:
    """Deterministic test stub. Returns the fixture extraction unchanged."""
    return {
        "data": dict(STUB_EXTRACTION),
        "confidence": dict(STUB_CONFIDENCE),
        "model": "test-stub",
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }


def _extract_anthropic(job: AICaptureJob, *, model: str, api_key: str) -> dict:
    """Live Anthropic call. Reads the attachment file, sends to Claude vision.

    Only called when AI_CAPTURE_MODEL != 'test-stub' AND api_key is non-empty.
    """
    # Lazy import: only loaded when live mode is active.
    try:
        import anthropic  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "anthropic package not installed; install or set AI_CAPTURE_MODEL=test-stub",
        ) from e

    path = Path(job.attachment_path)
    if not path.exists():
        raise RuntimeError(f"attachment file missing: {path}")

    content_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "image/jpeg"

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=2000,
        system=(
            "You are an invoice data extraction assistant. Extract the "
            "following fields and return STRICT JSON only: supplier_name, "
            "supplier_invoice_ref, invoice_date (YYYY-MM-DD), description, "
            "net_amount, vat_amount, gross_amount, vat_rate_pct. Include a "
            "second top-level key 'confidence' with 0-1 scores per field plus "
            "an 'overall' score."
        ),
        messages=[{
            "role": "user",
            "content": [
                {"type": "image" if media_type.startswith("image") else "document",
                 "source": {"type": "base64", "media_type": media_type,
                            "data": content_b64}},
                {"type": "text", "text": "Extract the invoice fields."},
            ],
        }],
    )
    raw_text = "".join(
        block.text for block in msg.content if hasattr(block, "text")
    )
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude returned non-JSON: {raw_text[:200]}") from e

    return {
        "data": parsed,
        "confidence": parsed.pop("confidence", {}),
        "model": model,
        "prompt_tokens": getattr(msg.usage, "input_tokens", None),
        "completion_tokens": getattr(msg.usage, "output_tokens", None),
    }


def process_one_job(db: Session) -> Optional[uuid.UUID]:
    """Claim + process the next Queued job. Called by the dispatcher.

    Returns the processed job id (or None when queue empty). On failure the
    job is moved to Failed if attempts >= max, otherwise back to Queued.
    """
    settings = get_settings()
    job = _claim_queued_job(db)
    if job is None:
        return None

    try:
        if settings.is_ai_stub or not settings.anthropic_api_key:
            result = _extract_stub(job)
        else:
            result = _extract_anthropic(
                job, model=settings.ai_capture_model,
                api_key=settings.anthropic_api_key,
            )
    except Exception as e:
        log.exception("AI capture job %s extraction failed", job.id)
        if (job.attempts or 0) >= settings.ai_capture_max_attempts:
            job.status = "Failed"
            job.last_error_message = str(e)[:1000]
        else:
            # Back into the queue for retry.
            job.status = "Queued"
            job.last_error_message = str(e)[:1000]
        db.flush()
        return job.id

    job.extracted_data = result["data"]
    job.confidence_scores = result["confidence"]
    job.model_used = result.get("model")
    job.prompt_tokens = result.get("prompt_tokens")
    job.completion_tokens = result.get("completion_tokens")
    job.status = "Awaiting_Review"
    job.last_error_message = None
    db.flush()
    return job.id


# ---------- Operator endpoints (promote / discard / retry) ------------

def _load_job(
    db: Session, job_id: uuid.UUID, user: User, perms: UserPermissions,
) -> AICaptureJob:
    job = db.get(AICaptureJob, job_id)
    if job is None:
        raise CaptureJobNotFoundError("Capture job not found")
    # AI capture jobs are admin-only (actuals.admin). The router enforces
    # this; the service trusts perms.
    return job


def list_capture_jobs(
    db: Session, *, status: Optional[str] = None, limit: int = 100, offset: int = 0,
) -> tuple[list[AICaptureJob], int]:
    from sqlalchemy import func
    q = select(AICaptureJob)
    if status:
        q = q.where(AICaptureJob.status == status)
    total = int(db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0)
    rows = db.scalars(
        q.order_by(AICaptureJob.created_at.desc())
        .offset(offset).limit(limit)
    ).all()
    return list(rows), total


def promote_capture_to_actual(
    db: Session,
    *,
    job_id: uuid.UUID,
    payload,  # PromoteCaptureToActualRequest
    user: User,
    perms: UserPermissions,
    request=None,
) -> tuple[AICaptureJob, Actual]:
    """Convert an Awaiting_Review job into a Draft actual.

    Operator overrides everything via the payload; the AI extraction is
    stored on the new actual as `ai_capture_metadata` for audit/diff.
    """
    from app.schemas.actuals import CreateActualRequest
    from app.services import actuals as actuals_service

    job = _load_job(db, job_id, user, perms)
    if job.status != "Awaiting_Review":
        raise CaptureJobNotReadyError(
            f"Job is {job.status}; only Awaiting_Review jobs can be promoted.",
        )

    # Build a CreateActualRequest from the operator-confirmed values.
    create_payload = CreateActualRequest(
        project_id=payload.project_id,
        budget_line_id=payload.budget_line_id,
        entity_id=payload.entity_id,
        source_type="Manual_Entry",  # AI capture creates a Manual_Entry shell
        transaction_date=payload.transaction_date,
        description=payload.description,
        net_amount=payload.net_amount,
        vat_amount=payload.vat_amount,
        vat_rate_pct=payload.vat_rate_pct,
        supplier_name_snapshot=payload.supplier_name_snapshot,
        supplier_invoice_ref=payload.supplier_invoice_ref,
        is_cis_applicable=payload.is_cis_applicable,
        cis_deduction_rate_pct=payload.cis_deduction_rate_pct,
        cis_labour_amount=payload.cis_labour_amount,
        cis_materials_amount=payload.cis_materials_amount,
        retention_rate_pct=payload.retention_rate_pct,
        retention_amount=payload.retention_amount,
    )

    actual = actuals_service.create_actual(
        db, payload=create_payload, user=user, perms=perms, request=request,
        source_overrides={
            "ai_capture_metadata": {
                "job_id": str(job.id),
                "extracted_data": job.extracted_data,
                "confidence_scores": job.confidence_scores,
                "model_used": job.model_used,
                "inbound_email_message_id": str(job.inbound_email_message_id),
            },
        },
    )

    job.status = "Completed"
    job.target_actual_id = actual.id
    db.flush()

    record_audit(
        db, action="Promote_From_Capture", resource_type="actual",
        resource_id=actual.id, actor_user_id=user.id,
        project_id=actual.project_id, entity_id=actual.entity_id,
        metadata={"capture_job_id": str(job.id),
                  "model_used": job.model_used},
        request=request,
    )
    return job, actual


def discard_capture(
    db: Session, *, job_id: uuid.UUID, reason: str, user: User,
    perms: UserPermissions, request=None,
) -> AICaptureJob:
    job = _load_job(db, job_id, user, perms)
    if job.status in TERMINAL_CAPTURE_STATUSES:
        raise CaptureJobNotReadyError(f"Job is already {job.status}")
    job.status = "Discarded"
    job.last_error_message = f"Discarded by {user.email}: {reason}"[:1000]
    db.flush()
    record_audit(
        db, action="Delete", resource_type="ai_capture_job",
        resource_id=job.id, actor_user_id=user.id,
        metadata={"reason": reason},
        request=request,
    )
    return job


def retry_capture(
    db: Session, *, job_id: uuid.UUID, user: User, perms: UserPermissions,
    request=None,
) -> AICaptureJob:
    job = _load_job(db, job_id, user, perms)
    if job.status != "Failed":
        raise CaptureJobNotReadyError(
            f"Only Failed jobs can be retried; job is {job.status}",
        )
    job.status = "Queued"
    job.last_error_message = None
    db.flush()
    record_audit(
        db, action="Update", resource_type="ai_capture_job",
        resource_id=job.id, actor_user_id=user.id,
        metadata={"retried_at": datetime.now(timezone.utc).isoformat()},
        request=request,
    )
    return job
