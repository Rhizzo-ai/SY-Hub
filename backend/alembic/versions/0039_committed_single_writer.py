"""Build Pack 2.6-FIX (Chat 39) — single writer of committed_not_invoiced.

§R2 Fix A1: rewrite ``fn_budget_line_recompute_commitments`` so it no
longer writes ``budget_lines.committed_not_invoiced``. That column is now
written exclusively from Python in
``app.services.budgets_reconciliation.recompute_for_line`` as
``retention_pending + po_committed_not_invoiced``.

The trigger keeps writing ``committed_value`` (the canonical commitment
sum), and now invokes the Python recompute path indirectly: it sets
``committed_value`` and the application calls ``recompute_for_line`` on
the relevant budget_line on PO change. Because we cannot call Python from
a Postgres trigger, the line's ``committed_not_invoiced`` will be stale
until the next application-level recompute. To keep it deterministic on
PO-change paths, the PO services (`purchase_orders` status transitions,
PO-line CUD) explicitly call ``recompute_for_line`` after their writes —
see ``app/services/purchase_orders.py`` (Chat 39 §R2 A1 follow-up).

Reversible: ``downgrade()`` restores the previous function body verbatim
(committed_not_invoiced = committed_value − invoiced_against_commitment).

Revision id:  0039_committed_single_writer
Revises:      0038_sc_valuations
"""
from __future__ import annotations

from alembic import op


revision = "0039_committed_single_writer"
down_revision = "0038_sc_valuations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rewrite fn_budget_line_recompute_commitments so it ONLY writes
    # committed_value. committed_not_invoiced is the sole responsibility
    # of Python (recompute_for_line) from this migration onward.
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_budget_line_recompute_commitments(
            p_budget_line_id uuid
        ) RETURNS void AS $$
        DECLARE
            v_committed numeric(14,2) := 0;
        BEGIN
            SELECT COALESCE(SUM(pol.net_amount), 0)
              INTO v_committed
              FROM purchase_order_lines pol
              JOIN purchase_orders po
                ON po.id = pol.purchase_order_id
             WHERE pol.budget_line_id = p_budget_line_id
               AND po.status IN ('approved','issued',
                                 'partially_receipted','receipted');

            -- §R2 A1: do NOT write committed_not_invoiced here. The
            -- Python recompute_for_line is the sole writer of that
            -- column (retention_pending + po_committed_not_invoiced).
            UPDATE budget_lines
               SET committed_value = v_committed
             WHERE id = p_budget_line_id;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Restore the pre-0039 body verbatim (also writes
    # committed_not_invoiced = committed_value − invoiced_against_commitment).
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_budget_line_recompute_commitments(
            p_budget_line_id uuid
        ) RETURNS void AS $$
        DECLARE
            v_committed numeric(14,2) := 0;
        BEGIN
            SELECT COALESCE(SUM(pol.net_amount), 0)
              INTO v_committed
              FROM purchase_order_lines pol
              JOIN purchase_orders po
                ON po.id = pol.purchase_order_id
             WHERE pol.budget_line_id = p_budget_line_id
               AND po.status IN ('approved','issued',
                                 'partially_receipted','receipted');

            UPDATE budget_lines
               SET committed_value = v_committed,
                   committed_not_invoiced = v_committed -
                     COALESCE(invoiced_against_commitment, 0)
             WHERE id = p_budget_line_id;
        END;
        $$ LANGUAGE plpgsql;
    """)
