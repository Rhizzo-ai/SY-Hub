"""Purchase Order state machine — Chat 24 §R2 (Prompt 2.5), R7.0 Option B,
R7.0b send-back (Chat 26).

States (8): draft, pending_approval, approved, issued,
partially_receipted, receipted, closed, voided.

Transitions:
  - draft -> pending_approval   (submit when approval_required=true,
                                 budget-gate enforced)
  - draft -> approved           (submit when within-budget AND
                                 approval_required=false — R7.0 Option B;
                                 was draft -> issued in §R2)
  - approved -> issued          (issue, post-approval — REQUIRED step;
                                 R7.0 stops the auto-issue collapse)
  - approved -> draft           (R7.0b send-back for correction; clears
                                 approve+submit stamps; the commitment
                                 trigger trg_po_status_commitments drops
                                 the PO out of committed_value
                                 automatically — no manual recompute)
  - draft|pending|approved|issued -> voided (void with reason)
  - partially_receipted|receipted -> closed   (close)
  - pending_approval -> approved | draft  (R3)
  - issued -> partially_receipted|receipted (R4 receipts)

Every successful transition stamps the appropriate `*_at`/`*_by`
columns and emits an audit_log row via the caller's service.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.models.purchase_orders import PurchaseOrder


class TransitionError(ValueError):
    """Raised when a state transition is not permitted for the current status."""


# Allowed transition map. Source-of-truth for the state machine.
# `closed` and `voided` are TERMINAL per build pack §2.4 — reopen-from-
# closed is deliberately NOT in scope for Prompt 2.5 (logged to
# SY_Homes_Future_Tasks.md §15).
#
# R7.0 — `draft -> approved` is now a permitted edge so the within-budget
# auto-approve path can land directly without first faking
# `pending_approval`. The legacy `draft -> issued` edge is retained for
# data-migration and admin tooling but no production code path takes it
# any more (auto-issue collapse removed; issue is always reached via
# `approved -> issued`).
#
# R7.0b (P0.13 resolution) — `approved -> draft` is the send-back edge.
# A within-budget auto-approved PO with a wrong line/amount can be
# corrected by sending it back to draft rather than being issued-wrong
# or voided (voiding burns the sequential PO number). The commitment
# trigger trg_po_status_commitments handles the committed_value drop
# automatically on status change.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft":                {"pending_approval", "approved", "issued", "voided"},
    "pending_approval":     {"approved", "draft", "voided"},
    "approved":             {"issued", "voided", "draft"},
    "issued":               {"partially_receipted", "receipted",
                             "voided", "closed"},
    "partially_receipted":  {"receipted", "closed"},
    "receipted":            {"closed"},
    "closed":               set(),                                  # terminal
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

    Behaviour (R7.0 Option B):
      - approval_required = true  -> draft -> pending_approval
      - approval_required = false -> draft -> approved  (was: issued
        in §R2. R7.0 changes the within-budget auto-flow to land at
        `approved` so a separate, explicit Issue action is required
        before a supplier-visible PO exists. `approved`-but-not-`issued`
        is the safety buffer — committed in the books, supplier not
        yet told, still pullable.)

    Note: this transition unit does NOT enforce the budget gate; the
    over-budget path is handled upstream in
    `po_approvals.submit_po_with_budget_gate` which forces
    `pending_approval` regardless of `approval_required`.

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
        # R7.0 — Option B: within-budget auto path lands at `approved`,
        # NOT `issued`. `issued_at`/`issued_by` are LEFT NULL and only
        # populated by the subsequent explicit `issue()` call. Record
        # the submit stamp for audit forensics, and the approved stamp
        # so reporting knows when the safety buffer started.
        target = "approved"
        po.submitted_at = now
        po.submitted_by = user_id
        po.approved_at = now
        po.approved_by = user_id
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
