"""Domain exceptions for the actuals module — Prompt 2.5A / Chat 19A.

Routers translate these to HTTP responses (see app/routers/actuals.py).
Keep these focused — DO NOT subclass HTTPException; that creates a circular
import when the service is used from a job/scheduler context.
"""
from __future__ import annotations


class ActualError(Exception):
    """Base for all actuals domain errors."""

    http_status: int = 400
    code: str = "actual_error"

    def __init__(self, message: str, *, code: str | None = None,
                 details: dict | None = None):
        super().__init__(message)
        if code:
            self.code = code
        self.details = details or {}


class ActualNotFoundError(ActualError):
    http_status = 404
    code = "actual_not_found"


class InvalidTransitionError(ActualError):
    http_status = 409
    code = "invalid_status_transition"


class ImmutableFieldError(ActualError):
    http_status = 409
    code = "immutable_field"


class BudgetLineLockedError(ActualError):
    http_status = 409
    code = "budget_line_locked"


class BudgetLineNotInProjectError(ActualError):
    http_status = 400
    code = "budget_line_project_mismatch"


class CommitmentLinkError(ActualError):
    """A bill's linked_commitment_id is invalid — it does not reference an
    existing PurchaseOrderLine, or that PO line sits on a different budget line
    than the bill. Mapped to 422 (validation error), consistent with other
    actuals validation failures (Chat 63 / C1-back)."""

    http_status = 422
    code = "commitment_link_invalid"


class DuplicateExternalIdError(ActualError):
    http_status = 409
    code = "duplicate_external_id"


class AttachmentNotFoundError(ActualError):
    http_status = 404
    code = "attachment_not_found"


class AttachmentTooLargeError(ActualError):
    http_status = 413
    code = "attachment_too_large"


class AttachmentTypeNotAllowedError(ActualError):
    http_status = 415
    code = "attachment_type_not_allowed"


class MissingRequiredFieldError(ActualError):
    http_status = 400
    code = "missing_required_field"


class CaptureJobNotFoundError(ActualError):
    http_status = 404
    code = "capture_job_not_found"


class CaptureJobNotReadyError(ActualError):
    http_status = 409
    code = "capture_job_not_ready"


class PostmarkSignatureError(ActualError):
    http_status = 401
    code = "postmark_signature_invalid"
