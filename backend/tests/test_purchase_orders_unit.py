"""Chat 24 §R2 (Prompt 2.5) — Purchase Order unit tests.

These tests are pure-Python — they exercise the state machine
(`po_transitions`) and the edit-tier guard (`po_authz`) without
touching the database. They are the canonical guards for the
build-pack target:

  G2.4  edit-tier matrix tests   (~8)
  G2.x  state-transition tests   (~10)

Integration tests (CRUD + numbering allocation against Postgres) live
in `test_purchase_orders_api.py` and require a live DB.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import po_transitions
from app.services.po_authz import (
    EditPermission,
    check_can_edit_fields,
    edit_tier_for,
    required_perm_for_tier,
)


# Helper to fabricate a minimal PO-like object for the state machine.
def _po(status: str, *, approval_required: bool = False, **extra) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        approval_required=approval_required,
        submitted_at=None, submitted_by=None,
        issued_at=None, issued_by=None,
        approved_at=None, approved_by=None,
        voided_at=None, voided_by=None, voided_reason=None,
        closed_at=None, closed_by=None, closed_reason=None,
        **extra,
    )


# Fake UserPermissions for edit-tier tests.
class _Perms:
    def __init__(self, codes: set[str] | None = None) -> None:
        self.codes = set(codes or [])

    def has(self, code: str) -> bool:
        return code in self.codes


# ─────────────────────────────────────────────────────────────────────────
# State machine: transition assertions
# ─────────────────────────────────────────────────────────────────────────

class TestTransitionAssertion:
    def test_draft_can_go_pending_approval_issued_or_voided(self):
        po_transitions.assert_transition("draft", "pending_approval")
        po_transitions.assert_transition("draft", "issued")
        po_transitions.assert_transition("draft", "voided")

    def test_voided_is_terminal(self):
        with pytest.raises(po_transitions.TransitionError):
            po_transitions.assert_transition("voided", "draft")
        with pytest.raises(po_transitions.TransitionError):
            po_transitions.assert_transition("voided", "approved")

    def test_closed_is_terminal(self):
        # Build pack §2.4 — `closed` has no outgoing transitions in
        # Prompt 2.5. Reopen-from-closed deferred to Future_Tasks §17.
        for tgt in ("approved", "issued", "partially_receipted", "receipted",
                    "voided", "draft"):
            with pytest.raises(po_transitions.TransitionError):
                po_transitions.assert_transition("closed", tgt)

    def test_unknown_status_raises(self):
        with pytest.raises(po_transitions.TransitionError):
            po_transitions.assert_transition("bogus", "draft")

    def test_issued_to_partially_or_fully_receipted_or_closed_or_voided(self):
        for tgt in ("partially_receipted", "receipted", "closed", "voided"):
            po_transitions.assert_transition("issued", tgt)

    def test_receipted_can_only_close(self):
        po_transitions.assert_transition("receipted", "closed")
        with pytest.raises(po_transitions.TransitionError):
            po_transitions.assert_transition("receipted", "voided")


# ─────────────────────────────────────────────────────────────────────────
# State machine: submit / void / close stampers
# ─────────────────────────────────────────────────────────────────────────

class TestSubmit:
    def test_submit_with_approval_required_goes_pending(self):
        po = _po("draft", approval_required=True)
        uid = uuid.uuid4()
        assert po_transitions.submit(po, uid) == "pending_approval"
        assert po.status == "pending_approval"
        assert po.submitted_at is not None
        assert po.submitted_by == uid
        # No auto-issue.
        assert po.issued_at is None

    def test_submit_without_approval_auto_issues(self):
        po = _po("draft", approval_required=False)
        uid = uuid.uuid4()
        assert po_transitions.submit(po, uid) == "issued"
        assert po.status == "issued"
        assert po.submitted_by == uid
        assert po.issued_by == uid
        assert po.issued_at is not None

    def test_submit_from_non_draft_raises(self):
        for bad in ("pending_approval", "approved", "issued", "closed", "voided"):
            po = _po(bad)
            with pytest.raises(po_transitions.TransitionError):
                po_transitions.submit(po, uuid.uuid4())


class TestVoid:
    def test_void_requires_reason(self):
        po = _po("draft")
        with pytest.raises(po_transitions.TransitionError):
            po_transitions.void(po, uuid.uuid4(), "")
        with pytest.raises(po_transitions.TransitionError):
            po_transitions.void(po, uuid.uuid4(), "   ")

    def test_void_from_active_states_succeeds(self):
        for src in ("draft", "pending_approval", "approved", "issued"):
            po = _po(src)
            po_transitions.void(po, uuid.uuid4(), "supplier withdrew")
            assert po.status == "voided"
            assert po.voided_reason == "supplier withdrew"

    def test_void_with_receipts_is_blocked(self):
        for src in ("partially_receipted", "receipted"):
            po = _po(src)
            with pytest.raises(po_transitions.TransitionError):
                po_transitions.void(po, uuid.uuid4(), "reason")

    def test_void_from_terminal_blocked(self):
        for src in ("voided", "closed"):
            po = _po(src)
            with pytest.raises(po_transitions.TransitionError):
                po_transitions.void(po, uuid.uuid4(), "reason")


class TestClose:
    def test_close_from_issued_partial_or_receipted(self):
        for src in ("issued", "partially_receipted", "receipted"):
            po = _po(src)
            po_transitions.close(po, uuid.uuid4(), "completed")
            assert po.status == "closed"
            assert po.closed_reason == "completed"
            assert po.closed_at is not None

    def test_close_optional_reason(self):
        po = _po("issued")
        po_transitions.close(po, uuid.uuid4(), None)
        assert po.status == "closed"
        assert po.closed_reason is None

    def test_close_from_draft_or_pending_blocked(self):
        for src in ("draft", "pending_approval", "approved",
                    "voided", "closed"):
            po = _po(src)
            with pytest.raises(po_transitions.TransitionError):
                po_transitions.close(po, uuid.uuid4(), None)


# ─────────────────────────────────────────────────────────────────────────
# Edit-tier matrix (G2.4 — 8 tests minimum)
# ─────────────────────────────────────────────────────────────────────────

class TestEditTier:
    @pytest.mark.parametrize("status,expected", [
        ("draft", EditPermission.FULL),
        ("approved", EditPermission.FULL),
        ("issued", EditPermission.HEADER_ANNOTATION_ONLY),
        ("partially_receipted", EditPermission.HEADER_ANNOTATION_ONLY),
        ("receipted", EditPermission.HEADER_ANNOTATION_ONLY),
        ("closed", EditPermission.READ_ONLY),
        ("voided", EditPermission.READ_ONLY),
        ("pending_approval", EditPermission.READ_ONLY),
    ])
    def test_edit_tier_for_status(self, status, expected):
        assert edit_tier_for(_po(status)) is expected

    def test_required_perm_for_each_tier(self):
        assert required_perm_for_tier(EditPermission.FULL) == "pos.edit"
        assert (
            required_perm_for_tier(EditPermission.HEADER_ANNOTATION_ONLY)
            == "pos.edit_issued"
        )
        assert required_perm_for_tier(EditPermission.READ_ONLY) is None


class TestCheckCanEditFields:
    def test_full_tier_allows_any_field(self):
        po = _po("draft")
        tier, disallowed = check_can_edit_fields(
            po, _Perms({"pos.edit"}),
            ["supplier_id", "delivery_address", "notes"],
        )
        assert tier is EditPermission.FULL
        assert disallowed == []

    def test_header_only_tier_allows_annotation_fields_only(self):
        po = _po("issued")
        tier, disallowed = check_can_edit_fields(
            po, _Perms({"pos.edit_issued"}),
            ["notes", "delivery_notes", "external_reference"],
        )
        assert tier is EditPermission.HEADER_ANNOTATION_ONLY
        assert disallowed == []

    def test_header_only_tier_rejects_non_annotation_fields(self):
        po = _po("issued")
        tier, disallowed = check_can_edit_fields(
            po, _Perms({"pos.edit_issued"}),
            ["notes", "supplier_id", "issue_date"],
        )
        assert tier is EditPermission.HEADER_ANNOTATION_ONLY
        assert set(disallowed) == {"supplier_id", "issue_date"}

    def test_missing_full_tier_perm_403(self):
        po = _po("draft")
        with pytest.raises(HTTPException) as ex:
            check_can_edit_fields(po, _Perms(set()), ["notes"])
        assert ex.value.status_code == 403
        assert ex.value.detail["type"] == "po_edit_forbidden"
        assert ex.value.detail["required_permission"] == "pos.edit"

    def test_missing_header_only_perm_403(self):
        po = _po("issued")
        with pytest.raises(HTTPException) as ex:
            check_can_edit_fields(
                po, _Perms({"pos.edit"}),  # has FULL perm but not HEADER one
                ["notes"],
            )
        assert ex.value.status_code == 403
        assert ex.value.detail["required_permission"] == "pos.edit_issued"

    def test_read_only_status_with_any_field_403(self):
        po = _po("closed")
        with pytest.raises(HTTPException) as ex:
            check_can_edit_fields(po, _Perms({"pos.edit"}), ["notes"])
        assert ex.value.status_code == 403
        assert ex.value.detail["po_status"] == "closed"

    def test_read_only_status_with_empty_fields_passes_without_403(self):
        # A PATCH with no changed fields against a closed PO is a no-op,
        # not a permission error.
        po = _po("voided")
        tier, disallowed = check_can_edit_fields(po, _Perms(set()), [])
        assert tier is EditPermission.READ_ONLY
        assert disallowed == []

    def test_pending_approval_treated_as_read_only(self):
        # Approvals come in R3; for R2 PA freezes edits entirely.
        po = _po("pending_approval")
        with pytest.raises(HTTPException) as ex:
            check_can_edit_fields(po, _Perms({"pos.edit"}), ["notes"])
        assert ex.value.status_code == 403
        assert ex.value.detail["po_status"] == "pending_approval"
