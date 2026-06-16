"""Purchase Order commitments + budget gating — Chat 24 §R3 (Prompt 2.5).

Two responsibilities:

  (1) `check_budget_for_po_submission` — evaluates the over-budget
      gate that decides whether a freshly-submitted PO can auto-approve
      or must go to pending_approval.

      Per spec §4.2 (D1):
        For each budget_line referenced by the PO's lines, sum the PO's
        net contribution and check whether
            committed_value + actuals_to_date + this_po_net > current_budget
        on that line. If ANY line trips, the PO is over-budget and
        must go through approval.

      The check uses the LIVE column names verified against the
      `BudgetLine` model: `current_budget`, `committed_value`,
      `actuals_to_date`. (Confirmed against R2 amendment audit — these
      are the literal column names, NOT spec-paraphrased.)

  (2) `build_budget_snapshot` — captures the JSON snapshot persisted on
      the approval row so the approver sees what they're approving even
      if the budget moves before resolution.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.budgets import BudgetLine
from app.models.cost_codes import CostCode
from app.models.purchase_orders import PurchaseOrder, PurchaseOrderLine


# ─────────────────────────────────────────────────────────────────────────
# (1) Budget gate
# ─────────────────────────────────────────────────────────────────────────

def _aggregate_po_net_by_budget_line(
    po: PurchaseOrder,
) -> dict[uuid.UUID, Decimal]:
    """Sum the PO's net contribution per budget_line_id."""
    out: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    for line in po.lines:
        out[line.budget_line_id] += Decimal(line.net_amount)
    return dict(out)


def evaluate_budget_overrun(
    db: Session, po: PurchaseOrder,
) -> list[dict[str, Any]]:
    """Return a list of over-budget budget_lines for this PO.

    Each dict carries:
      - budget_line_id (uuid)
      - cost_code (str)
      - current_budget (str — decimal serialised)
      - committed_value (str)
      - actuals_to_date (str)
      - this_po_net (str)
      - projected_total (str)  — committed + actuals + this_po_net
      - over_by (str)          — projected_total - current_budget

    Empty list ⇒ within-budget for every line.
    """
    by_line = _aggregate_po_net_by_budget_line(po)
    if not by_line:
        return []

    rows = db.scalars(
        select(BudgetLine).where(BudgetLine.id.in_(list(by_line.keys())))
    ).all()
    overruns: list[dict[str, Any]] = []
    for bline in rows:
        # B105/B106 option (ii) — Gate A owns unbudgeted lines.
        # Use getattr() with safe defaults so unit-test mocks that
        # don't construct the full SQLAlchemy attribute set (e.g.
        # SimpleNamespace fixtures in test_po_approvals_unit.py) treat
        # the line as a normal budgeted line by default.
        if getattr(bline, "is_unbudgeted", False) and \
                getattr(bline, "unbudgeted_cleared_at", None) is None:
            continue
        po_net = by_line[bline.id]
        current_budget = Decimal(bline.current_budget or 0)
        committed = Decimal(bline.committed_value or 0)
        actuals = Decimal(bline.actuals_to_date or 0)
        projected = committed + actuals + po_net
        if projected > current_budget:
            cc = db.get(CostCode, bline.cost_code_id)
            overruns.append({
                "budget_line_id": str(bline.id),
                "cost_code": (cc.code if cc else "UNKNOWN"),
                "current_budget": str(current_budget),
                "committed_value": str(committed),
                "actuals_to_date": str(actuals),
                "this_po_net": str(po_net),
                "projected_total": str(projected),
                "over_by": str(projected - current_budget),
            })
    return overruns


def is_within_budget(db: Session, po: PurchaseOrder) -> bool:
    """Convenience: True if no budget_line is over-budget."""
    return not evaluate_budget_overrun(db, po)


# ─────────────────────────────────────────────────────────────────────────
# (2) Budget snapshot for the approval row
# ─────────────────────────────────────────────────────────────────────────

def build_budget_snapshot(
    db: Session, po: PurchaseOrder,
) -> list[dict[str, Any]]:
    """Snapshot every budget_line touched by this PO at submission time.

    Always returns the full set (including within-budget lines), so the
    approver can see all per-line context, not just the overruns. The
    overrun flag is implicit (projected_total > current_budget).
    """
    by_line = _aggregate_po_net_by_budget_line(po)
    if not by_line:
        return []
    rows = db.scalars(
        select(BudgetLine).where(BudgetLine.id.in_(list(by_line.keys())))
    ).all()
    out: list[dict[str, Any]] = []
    for bline in rows:
        po_net = by_line[bline.id]
        current_budget = Decimal(bline.current_budget or 0)
        committed = Decimal(bline.committed_value or 0)
        actuals = Decimal(bline.actuals_to_date or 0)
        projected = committed + actuals + po_net
        cc = db.get(CostCode, bline.cost_code_id)
        out.append({
            "budget_line_id": str(bline.id),
            "cost_code": (cc.code if cc else "UNKNOWN"),
            "current_budget": str(current_budget),
            "committed_value": str(committed),
            "actuals_to_date": str(actuals),
            "this_po_net": str(po_net),
            "projected_total": str(projected),
            "over_by": str(projected - current_budget) if projected > current_budget else "0",
            "is_overrun": projected > current_budget,
        })
    return out
