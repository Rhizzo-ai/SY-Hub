"""Actuals API — Prompt 2.5A / Chat 19A.

Mounts under /api/v1. 15 endpoints:

  Project-scoped list:
    GET    /projects/{project_id}/actuals                     list actuals

  Generic list + create:
    GET    /actuals                                           list (filters)
    POST   /actuals                                           create Draft   [actuals.create]

  Single actual:
    GET    /actuals/{actual_id}                               detail
    PATCH  /actuals/{actual_id}                               edit Draft     [actuals.edit]
    DELETE /actuals/{actual_id}                               delete Draft   [actuals.edit]
    GET    /actuals/{actual_id}/change-log                    change history

  State transitions:
    POST   /actuals/{actual_id}/post                          Draft → Posted [actuals.post]
    POST   /actuals/{actual_id}/mark-paid                     Posted → Paid  [actuals.approve]
    POST   /actuals/{actual_id}/void                          → Void         [actuals.approve]
    POST   /actuals/{actual_id}/dispute                       Posted → Disputed [actuals.edit]
    POST   /actuals/{actual_id}/undispute                     Disputed → Posted [actuals.edit]
    POST   /actuals/{actual_id}/release-retention             retention release [actuals.approve]

  Attachments:
    GET    /actuals/{actual_id}/attachments                   list
    POST   /actuals/{actual_id}/attachments                   multipart upload [actuals.edit]
    DELETE /actuals/{actual_id}/attachments/{att_id}          remove         [actuals.edit]

Tenant scoping: Pattern α via _visible_project_ids (same as budgets/appraisals).
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile,
    Response,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.actuals import Actual, ActualAttachment, ActualChangeLog
from app.models.user import User
from app.schemas.actuals import (
    ActualsListFilters, CreateActualRequest, DisputeActualRequest,
    MarkPaidRequest, PostActualRequest, ReleaseRetentionRequest,
    UndisputeActualRequest, UpdateDraftActualRequest, VoidActualRequest,
)
from app.services import actuals as actuals_svc
from app.services import actual_attachments as att_svc
from app.services.actual_errors import ActualError


router = APIRouter(tags=["actuals"])


def _actuals_filters_dep(
    project_id: Optional[uuid.UUID] = Query(default=None),
    budget_line_id: Optional[uuid.UUID] = Query(default=None),
    entity_id: Optional[uuid.UUID] = Query(default=None),
    status: Optional[str] = Query(default=None),
    source_type: Optional[str] = Query(default=None),
    supplier_id: Optional[uuid.UUID] = Query(default=None),
    transaction_date_from: Optional[str] = Query(default=None),
    transaction_date_to: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ActualsListFilters:
    """D32 — wraps `ActualsListFilters` construction so that a
    `ValidationError` raised from a `@field_validator` (e.g. comma-separated
    status containing an invalid value) is converted to a clean
    `HTTPException(422)` instead of escaping the dependency stack and
    surfacing as a 500.
    """
    try:
        return ActualsListFilters(
            project_id=project_id,
            budget_line_id=budget_line_id,
            entity_id=entity_id,
            status=status,
            source_type=source_type,
            supplier_id=supplier_id,
            transaction_date_from=transaction_date_from,
            transaction_date_to=transaction_date_to,
            limit=limit,
            offset=offset,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_url=False, include_context=False),
        ) from exc


# ---------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------

def _raise_for(exc: ActualError):
    raise HTTPException(
        exc.http_status,
        detail={"code": exc.code, "message": str(exc), "details": exc.details},
    )


# ---------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------

def _serialise_actual(a: Actual, *, include_sensitive: bool) -> dict:
    """Build the response shape. `include_sensitive` gates retention/CIS detail.

    The retention/CIS *header* fields are always shown so users see status;
    `include_sensitive` adds the calculated amounts.
    """
    base: dict[str, Any] = {
        "id": str(a.id),
        "project_id": str(a.project_id),
        "budget_line_id": str(a.budget_line_id),
        "entity_id": str(a.entity_id),
        "source_type": a.source_type,
        "source_reference": a.source_reference,
        "external_id": a.external_id,
        "transaction_date": a.transaction_date.isoformat() if a.transaction_date else None,
        "posting_date": a.posting_date.isoformat() if a.posting_date else None,
        "description": a.description,
        "net_amount": str(a.net_amount),
        "vat_amount": str(a.vat_amount),
        "gross_amount": str(a.gross_amount),
        "vat_rate_pct": str(a.vat_rate_pct),
        "is_vat_recoverable": a.is_vat_recoverable,
        "currency": a.currency,
        "exchange_rate": str(a.exchange_rate) if a.exchange_rate is not None else None,
        "supplier_id": str(a.supplier_id) if a.supplier_id else None,
        "supplier_name_snapshot": a.supplier_name_snapshot,
        "supplier_invoice_ref": a.supplier_invoice_ref,
        "is_cis_applicable": a.is_cis_applicable,
        "retention_released": a.retention_released,
        "linked_commitment_id": str(a.linked_commitment_id) if a.linked_commitment_id else None,
        "related_subcontract_id": str(a.related_subcontract_id) if a.related_subcontract_id else None,
        "is_reconciled_to_xero": a.is_reconciled_to_xero,
        "status": a.status,
        "posted_at": a.posted_at.isoformat() if a.posted_at else None,
        "paid_date": a.paid_date.isoformat() if a.paid_date else None,
        "payment_reference": a.payment_reference,
        "disputed_at": a.disputed_at.isoformat() if a.disputed_at else None,
        "voided_at": a.voided_at.isoformat() if a.voided_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
    if include_sensitive:
        base.update({
            "cis_deduction_rate_pct": (
                str(a.cis_deduction_rate_pct) if a.cis_deduction_rate_pct is not None else None
            ),
            "cis_labour_amount": (
                str(a.cis_labour_amount) if a.cis_labour_amount is not None else None
            ),
            "cis_materials_amount": (
                str(a.cis_materials_amount) if a.cis_materials_amount is not None else None
            ),
            "cis_deduction_amount": (
                str(a.cis_deduction_amount) if a.cis_deduction_amount is not None else None
            ),
            "retention_rate_pct": (
                str(a.retention_rate_pct) if a.retention_rate_pct is not None else None
            ),
            "retention_amount": (
                str(a.retention_amount) if a.retention_amount is not None else None
            ),
            "retention_release_date": (
                a.retention_release_date.isoformat()
                if a.retention_release_date else None
            ),
            "reconciliation_variance": (
                str(a.reconciliation_variance) if a.reconciliation_variance is not None else None
            ),
            "dispute_reason": a.dispute_reason,
            "void_reason": a.void_reason,
            "ai_capture_metadata": a.ai_capture_metadata,
        })
    return base


def _serialise_change_log(c: ActualChangeLog) -> dict:
    return {
        "id": str(c.id),
        "actual_id": str(c.actual_id),
        "event_type": c.event_type,
        "actor_user_id": str(c.actor_user_id) if c.actor_user_id else None,
        "event_payload": c.event_payload,
        "occurred_at": c.occurred_at.isoformat() if c.occurred_at else None,
    }


def _serialise_attachment(att: ActualAttachment) -> dict:
    return {
        "id": str(att.id),
        "actual_id": str(att.actual_id),
        "original_filename": att.original_filename,
        "file_type": att.file_type,
        "file_size_bytes": att.file_size_bytes,
        "source": att.source,
        "uploaded_by_user_id": str(att.uploaded_by_user_id) if att.uploaded_by_user_id else None,
        "uploaded_at": att.uploaded_at.isoformat() if att.uploaded_at else None,
    }


def _include_sensitive(perms: UserPermissions) -> bool:
    return perms.has("actuals.view_sensitive") or perms.is_super_admin


# ---------------------------------------------------------------------
# 1. List (generic + project-scoped)
# ---------------------------------------------------------------------

@router.get("/actuals")
def list_actuals(
    filters: ActualsListFilters = Depends(_actuals_filters_dep),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.view")),
    db: Session = Depends(get_db),
):
    rows, total = actuals_svc.list_actuals(
        db, filters=filters, user=current, perms=perms,
    )
    inc = _include_sensitive(perms)
    return {
        "items": [_serialise_actual(a, include_sensitive=inc) for a in rows],
        "count": len(rows),
        "total": total,
        "limit": filters.limit,
        "offset": filters.offset,
    }


@router.get("/projects/{project_id}/actuals")
def list_project_actuals(
    project_id: uuid.UUID,
    status: Optional[str] = Query(default=None),
    budget_line_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.view")),
    db: Session = Depends(get_db),
):
    # D32 — wrap mid-handler model construction so a `field_validator`
    # raise (e.g. invalid comma-separated status) surfaces as 422 rather
    # than 500. B34 closure.
    try:
        filters = ActualsListFilters(
            project_id=project_id, status=status,
            budget_line_id=budget_line_id,
            limit=limit, offset=offset,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_url=False, include_context=False),
        ) from exc
    rows, total = actuals_svc.list_actuals(
        db, filters=filters, user=current, perms=perms,
    )
    inc = _include_sensitive(perms)
    return {
        "project_id": str(project_id),
        "items": [_serialise_actual(a, include_sensitive=inc) for a in rows],
        "count": len(rows),
        "total": total,
    }


# ---------------------------------------------------------------------
# 2. Create + detail + update + delete
# ---------------------------------------------------------------------

@router.post("/actuals", status_code=201)
def create_actual(
    body: CreateActualRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.create")),
    db: Session = Depends(get_db),
):
    try:
        a = actuals_svc.create_actual(
            db, payload=body, user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(a)
    return _serialise_actual(a, include_sensitive=_include_sensitive(perms))


@router.get("/actuals/{actual_id}")
def get_actual(
    actual_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.view")),
    db: Session = Depends(get_db),
):
    try:
        a = actuals_svc._load_actual(db, actual_id, current, perms)
    except ActualError as exc:
        _raise_for(exc)
    return _serialise_actual(a, include_sensitive=_include_sensitive(perms))


@router.patch("/actuals/{actual_id}")
def update_actual(
    actual_id: uuid.UUID,
    body: UpdateDraftActualRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.edit")),
    db: Session = Depends(get_db),
):
    try:
        a = actuals_svc.update_draft_actual(
            db, actual_id=actual_id, payload=body,
            user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(a)
    return _serialise_actual(a, include_sensitive=_include_sensitive(perms))


@router.delete("/actuals/{actual_id}", status_code=204)
def delete_actual(
    actual_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.edit")),
    db: Session = Depends(get_db),
):
    try:
        actuals_svc.delete_draft_actual(
            db, actual_id=actual_id, user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    return Response(status_code=204)


@router.get("/actuals/{actual_id}/change-log")
def get_change_log(
    actual_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = actuals_svc.get_change_log(
            db, actual_id=actual_id, user=current, perms=perms,
        )
    except ActualError as exc:
        _raise_for(exc)
    return {
        "actual_id": str(actual_id),
        "items": [_serialise_change_log(c) for c in rows],
        "count": len(rows),
    }


# ---------------------------------------------------------------------
# 3. State transitions
# ---------------------------------------------------------------------

@router.post("/actuals/{actual_id}/post")
def post_actual(
    actual_id: uuid.UUID,
    body: PostActualRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.edit")),
    db: Session = Depends(get_db),
):
    try:
        a = actuals_svc.post_actual(
            db, actual_id=actual_id, user=current, perms=perms,
            request=request, notes=body.notes,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(a)
    return _serialise_actual(a, include_sensitive=_include_sensitive(perms))


@router.post("/actuals/{actual_id}/mark-paid")
def mark_paid(
    actual_id: uuid.UUID,
    body: MarkPaidRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.approve")),
    db: Session = Depends(get_db),
):
    try:
        a = actuals_svc.mark_paid(
            db, actual_id=actual_id, paid_date=body.paid_date,
            payment_reference=body.payment_reference,
            user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(a)
    return _serialise_actual(a, include_sensitive=_include_sensitive(perms))


@router.post("/actuals/{actual_id}/void")
def void_actual(
    actual_id: uuid.UUID,
    body: VoidActualRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.approve")),
    db: Session = Depends(get_db),
):
    try:
        a = actuals_svc.void_actual(
            db, actual_id=actual_id, void_reason=body.void_reason,
            user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(a)
    return _serialise_actual(a, include_sensitive=_include_sensitive(perms))


@router.post("/actuals/{actual_id}/dispute")
def dispute_actual(
    actual_id: uuid.UUID,
    body: DisputeActualRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.edit")),
    db: Session = Depends(get_db),
):
    try:
        a = actuals_svc.dispute_actual(
            db, actual_id=actual_id, dispute_reason=body.dispute_reason,
            user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(a)
    return _serialise_actual(a, include_sensitive=_include_sensitive(perms))


@router.post("/actuals/{actual_id}/undispute")
def undispute_actual(
    actual_id: uuid.UUID,
    body: UndisputeActualRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.edit")),
    db: Session = Depends(get_db),
):
    try:
        a = actuals_svc.undispute_actual(
            db, actual_id=actual_id, user=current, perms=perms,
            request=request, notes=body.notes,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(a)
    return _serialise_actual(a, include_sensitive=_include_sensitive(perms))


@router.post("/actuals/{actual_id}/release-retention")
def release_retention(
    actual_id: uuid.UUID,
    body: ReleaseRetentionRequest,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.approve")),
    db: Session = Depends(get_db),
):
    try:
        a = actuals_svc.release_retention(
            db, actual_id=actual_id,
            retention_release_date=body.retention_release_date,
            user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    db.refresh(a)
    return _serialise_actual(a, include_sensitive=_include_sensitive(perms))


# ---------------------------------------------------------------------
# 4. Attachments
# ---------------------------------------------------------------------

@router.get("/actuals/{actual_id}/attachments")
def list_attachments(
    actual_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.view")),
    db: Session = Depends(get_db),
):
    try:
        rows = att_svc.list_attachments(
            db, actual_id=actual_id, user=current, perms=perms,
        )
    except ActualError as exc:
        _raise_for(exc)
    return {
        "actual_id": str(actual_id),
        "items": [_serialise_attachment(a) for a in rows],
        "count": len(rows),
    }


@router.post("/actuals/{actual_id}/attachments", status_code=201)
def upload_attachment(
    actual_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    source: str = Form(default="Manual_Upload"),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.edit")),
    db: Session = Depends(get_db),
):
    if source not in ("Manual_Upload", "Email_Capture", "AI_Capture"):
        raise HTTPException(400, "Invalid source")
    try:
        att = att_svc.add_attachment(
            db, actual_id=actual_id,
            file_stream=file.file,
            original_filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            source=source,
            user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    return _serialise_attachment(att)


@router.delete("/actuals/{actual_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    actual_id: uuid.UUID,
    attachment_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("actuals.edit")),
    db: Session = Depends(get_db),
):
    try:
        att_svc.remove_attachment(
            db, actual_id=actual_id, attachment_id=attachment_id,
            user=current, perms=perms, request=request,
        )
    except ActualError as exc:
        _raise_for(exc)
    db.commit()
    return Response(status_code=204)
