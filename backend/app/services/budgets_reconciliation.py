"""Budgets reconciliation — Prompt 2.5A / Chat 19A.

When an actual transitions state, the parent budget's cached `actuals_to_date`
column and downstream variance must be recomputed.

Contract (rules of engagement):
  - Counted statuses: Posted, Paid, Disputed (the row represents real cost).
  - NOT counted: Draft (not yet posted), Void (cancelled).
  - Retention amount is subtracted from actuals_to_date while
    retention_released=false — represents money not yet paid out — and added
    to `committed_not_invoiced` (the contractual money committed but not yet
    invoiced for cash). On release the gross flows to actuals_to_date and
    the retention bucket is no longer pending.
  - Net vs gross: spec uses NET amount for actuals_to_date (matches Phase 1
    cost-tracker semantics — VAT recoverable is not a cost).

Build Pack 2.6-FIX §R2 A1/A2/A3:
  - `committed_not_invoiced` is now a single-writer column owned by Python.
    Formula: `retention_pending + po_committed_not_invoiced`. Migration
    0039 removes the PG trigger's write of this column.
  - `recompute_for_line` acquires the parent-budget FOR UPDATE lock first,
    then the BudgetLine FOR UPDATE lock — same order as `apply_bcr` — to
    avoid lost updates when a BCR apply / valuation certify / actual
    transition race on the same budget.
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
from app.models.purchase_orders import PurchaseOrder, PurchaseOrderLine
from app.services.budgets import _recompute_line, recompute_summary

log = logging.getLogger(__name__)


# Statuses that contribute to actuals_to_date
COUNTED_STATUSES = ("Posted", "Paid", "Disputed")

# PO statuses that contribute to committed_value / committed_not_invoiced —
# kept in exact lock-step with the trigger fn_budget_line_recompute_commitments
# (alembic/versions/0032_po_approvals.py:166-167). If the two ever drift, the
# Python value will not match the DB-trigger-maintained committed_value and
# auditors will (rightly) lose faith in the cost ledger.
PO_COMMITTED_STATUSES = (
    "approved", "issued", "partially_receipted", "receipted",
)


def _po_committed_not_invoiced_for_line(
    db: Session, line: BudgetLine,
) -> Decimal:
    """``po_committed_value − invoiced_against_commitment`` for one budget_line.

    Mirrors the WHERE / SUM / column arithmetic of the trigger
    ``fn_budget_line_recompute_commitments`` (alembic 0032 §R3, lines 160-173
    pre-0039) column-for-column so the value matches what the trigger used
    to write into ``committed_not_invoiced``.

    Closed / voided POs are excluded by virtue of not appearing in
    ``PO_COMMITTED_STATUSES``.
    """
    committed = db.execute(
        select(
            func.coalesce(func.sum(PurchaseOrderLine.net_amount), 0)
        ).select_from(PurchaseOrderLine).join(
            PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id,
        ).where(
            PurchaseOrderLine.budget_line_id == line.id,
            PurchaseOrder.status.in_(PO_COMMITTED_STATUSES),
        )
    ).scalar()
    committed_d = Decimal(committed or 0)
    invoiced_d = Decimal(line.invoiced_against_commitment or 0)
    return committed_d - invoiced_d


def recompute_for_line(db: Session, budget_line_id: uuid.UUID) -> Optional[Decimal]:
    """Recompute `actuals_to_date` + `committed_not_invoiced` for one BudgetLine.

    Returns the new actuals_to_date Decimal (or None if line doesn't exist).
    Also triggers parent budget summary recompute via recompute_summary.

    Locking (Chat 39 §R2 A2/A3): acquires the parent-budget FOR UPDATE lock
    first, then the BudgetLine FOR UPDATE lock — same order as
    ``budget_changes.apply_bcr`` — so concurrent apply/certify/post paths
    serialise on the parent budget row instead of clobbering each other.

    SAFE TO CALL repeatedly from a request handler.
    """
    # ── Lock order: parent budget FIRST, then the line. Matches apply_bcr
    # (services/budget_changes.py:608) — same order prevents deadlock.
    line_peek = db.get(BudgetLine, budget_line_id)
    if line_peek is None:
        return None
    parent_budget_id = line_peek.budget_id

    # 1. Lock the parent budget row.
    db.execute(
        select(Budget.id).where(Budget.id == parent_budget_id).with_for_update()
    )

    # 2. Lock the target BudgetLine row.
    line = db.scalar(
        select(BudgetLine).where(BudgetLine.id == budget_line_id)
        .with_for_update()
    )
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

    # PO bucket — mirrors trigger fn_budget_line_recompute_commitments'
    # filter exactly. Sole writer of committed_not_invoiced post-0039.
    po_committed_not_invoiced = _po_committed_not_invoiced_for_line(db, line)

    line.actuals_to_date = actuals_to_date
    # Chat 39 §R2 A1: single-writer formula.
    # committed_not_invoiced = retention pending (money committed by contract,
    # not yet released for cash) + PO committed-not-invoiced (purchase orders
    # in approved/issued/partially_receipted/receipted status, less anything
    # already invoiced against that commitment).
    # On retention release, retention_released flips to true → the retention
    # row drops out of retention_pending → the formula yields PO-only, and
    # the released gross flows into actuals_to_date via the COUNTED_STATUSES
    # branch above. Verified by Test #2 (test_retention_release_*).
    line.committed_not_invoiced = (
        retention_pending + po_committed_not_invoiced
    ).quantize(Decimal("0.01"))

    # Recompute the parent budget header.
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


def recompute_for_po(db: Session, po_id: uuid.UUID) -> None:
    """Recompute committed_not_invoiced on every budget_line touched by `po_id`.

    Called by PO status-mutation paths after `db.flush()` so the
    application-side recompute runs immediately after the PG trigger has
    updated `committed_value`. Without this, `committed_not_invoiced`
    would lag PO changes (the trigger no longer writes that column post-
    Chat 39 §R2 A1).
    """
    rows = db.execute(
        select(PurchaseOrderLine.budget_line_id)
        .where(PurchaseOrderLine.purchase_order_id == po_id)
        .distinct()
    ).all()
    blids = [r[0] for r in rows if r[0] is not None]
    if not blids:
        return
    recompute_for_lines(db, blids)
