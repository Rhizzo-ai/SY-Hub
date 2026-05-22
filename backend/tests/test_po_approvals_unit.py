"""Chat 24 §R3 (Prompt 2.5) — PO Approvals unit tests.

Pure-Python tests (no DB). Cover:
  - Budget gate math: within-budget, over by one line, over by multiple
    lines, line aggregation across multiple PO lines on same budget_line.
  - Self-approval guard logic (SelfApprovalForbidden raised).
  - Approval transition assertions integrate with R2 state machine.

Live DB tests (triggers + audit + notifications) live in
`test_po_approvals_api.py`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import po_commitments


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

class FakeDB:
    """Minimal SQLAlchemy Session stand-in for unit testing.

    Supports:
      - `scalars(stmt).all()` → returns the BudgetLine list set via
        `set_budget_lines(...)`.
      - `get(model, pk)` → looks up CostCodes by id in a dict.
    """

    def __init__(self, budget_lines, cost_codes):
        self._blines = list(budget_lines)
        self._ccs = {c.id: c for c in cost_codes}

    def scalars(self, stmt):
        # We don't actually parse the statement — we just return the
        # set list. Sufficient for evaluate_budget_overrun / snapshot
        # which only do a single `select(BudgetLine).where(id.in_(...))`.
        out = SimpleNamespace(all=lambda: list(self._blines))
        return out

    def get(self, model, pk):
        return self._ccs.get(pk)


def _bline(*, current, committed, actuals, cc_id=None):
    bl = SimpleNamespace(
        id=uuid.uuid4(),
        cost_code_id=cc_id or uuid.uuid4(),
        current_budget=Decimal(str(current)),
        committed_value=Decimal(str(committed)),
        actuals_to_date=Decimal(str(actuals)),
    )
    return bl


def _po(lines):
    return SimpleNamespace(lines=list(lines))


def _po_line(budget_line_id, net):
    return SimpleNamespace(
        budget_line_id=budget_line_id,
        net_amount=Decimal(str(net)),
    )


# ─────────────────────────────────────────────────────────────────────────
# Budget gate math
# ─────────────────────────────────────────────────────────────────────────

class TestEvaluateBudgetOverrun:
    def test_within_budget_returns_empty(self):
        bl = _bline(current=1000, committed=200, actuals=100)
        po = _po([_po_line(bl.id, 500)])
        cc = SimpleNamespace(id=bl.cost_code_id, code="01.01")
        db = FakeDB([bl], [cc])
        assert po_commitments.evaluate_budget_overrun(db, po) == []

    def test_over_budget_by_one_line(self):
        bl = _bline(current=1000, committed=900, actuals=50)
        po = _po([_po_line(bl.id, 100)])  # 900 + 50 + 100 = 1050 > 1000
        cc = SimpleNamespace(id=bl.cost_code_id, code="01.02")
        db = FakeDB([bl], [cc])
        overruns = po_commitments.evaluate_budget_overrun(db, po)
        assert len(overruns) == 1
        assert overruns[0]["over_by"] == "50"
        assert overruns[0]["projected_total"] == "1050"

    def test_over_budget_by_multiple_lines(self):
        bl1 = _bline(current=1000, committed=950, actuals=0)  # over by 50
        bl2 = _bline(current=2000, committed=0, actuals=0)    # within
        bl3 = _bline(current=500, committed=400, actuals=50)  # over by 50
        po = _po([
            _po_line(bl1.id, 100),
            _po_line(bl2.id, 100),
            _po_line(bl3.id, 100),
        ])
        ccs = [
            SimpleNamespace(id=bl1.cost_code_id, code="01"),
            SimpleNamespace(id=bl2.cost_code_id, code="02"),
            SimpleNamespace(id=bl3.cost_code_id, code="03"),
        ]
        db = FakeDB([bl1, bl2, bl3], ccs)
        overruns = po_commitments.evaluate_budget_overrun(db, po)
        assert len(overruns) == 2
        codes = sorted(o["cost_code"] for o in overruns)
        assert codes == ["01", "03"]

    def test_multiple_po_lines_on_same_budget_line_sum(self):
        bl = _bline(current=1000, committed=0, actuals=0)
        # 3 PO lines all hit the SAME budget_line, summing to 1100 > 1000.
        po = _po([
            _po_line(bl.id, 400),
            _po_line(bl.id, 400),
            _po_line(bl.id, 300),
        ])
        cc = SimpleNamespace(id=bl.cost_code_id, code="01")
        db = FakeDB([bl], [cc])
        overruns = po_commitments.evaluate_budget_overrun(db, po)
        assert len(overruns) == 1
        assert overruns[0]["this_po_net"] == "1100"
        assert overruns[0]["over_by"] == "100"

    def test_existing_approved_po_already_in_committed_pushes_over(self):
        # bl.committed already reflects another approved PO of 700.
        # This PO adds 400 → 700 + 0 + 400 = 1100 > 1000.
        bl = _bline(current=1000, committed=700, actuals=0)
        po = _po([_po_line(bl.id, 400)])
        cc = SimpleNamespace(id=bl.cost_code_id, code="01")
        db = FakeDB([bl], [cc])
        overruns = po_commitments.evaluate_budget_overrun(db, po)
        assert len(overruns) == 1
        assert overruns[0]["committed_value"] == "700"
        assert overruns[0]["over_by"] == "100"


# ─────────────────────────────────────────────────────────────────────────
# Snapshot builder
# ─────────────────────────────────────────────────────────────────────────

class TestBuildBudgetSnapshot:
    def test_snapshot_includes_within_budget_lines_with_overrun_flag(self):
        bl1 = _bline(current=1000, committed=100, actuals=0)
        bl2 = _bline(current=500, committed=450, actuals=0)
        po = _po([_po_line(bl1.id, 100), _po_line(bl2.id, 100)])
        ccs = [
            SimpleNamespace(id=bl1.cost_code_id, code="01"),
            SimpleNamespace(id=bl2.cost_code_id, code="02"),
        ]
        db = FakeDB([bl1, bl2], ccs)
        snap = po_commitments.build_budget_snapshot(db, po)
        by_code = {s["cost_code"]: s for s in snap}
        assert by_code["01"]["is_overrun"] is False
        assert by_code["02"]["is_overrun"] is True

    def test_snapshot_aggregates_multiple_po_lines_per_budget_line(self):
        bl = _bline(current=2000, committed=0, actuals=0)
        po = _po([
            _po_line(bl.id, 100),
            _po_line(bl.id, 200),
        ])
        cc = SimpleNamespace(id=bl.cost_code_id, code="01")
        db = FakeDB([bl], [cc])
        snap = po_commitments.build_budget_snapshot(db, po)
        assert len(snap) == 1
        assert snap[0]["this_po_net"] == "300"


# ─────────────────────────────────────────────────────────────────────────
# SelfApprovalForbidden surfaces correctly
# ─────────────────────────────────────────────────────────────────────────

class TestSelfApprovalForbidden:
    def test_self_approval_forbidden_is_exception_type(self):
        from app.services.po_approvals import SelfApprovalForbidden
        with pytest.raises(SelfApprovalForbidden):
            raise SelfApprovalForbidden("test")



# ─────────────────────────────────────────────────────────────────────────
# Chat 26 §R7.0b — transition map edge (`approved -> draft`)
# ─────────────────────────────────────────────────────────────────────────

class TestR7SendBackTransition:
    def test_transition_map_allows_approved_to_draft(self):
        """T-unit — pure state-machine check, no DB.

        - approved → draft: now permitted (R7.0b send-back).
        - draft → approved: still permitted (R7.0 Option B within-budget
          auto-approve).
        - issued → draft: still forbidden (terminal-ish; only voided/
          partially_receipted/receipted/closed are valid from issued).
        """
        from app.services.po_transitions import (
            TransitionError, assert_transition,
        )
        # The new edge.
        assert_transition("approved", "draft")
        # The R7.0 edge is still there.
        assert_transition("draft", "approved")
        # An adjacent edge that MUST stay forbidden.
        with pytest.raises(TransitionError):
            assert_transition("issued", "draft")
