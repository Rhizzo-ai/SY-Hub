"""Purchase Order approvals service — Chat 24 §R3 (Prompt 2.5).

Implements:
  - submit_po_with_budget_gate   (replaces R2's bare submit for non-issue PA path)
  - approve_po                   (pending_approval → approved)
  - reject_po                    (pending_approval → draft + notes required)
  - unlock_po                    (approved → draft; rare path; notifies approver)
  - list_approvals_for_po
  - list_pending_approvals       (project-scoped + cross-project)

Critical invariants:
  - SELF-APPROVAL GUARD: the user who submitted a PO must NOT be able
    to approve OR reject it, even if they hold `pos.approve`.
    Surfaced as 403 + error type `po/self-approval-forbidden`.
  - Approval row immutability: once `resolution` is set, the row is
    closed — re-submit after rejection creates a fresh row (the
    `ux_poa_one_open_per_po` partial unique idx enforces "at most one
    open approval per PO" at the DB layer).
  - Every approval/reject/unlock writes an audit_log row with field-
    level diff against the PO header (status, *_at, *_by, *_reason).
  - Notifications fired on submit / approve / reject / unlock via the
    existing `Approval_Requested` and `Approval_Decision` types.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.permissions import UserPermissions
from app.models.notifications import Notification
from app.models.po_approvals import PurchaseOrderApproval
from app.models.purchase_orders import PurchaseOrder
from app.models.user import User
from app.services import po_transitions
from app.services.audit import field_diff, record_audit
from app.services.po_authz import PoNotFound, load_po_for_write
from app.services.po_commitments import (
    build_budget_snapshot,
    evaluate_budget_overrun,
)
from app.services.purchase_orders import _snap_po  # internal but stable


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def _notify(
    db: Session,
    *,
    recipient_user_id: uuid.UUID,
    notification_type: str,
    title: str,
    body: str,
    po: PurchaseOrder,
    priority: str = "Normal",
) -> None:
    """Insert an in-platform notification (no email/SMS in R3)."""
    db.add(Notification(
        recipient_user_id=recipient_user_id,
        notification_type=notification_type,
        priority=priority,
        title=title[:255],
        body=body,
        related_resource_type="purchase_order",
        related_resource_id=po.id,
        action_url=f"/purchase-orders/{po.id}",
        action_label="View PO",
    ))


def _broadcast_to_approvers(
    db: Session, *, po: PurchaseOrder, exclude_user_id: uuid.UUID,
    title: str, body: str,
) -> int:
    """Notify every active user in this tenant who holds `pos.approve`,
    EXCEPT the submitter (self-notify is noise).

    Returns the recipient count.
    """
    from app.auth.permissions import compute_effective_permissions
    from sqlalchemy import select
    users = db.scalars(
        select(User).where(
            User.tenant_id == po.tenant_id,
            User.is_active.is_(True) if hasattr(User, "is_active") else True,
        )
    ).all()
    count = 0
    for u in users:
        if u.id == exclude_user_id:
            continue
        perms = compute_effective_permissions(db, u.id, po.tenant_id)
        if perms.has("pos.approve"):
            _notify(
                db, recipient_user_id=u.id,
                notification_type="Approval_Requested",
                title=title, body=body, po=po, priority="High",
            )
            count += 1
    return count


def _get_open_approval(
    db: Session, po_id: uuid.UUID,
) -> Optional[PurchaseOrderApproval]:
    """Return the open (unresolved) approval row for this PO, or None."""
    return db.scalar(
        select(PurchaseOrderApproval).where(
            PurchaseOrderApproval.purchase_order_id == po_id,
            PurchaseOrderApproval.resolution.is_(None),
        )
    )


# ─────────────────────────────────────────────────────────────────────────
# Submit (replaces R2 bare submit for the budget-gated path)
# ─────────────────────────────────────────────────────────────────────────

def submit_po_with_budget_gate(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    submission_reason: Optional[str] = None,
    request: Optional[Request] = None,
) -> tuple[PurchaseOrder, Optional[PurchaseOrderApproval]]:
    """Submit a Draft PO with the §4.2 budget gate.

    Branches (R7.0 Option B):
      1. Within-budget AND PO.approval_required=false → auto-approve
         (transition draft → approved, no approval row created). The
         operator must then call the explicit `issue` action to move
         approved → issued. R7.0 removed the legacy auto-issue collapse:
         `approved`-but-not-`issued` is now the safety buffer (committed
         in the books, supplier not yet told).
      2. Within-budget AND PO.approval_required=true  → pending_approval
         (user-driven approval requirement; approval row created).
      3. Over-budget → draft → pending_approval, fresh approval row
         created with budget_snapshot + submission_reason (the gate
         trumps the approval_required flag).

    Returns (po, approval) — `approval` is None for case (1).
    """
    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    if po.status != "draft":
        from app.services.po_transitions import TransitionError
        raise TransitionError(
            f"Submit only valid from 'draft'; current status={po.status!r}"
        )

    overruns = evaluate_budget_overrun(db, po)
    over_budget = bool(overruns)
    snapshot = build_budget_snapshot(db, po)
    before = _snap_po(po)

    approval_row: Optional[PurchaseOrderApproval] = None

    if not over_budget and not po.approval_required:
        # Case 1 — within budget AND caller didn't flag approval_required.
        # R7.0: lands at `approved`, NOT `issued`. The explicit issue
        # endpoint is the only legitimate path to `issued` from here.
        target = po_transitions.submit(po, user.id)
        assert target == "approved", (
            f"R7.0 Option B invariant broken: within-budget auto path "
            f"must land at 'approved', got {target!r}"
        )
        po.updated_by = user.id
        po.updated_at = datetime.now(timezone.utc)
        db.flush()
        after = _snap_po(po)
        record_audit(
            db, action="Status_Change",
            resource_type="purchase_order",
            resource_id=po.id,
            actor_user_id=user.id,
            project_id=po.project_id,
            field_changes=field_diff(before, after),
            metadata={
                "po_number": po.po_number,
                "new_status": "approved",
                "auto_approved": True,
                "budget_gate": "within_budget",
            },
            request=request,
        )
        return po, None

    # All other paths land in pending_approval with an open approval
    # row — either because the budget gate tripped, OR because the
    # caller explicitly flagged approval_required=true (user-driven
    # approval is always honoured, even within budget).
    target = po_transitions.submit(po, user.id)
    # R7.0 — po_transitions.submit() with approval_required=false now
    # auto-APPROVES (was: auto-issued in §R2). For the over-budget
    # path we force PA regardless of approval_required: the gate
    # trumps the flag. Rewind the auto-approve stamps if we landed
    # there.
    if target == "approved":
        po.status = "pending_approval"
        po.approved_at = None
        po.approved_by = None
    now = datetime.now(timezone.utc)
    approval_row = PurchaseOrderApproval(
        purchase_order_id=po.id,
        submitted_by=user.id,
        submitted_at=now,
        submission_reason=submission_reason,
        budget_snapshot=snapshot,
    )
    db.add(approval_row)
    po.updated_by = user.id
    po.updated_at = now
    db.flush()
    after = _snap_po(po)
    record_audit(
        db, action="Submit",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, after),
        metadata={
            "po_number": po.po_number,
            "new_status": "pending_approval",
            "budget_gate": "over_budget" if over_budget else "within_budget_with_approval_flag",
            "overruns": overruns,
            "approval_row_id": str(approval_row.id),
        },
        request=request,
    )
    # Notify every approver in the tenant (excluding the submitter).
    _broadcast_to_approvers(
        db, po=po, exclude_user_id=user.id,
        title=f"PO {po.po_number} needs approval",
        body=(
            f"Over-budget by £{sum(float(o['over_by']) for o in overruns):.2f} "
            f"across {len(overruns)} budget line(s)."
            if over_budget else
            "Submitter flagged this PO as requiring approval."
        ),
    )
    return po, approval_row


# ─────────────────────────────────────────────────────────────────────────
# Approve / Reject
# ─────────────────────────────────────────────────────────────────────────

class SelfApprovalForbidden(Exception):
    """Raised when the submitter tries to resolve their own approval."""


def approve_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    notes: Optional[str] = None,
    request: Optional[Request] = None,
) -> tuple[PurchaseOrder, PurchaseOrderApproval]:
    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    if po.status != "pending_approval":
        from app.services.po_transitions import TransitionError
        raise TransitionError(
            f"Approve only valid from 'pending_approval'; "
            f"current status={po.status!r}"
        )
    row = _get_open_approval(db, po.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "po/no-open-approval",
                "title": "No open approval row for this PO",
            },
        )
    # Self-approval guard — submitter cannot approve their own PO.
    if row.submitted_by == user.id:
        raise SelfApprovalForbidden(
            f"User {user.id} submitted this PO and cannot approve it"
        )

    before = _snap_po(po)
    now = datetime.now(timezone.utc)
    row.resolution = "approved"
    row.resolved_by = user.id
    row.resolved_at = now
    if notes and notes.strip():
        row.resolution_notes = notes.strip()

    po_transitions.assert_transition("pending_approval", "approved")
    po.status = "approved"
    po.approved_at = now
    po.approved_by = user.id
    po.updated_by = user.id
    po.updated_at = now
    db.flush()
    after = _snap_po(po)
    record_audit(
        db, action="Approve",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, after),
        metadata={
            "po_number": po.po_number,
            "new_status": "approved",
            "approval_row_id": str(row.id),
            "submitted_by": str(row.submitted_by),
        },
        request=request,
    )
    _notify(
        db, recipient_user_id=row.submitted_by,
        notification_type="Approval_Decision",
        title=f"PO {po.po_number} approved",
        body=(notes.strip() if notes and notes.strip()
              else "Your PO submission has been approved."),
        po=po, priority="Normal",
    )
    return po, row


def reject_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    notes: str,
    request: Optional[Request] = None,
) -> tuple[PurchaseOrder, PurchaseOrderApproval]:
    """Reject a pending PO → goes back to draft, notes are REQUIRED."""
    if not notes or not notes.strip():
        raise ValueError("Rejection notes are required")

    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    if po.status != "pending_approval":
        from app.services.po_transitions import TransitionError
        raise TransitionError(
            f"Reject only valid from 'pending_approval'; "
            f"current status={po.status!r}"
        )
    row = _get_open_approval(db, po.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "po/no-open-approval",
                "title": "No open approval row for this PO",
            },
        )
    if row.submitted_by == user.id:
        raise SelfApprovalForbidden(
            f"User {user.id} submitted this PO and cannot reject it"
        )

    before = _snap_po(po)
    now = datetime.now(timezone.utc)
    row.resolution = "rejected"
    row.resolved_by = user.id
    row.resolved_at = now
    row.resolution_notes = notes.strip()

    po_transitions.assert_transition("pending_approval", "draft")
    po.status = "draft"
    # Clear submit stamps on rejection (the submitter has to resubmit).
    po.submitted_at = None
    po.submitted_by = None
    po.updated_by = user.id
    po.updated_at = now
    db.flush()
    after = _snap_po(po)
    record_audit(
        db, action="Reject",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, after),
        metadata={
            "po_number": po.po_number,
            "new_status": "draft",
            "approval_row_id": str(row.id),
            "submitted_by": str(row.submitted_by),
            "rejection_notes": notes.strip(),
        },
        request=request,
    )
    _notify(
        db, recipient_user_id=row.submitted_by,
        notification_type="Approval_Decision",
        title=f"PO {po.po_number} rejected",
        body=f"Rejection reason: {notes.strip()}",
        po=po, priority="High",
    )
    return po, row


# ─────────────────────────────────────────────────────────────────────────
# Unlock — approved → draft (rare path)
# ─────────────────────────────────────────────────────────────────────────

def unlock_po(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    po_id: uuid.UUID,
    reason: str,
    request: Optional[Request] = None,
) -> PurchaseOrder:
    """Move an Approved PO back to Draft.

    Use case: budget reorganisation / supplier change after approval but
    before issue. Notifies the prior approver so they know the
    pre-approved record is no longer valid.
    """
    if not reason or not reason.strip():
        raise ValueError("Unlock reason is required")

    po = load_po_for_write(db, po_id, user, perms, lock_for_update=True)
    if po.status != "approved":
        from app.services.po_transitions import TransitionError
        raise TransitionError(
            f"Unlock only valid from 'approved'; current status={po.status!r}"
        )

    # The state machine doesn't have an approved → draft edge today.
    # We add it inline (a deliberate state-machine extension for the
    # unlock path) — log the transition for the operator audit.
    prior_approver = po.approved_by

    before = _snap_po(po)
    po.status = "draft"
    po.approved_at = None
    po.approved_by = None
    po.submitted_at = None
    po.submitted_by = None
    po.updated_by = user.id
    po.updated_at = datetime.now(timezone.utc)
    db.flush()
    after = _snap_po(po)
    record_audit(
        db, action="Unlock",
        resource_type="purchase_order",
        resource_id=po.id,
        actor_user_id=user.id,
        project_id=po.project_id,
        field_changes=field_diff(before, after),
        metadata={
            "po_number": po.po_number,
            "new_status": "draft",
            "unlock_reason": reason.strip(),
            "prior_approver": str(prior_approver) if prior_approver else None,
        },
        request=request,
    )
    if prior_approver is not None and prior_approver != user.id:
        _notify(
            db, recipient_user_id=prior_approver,
            notification_type="Approval_Decision",
            title=f"PO {po.po_number} unlocked to draft",
            body=f"Reason: {reason.strip()}",
            po=po, priority="High",
        )
    return po


# ─────────────────────────────────────────────────────────────────────────
# Listing
# ─────────────────────────────────────────────────────────────────────────

def list_approvals_for_po(
    db: Session, po: PurchaseOrder,
) -> list[PurchaseOrderApproval]:
    return list(db.scalars(
        select(PurchaseOrderApproval)
        .where(PurchaseOrderApproval.purchase_order_id == po.id)
        .order_by(PurchaseOrderApproval.submitted_at.asc())
    ).all())


def list_pending_approvals(
    db: Session,
    *,
    user: User,
    perms: UserPermissions,
    project_id: Optional[uuid.UUID] = None,
) -> list[dict[str, Any]]:
    """List open approval rows visible to the caller.

    Pattern α visibility applies via the underlying PO's project_id.
    Self-approval guard: a row is hidden from its own submitter (they
    can't act on it anyway).
    """
    stmt = (
        select(PurchaseOrderApproval, PurchaseOrder)
        .join(PurchaseOrder, PurchaseOrder.id ==
              PurchaseOrderApproval.purchase_order_id)
        .where(
            PurchaseOrderApproval.resolution.is_(None),
            PurchaseOrder.tenant_id == user.tenant_id,
            PurchaseOrderApproval.submitted_by != user.id,
        )
    )
    if project_id is not None:
        stmt = stmt.where(PurchaseOrder.project_id == project_id)
    if not perms.is_super_admin:
        from app.services.po_authz import visible_project_ids
        allowed = visible_project_ids(db, user.id, user.tenant_id)
        if allowed is None:
            pass
        elif not allowed:
            return []
        else:
            stmt = stmt.where(PurchaseOrder.project_id.in_(allowed))
    rows = db.execute(stmt.order_by(
        PurchaseOrderApproval.submitted_at.asc()
    )).all()
    return [
        {
            "approval_id": str(a.id),
            "po_id": str(p.id),
            "po_number": p.po_number,
            "project_id": str(p.project_id),
            "submitted_by": str(a.submitted_by),
            "submitted_at": a.submitted_at.isoformat(),
            "submission_reason": a.submission_reason,
            "budget_snapshot": a.budget_snapshot,
        }
        for (a, p) in rows
    ]


# ─────────────────────────────────────────────────────────────────────────
# Serialisation
# ─────────────────────────────────────────────────────────────────────────

def serialise_approval(row: PurchaseOrderApproval) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "purchase_order_id": str(row.purchase_order_id),
        "submitted_by": str(row.submitted_by),
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "submission_reason": row.submission_reason,
        "budget_snapshot": row.budget_snapshot,
        "resolution": row.resolution,
        "resolved_by": str(row.resolved_by) if row.resolved_by else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolution_notes": row.resolution_notes,
    }
