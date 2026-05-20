"""Purchase Order authorisation — Chat 24 §R2 (Prompt 2.5).

Two responsibilities, both mandatory per build pack §4.5:

  (a) Tenant / project scoping (Pattern α).  Mirrors the budgets +
      appraisals services: resolves the PO's project, validates tenant
      membership, and intersects with `_visible_project_ids`.

  (b) Edit-tier guard.  Per build pack §4.5:
        - EditPermission.FULL                — Draft / Approved, with `pos.edit`
        - EditPermission.HEADER_ANNOTATION_ONLY
                                              — Issued / Partially-receipted /
                                                Receipted, with `pos.edit_issued`
                                                (only `notes`, `delivery_notes`,
                                                 `external_reference` editable)
        - EditPermission.READ_ONLY            — Closed / Voided
      `check_can_edit_fields` enforces both the tier AND the
      permission code; PATCH endpoints feed it the payload diff and
      get back a list of disallowed fields (or an empty list on pass).
"""
from __future__ import annotations

import enum
import uuid
from typing import Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.permissions import UserPermissions
from app.models.projects import Project
from app.models.purchase_orders import (
    PurchaseOrder,
    HEADER_ANNOTATION_FIELDS,
    ISSUED_OR_BEYOND_STATUSES,
    TERMINAL_PO_STATUSES,
)
from app.models.user import User
from app.services.budgets import _scope_check_project, _visible_project_ids
from app.services.budget_errors import BudgetNotFoundError


class PoNotFound(Exception):
    """Raised when a PO is invisible to the caller (Pattern α 404)."""


class EditPermission(enum.Enum):
    FULL = "full"
    HEADER_ANNOTATION_ONLY = "header_annotation_only"
    READ_ONLY = "read_only"


# ─────────────────────────────────────────────────────────────────────────
# (a) Tenant / project scoping
# ─────────────────────────────────────────────────────────────────────────

def scope_check_project(
    db: Session, project: Project, user: User, perms: UserPermissions,
) -> None:
    """Raise PoNotFound if the project isn't in this user's visible set.

    Thin wrapper over `services.budgets._scope_check_project` so PO
    services own a stable error type rather than leaking budget errors.
    """
    try:
        _scope_check_project(db, project, user, perms)
    except BudgetNotFoundError as e:
        raise PoNotFound(str(e)) from e


def visible_project_ids(
    db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID,
) -> Optional[set[uuid.UUID]]:
    """Re-export of budgets `_visible_project_ids` for PO list paths.

    None  -> unrestricted
    set() -> no access
    set(...) -> explicit set
    """
    return _visible_project_ids(db, user_id, tenant_id)


def load_po_for_read(
    db: Session, po_id: uuid.UUID, user: User, perms: UserPermissions,
) -> PurchaseOrder:
    """Read path: returns the PO if visible, raises PoNotFound otherwise.

    The caller is responsible for any deeper permission checks (e.g.
    `pos.view_sensitive` gating on pricing fields at serialisation
    time).
    """
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise PoNotFound("Purchase order not found")
    if po.tenant_id != user.tenant_id:
        raise PoNotFound("Purchase order not found")
    project = db.get(Project, po.project_id)
    if project is None:
        raise PoNotFound("Purchase order not found")
    # Project doesn't carry tenant_id; guard via hasattr (matches the
    # budgets service convention).
    if hasattr(project, "tenant_id") and project.tenant_id != user.tenant_id:
        raise PoNotFound("Purchase order not found")
    scope_check_project(db, project, user, perms)
    return po


def load_po_for_write(
    db: Session, po_id: uuid.UUID, user: User, perms: UserPermissions,
    *, lock_for_update: bool = False,
) -> PurchaseOrder:
    """Write path: same as read path, optionally re-fetched FOR UPDATE."""
    po = load_po_for_read(db, po_id, user, perms)
    if lock_for_update:
        from sqlalchemy import select
        po = db.scalar(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id)
            .with_for_update()
        )
        if po is None:
            raise PoNotFound("Purchase order not found")
    return po


# ─────────────────────────────────────────────────────────────────────────
# (b) Edit-tier guard
# ─────────────────────────────────────────────────────────────────────────

def edit_tier_for(po: PurchaseOrder) -> EditPermission:
    """Return the EditPermission tier appropriate to this PO's status.

    The mapping is purely a function of `po.status` — the caller must
    additionally check the permission code (see `check_can_edit_fields`).
    """
    if po.status in TERMINAL_PO_STATUSES:
        return EditPermission.READ_ONLY
    if po.status in ISSUED_OR_BEYOND_STATUSES:
        # 'closed' is in both ISSUED_OR_BEYOND and TERMINAL — terminal
        # check above already short-circuits it.
        return EditPermission.HEADER_ANNOTATION_ONLY
    if po.status in ("draft", "approved"):
        return EditPermission.FULL
    # `pending_approval` falls through — no edits allowed mid-approval.
    return EditPermission.READ_ONLY


def required_perm_for_tier(tier: EditPermission) -> Optional[str]:
    """Permission code that gates this tier.

    READ_ONLY has no edit perm (we 403 the request outright).
    """
    if tier is EditPermission.FULL:
        return "pos.edit"
    if tier is EditPermission.HEADER_ANNOTATION_ONLY:
        return "pos.edit_issued"
    return None


def check_can_edit_fields(
    po: PurchaseOrder,
    perms: UserPermissions,
    fields_being_modified: Iterable[str],
) -> tuple[EditPermission, list[str]]:
    """Check that the caller can edit each field in `fields_being_modified`.

    Returns (tier, disallowed_fields):
      - `tier` is the EditPermission derived from po.status.
      - `disallowed_fields` is the subset of `fields_being_modified`
        that the caller may NOT modify under this tier. Empty list
        means the edit is fully permitted.

    Raises HTTPException(403) when:
      - The PO is read-only (closed/voided/pending_approval) and any
        field is in the payload.
      - The caller is missing the required permission code for the
        tier (`pos.edit` for FULL, `pos.edit_issued` for HEADER_ONLY).

    Field-level violations (e.g. trying to edit `supplier_id` on an
    issued PO) are NOT raised here — they are returned in
    `disallowed_fields` so the router can build a problem-detail
    response listing every offending field.
    """
    tier = edit_tier_for(po)
    fields = list(fields_being_modified)

    if tier is EditPermission.READ_ONLY:
        if fields:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "type": "po_edit_forbidden",
                    "title": "Purchase order is read-only",
                    "po_status": po.status,
                    "fields_attempted": fields,
                    "allowed_fields": [],
                },
            )
        return tier, []

    req_code = required_perm_for_tier(tier)
    if req_code is not None and not perms.has(req_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "type": "po_edit_forbidden",
                "title": f"Missing permission {req_code}",
                "po_status": po.status,
                "fields_attempted": fields,
                "required_permission": req_code,
            },
        )

    if tier is EditPermission.HEADER_ANNOTATION_ONLY:
        disallowed = [f for f in fields if f not in HEADER_ANNOTATION_FIELDS]
    else:  # FULL
        disallowed = []
    return tier, disallowed
