"""Purchase Order state machine — Chat 24 §R2 (Prompt 2.5).

States (8): draft, pending_approval, approved, issued,
partially_receipted, receipted, closed, voided.

R2-scoped transitions:
  - draft -> pending_approval   (submit when approval_required=true)
  - draft -> issued             (submit when approval_required=false)
  - approved -> issued          (issue, post-approval)
  - draft|pending|approved|issued -> voided (void with reason)
  - partially_receipted|receipted -> closed   (close)

Transitions deferred to R3 / R4 are not implemented here but the
status set is the same:
  - pending_approval -> approved | draft  (R3)
  - issued -> partially_receipted|receipted (R4 receipts)
  - closed -> approved|issued|… (R4 reopen)

Every successful transition stamps the appropriate `*_at`/`*_by`
columns and emits an audit_log row via the caller's service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.models.purchase_orders import PurchaseOrder


class TransitionError(ValueError):
    """Raised when a state transition is not permitted for the current status."""


# Allowed transition map. Source-of-truth for the R2 state machine.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft":                {"pending_approval", "issued", "voided"},
    "pending_approval":     {"approved", "draft", "voided"},      # R3 does the work
    "approved":             {"issued", "voided"},
    "issued":               {"partially_receipted", "receipted",
                             "voided", "closed"},
    "partially_receipted":  {"receipted", "closed"},
    "receipted":            {"closed"},
    "closed":               {"approved", "issued",
                             "partially_receipted", "receipted"},  # R4 reopen
    "voided":               set(),                                  # terminal
}


def assert_transition(current: str, target: str) -> None:
    """Validate that `current -> target` is a permitted transition.

    Raises TransitionError with a human-readable message when it isn't.
    """
    if current not in ALLOWED_TRANSITIONS:
        raise TransitionError(f"Unknown PO status {current!r}")
    if target not in ALLOWED_TRANSITIONS[current]:
        allowed = sorted(ALLOWED_TRANSITIONS[current])
        raise TransitionError(
            f"Cannot transition from {current!r} to {target!r} "
            f"(allowed: {allowed or 'none — terminal state'})"
        )


# ─────────────────────────────────────────────────────────────────────────
# R2-scope transitions
# ─────────────────────────────────────────────────────────────────────────

def submit(po: PurchaseOrder, user_id) -> str:
    """Submit a Draft PO.

    Behaviour:
      - approval_required = true  -> draft -> pending_approval
      - approval_required = false -> draft -> issued (auto-issue path)

    Returns the new status. Caller persists.
    """
    if po.status != "draft":
        raise TransitionError(
            f"Submit only valid from 'draft', current={po.status!r}"
        )
    now = datetime.now(timezone.utc)
    if po.approval_required:
        target = "pending_approval"
        po.submitted_at = now
        po.submitted_by = user_id
    else:
        # Auto-issue: still record the submit stamp for audit forensics.
        target = "issued"
        po.submitted_at = now
        po.submitted_by = user_id
        po.issued_at = now
        po.issued_by = user_id
    assert_transition(po.status, target)
    po.status = target
    return target


def issue(po: PurchaseOrder, user_id) -> str:
    """Issue an Approved PO (approved -> issued)."""
    if po.status != "approved":
        raise TransitionError(
            f"Issue only valid from 'approved', current={po.status!r}"
        )
    assert_transition(po.status, "issued")
    po.status = "issued"
    po.issued_at = datetime.now(timezone.utc)
    po.issued_by = user_id
    return po.status


def void(po: PurchaseOrder, user_id, reason: str) -> str:
    """Void a PO with a required reason.

    Voidable from: draft, pending_approval, approved, issued. Once a PO
    has receipts (partially_receipted, receipted) it must be closed,
    not voided — the void path is rejected.
    """
    if not reason or not reason.strip():
        raise TransitionError("Void requires a non-empty reason")
    if po.status in ("voided", "closed"):
        raise TransitionError(
            f"Void only valid from active states; current={po.status!r}"
        )
    if po.status in ("partially_receipted", "receipted"):
        raise TransitionError(
            f"PO has receipts (status={po.status!r}); close instead of void"
        )
    assert_transition(po.status, "voided")
    po.status = "voided"
    po.voided_at = datetime.now(timezone.utc)
    po.voided_by = user_id
    po.voided_reason = reason.strip()
    return po.status


def close(po: PurchaseOrder, user_id, reason: Optional[str] = None) -> str:
    """Close a receipted PO (partially_receipted / receipted -> closed).

    Optional reason is captured on `closed_reason` when supplied.
    """
    if po.status not in ("partially_receipted", "receipted", "issued"):
        raise TransitionError(
            f"Close only valid from issued / partially_receipted / "
            f"receipted; current={po.status!r}"
        )
    assert_transition(po.status, "closed")
    po.status = "closed"
    po.closed_at = datetime.now(timezone.utc)
    po.closed_by = user_id
    if reason and reason.strip():
        po.closed_reason = reason.strip()
    return po.status
