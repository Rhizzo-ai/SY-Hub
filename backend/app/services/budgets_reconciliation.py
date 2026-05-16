"""Budgets reconciliation — Prompt 2.5A / Chat 19A.

When an actual transitions state, the parent budget's cached `actuals_to_date`
column and downstream variance must be recomputed.

Contract (rules of engagement):
  - Counted statuses: Posted, Paid, Disputed (the row represents real cost).
  - NOT counted: Draft (not yet posted), Void (cancelled).
  - Retention amount is subtracted from actuals_to_date while
    retention_released=false — represents money not yet paid out — and added
    back to committed_not_invoiced. After release, the full gross flows to
    actuals_to_date.
  - Net vs gross: spec uses NET amount for actuals_to_date (matches Phase 1
    cost-tracker semantics — VAT recoverable is not a cost).
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.models.actuals import Actual
from app.models.budgets import Budget, BudgetLine
from app.services.budgets import _recompute_line, recompute_summary

log = logging.getLogger(__name__)


# Statuses that contribute to actuals_to_date
COUNTED_STATUSES = ("Posted", "Paid", "Disputed")


def recompute_for_line(db: Session, budget_line_id: uuid.UUID) -> Optional[Decimal]:
    """Recompute `actuals_to_date` + `committed_not_invoiced` for one BudgetLine.

    Returns the new actuals_to_date Decimal (or None if line doesn't exist).
    Also triggers parent budget summary recompute via recompute_summary.

    SAFE TO CALL repeatedly from a request handler. Identity-mapped: budget
    refresh is one SELECT plus the relationships already loaded.
    """
    line = db.get(BudgetLine, budget_line_id)
    if line is None:
        return None

    # Sum net_amount for counted statuses
    total_actuals_q = select(
        func.coalesce(func.sum(Actual.net_amount), 0)
    ).where(
        Actual.budget_line_id == budget_line_id,
        Actual.status.in_(COUNTED_STATUSES),
    )
    total_actuals = Decimal(db.execute(total_actuals_q).scalar() or 0)

    # Retention pending = sum(retention_amount) where retention_released=false
    # and status is counted (i.e. cost has been recognised). When released the
    # retention flows out of pending and into actuals_to_date naturally.
    retention_pending_q = select(
        func.coalesce(func.sum(Actual.retention_amount), 0)
    ).where(
        Actual.budget_line_id == budget_line_id,
        Actual.status.in_(COUNTED_STATUSES),
        Actual.retention_released.is_(False),
        Actual.retention_amount.isnot(None),
    )
    retention_pending = Decimal(db.execute(retention_pending_q).scalar() or 0)

    # actuals_to_date = total recognised cost MINUS retention still being held.
    actuals_to_date = (total_actuals - retention_pending).quantize(Decimal("0.01"))

    line.actuals_to_date = actuals_to_date
    # committed_not_invoiced now ALSO carries the retention pending bucket
    # (it's money committed by contract, not yet invoiced for cash payment).
    # Pre-existing PO commitments will be additive (Chat 20). For now, just
    # retention.
    line.committed_not_invoiced = retention_pending.quantize(Decimal("0.01"))

    # Recompute the parent budget header
    budget = db.scalar(
        select(Budget).where(Budget.id == line.budget_id).options(
            selectinload(Budget.lines)
        )
    )
    if budget is not None:
        recompute_summary(db, budget)

    db.flush()
    return actuals_to_date


def recompute_for_lines(db: Session, budget_line_ids: list[uuid.UUID]) -> None:
    """Bulk recompute helper. Deduplicates ids before recomputing."""
    seen: set[uuid.UUID] = set()
    for blid in budget_line_ids:
        if blid in seen:
            continue
        seen.add(blid)
        recompute_for_line(db, blid)
