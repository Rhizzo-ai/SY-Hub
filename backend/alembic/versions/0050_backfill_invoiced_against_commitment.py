"""0050 — C1-back: backfill invoiced_against_commitment / committed_not_invoiced.

Chat 63 / C1-back — Budget Double-Counts Committed Cost.

Root cause: ``budget_lines.invoiced_against_commitment`` was never written —
it defaulted to 0 and stayed 0 — so the reconciliation formula
``committed_not_invoiced = retention_pending + (po_committed − invoiced)`` never
decreased as bills arrived. A £10k PO plus its £10k bill read as £20k of
spend/forecast (the same £10k counted twice).

The service fix (``budgets_reconciliation``) makes ``invoiced_against_commitment``
a DERIVED figure (summed fresh from the linked bills inside ``recompute_for_line``)
and persists it back onto the cached column. That corrects all FUTURE recomputes,
but EXISTING lines still hold the stale (wrong) cached
``committed_not_invoiced`` / ``invoiced_against_commitment`` from before the fix.

This one-off DATA-ONLY migration recomputes every existing budget line by
reusing the EXACT same ``recompute_for_line`` the live path now uses — so the
backfill and the runtime can never drift. It is naturally idempotent: deriving
the figure again yields the same answer, so it is safe to run on a DB where some
lines are already correct.

downgrade(): NO-OP. Recomputing cached aggregates is not meaningfully
reversible — the pre-fix values were a bug, not a state worth restoring, and the
derived figure is recoverable at any time by re-running the recompute. There is
no schema change to undo. (This makes the round-trip downgrade -1 / upgrade head
a clean no-op + re-backfill, both safe.)

Revision id:  0050_backfill_invoiced_commit
Revises:      0049_unbudgeted_order_lines
"""
from __future__ import annotations

import logging

from alembic import op
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.budgets import BudgetLine
from app.services.budgets_reconciliation import recompute_for_line

revision = "0050_backfill_invoiced_commit"
down_revision = "0049_unbudgeted_order_lines"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    # Bind a Session to the migration's own connection so the backfill writes
    # inside the same transaction Alembic commits at the end — and so we reuse
    # recompute_for_line verbatim (no re-implemented SQL that could drift from
    # the live path). recompute_for_line takes FOR UPDATE locks (parent budget,
    # then line) and flushes; within the single migration transaction that is
    # safe and serialises correctly.
    bind = op.get_bind()
    session = Session(bind=bind)

    line_ids = session.execute(select(BudgetLine.id)).scalars().all()
    log.info(
        "0050 backfill: recomputing %d budget line(s) "
        "(invoiced_against_commitment + committed_not_invoiced + summaries)",
        len(line_ids),
    )

    for blid in line_ids:
        recompute_for_line(session, blid)

    session.flush()
    log.info("0050 backfill: complete (%d lines recomputed)", len(line_ids))


def downgrade() -> None:
    # Intentional no-op — see module docstring. Cached aggregates are derived
    # and re-derivable; the pre-fix values were a double-counting bug, not a
    # state worth restoring. No schema change to reverse.
    pass
