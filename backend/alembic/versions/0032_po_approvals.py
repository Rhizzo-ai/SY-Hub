"""Chat 24 §R3 (Prompt 2.5) — PO Approvals + commitment recompute.

Lands the approval table + the budget-line commitment-recompute engine
that drives the over-budget approval trigger and the commitment
contract documented in `docs/engineering-invariants.md` §R3.

Commitment contract (verbatim from §R3 invariants):
  committed_value(budget_line) = SUM(line.net_amount) for PO lines whose
    parent PO.status ∈ {approved, issued, partially_receipted, receipted}
  pending_value(budget_line)   = SUM(line.net_amount) for PO lines whose
    parent PO.status ∈ {draft, pending_approval}
  closed + voided contribute ZERO to both.

Implementation:
  - `fn_budget_line_recompute_commitments(p_budget_line_id uuid)` —
    recomputes committed_value (and the derived committed_not_invoiced
    arithmetic kept in lock-step by the existing R8/Chat 23 budget
    triggers) for a single budget_line.
  - Trigger `trg_po_status_commitments` on `purchase_orders` AFTER
    UPDATE of status — recomputes commitments for every linked
    budget_line.
  - Trigger `trg_pol_commitments_on_change` on `purchase_order_lines`
    AFTER INSERT / UPDATE / DELETE — recomputes commitments for the
    affected budget_lines (both OLD and NEW if budget_line_id changes).

Note: `budget_lines.committed_value` is the canonical commitment field
established in Chat 23 §R5 (B-track) — it is NOT renamed to
`pending_commitment`. The PRD §R3 talks about "pending_value" — we
store the same number on the same column; the distinction is a
function of the parent PO.status (it's the source-of-truth for which
bucket the sum lands in).

Revision id:  0032_po_approvals
Revises:      0031_po_permissions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID


revision = "0032_po_approvals"
down_revision = "0031_po_permissions"
branch_labels = None
depends_on = None


def _add_enum_value_if_missing(enum_name: str, new_value: str) -> None:
    """Add a value to a PostgreSQL ENUM, idempotently, outside the
    migration's transaction (ALTER TYPE ADD VALUE cannot run inside one)."""
    with op.get_context().autocommit_block():
        op.execute(
            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{new_value}'"
        )


def upgrade() -> None:
    # ─── 1. New ENUM type ────────────────────────────────────────────────────
    po_resolution = ENUM(
        "approved", "rejected",
        name="po_approval_resolution",
        create_type=False,
    )
    po_resolution.create(op.get_bind(), checkfirst=True)

    # audit_action ext: Reject, Unlock are the two new verbs we surface.
    _add_enum_value_if_missing("audit_action", "Reject")
    _add_enum_value_if_missing("audit_action", "Unlock")
    _add_enum_value_if_missing("audit_action", "Approve")  # idempotent

    # ─── 2. purchase_order_approvals table (§2.1) ────────────────────────────
    op.create_table(
        "purchase_order_approvals",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "purchase_order_id", UUID(as_uuid=True),
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "submitted_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column("submission_reason", sa.Text, nullable=True),
        sa.Column(
            # JSON snapshot of every linked budget_line at submission
            # time: {budget_line_id, cost_code, current_budget,
            # committed_value, actuals_to_date, this_po_net}. Used for
            # forensic reconstruction long after the budget has moved.
            "budget_snapshot", JSONB, nullable=False,
        ),
        sa.Column(
            "resolution", po_resolution, nullable=True,
        ),
        sa.Column(
            "resolved_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id"), nullable=True,
        ),
        sa.Column(
            "resolved_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        # resolution_consistency CHECK — all 3 resolution_* columns
        # must be set together, or all unset.
        sa.CheckConstraint(
            "(resolution IS NULL AND resolved_by IS NULL "
            "AND resolved_at IS NULL) OR "
            "(resolution IS NOT NULL AND resolved_by IS NOT NULL "
            "AND resolved_at IS NOT NULL)",
            name="ck_poa_resolution_consistency",
        ),
        # rejection_notes_required: when resolution = 'rejected',
        # resolution_notes must be non-null/non-empty.
        sa.CheckConstraint(
            "resolution != 'rejected' OR "
            "(resolution_notes IS NOT NULL AND length(trim(resolution_notes)) > 0)",
            name="ck_poa_reject_requires_notes",
        ),
    )
    op.create_index(
        "ix_poa_po_id", "purchase_order_approvals", ["purchase_order_id"],
    )
    # Partial unique idx — at most one OPEN (resolution IS NULL)
    # approval row per PO. Resolved rows can stack (re-submit after
    # rejection → fresh row).
    op.create_index(
        "ux_poa_one_open_per_po",
        "purchase_order_approvals",
        ["purchase_order_id"],
        unique=True,
        postgresql_where=sa.text("resolution IS NULL"),
    )

    # ─── 3. fn_budget_line_recompute_commitments(p_budget_line_id) ───────────
    #
    # Recomputes commitment buckets on a single budget_line by walking
    # all PO lines that reference it, partitioned by parent PO.status:
    #   committed_value = SUM(net) where PO.status IN (approved, issued,
    #     partially_receipted, receipted)
    # Closed / voided are excluded explicitly.
    #
    # `committed_not_invoiced` is held in lock-step (committed_value -
    # invoiced_against_commitment). The R4 receipt service updates
    # invoiced_against_commitment in a separate path.
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

    # ─── 4. trg_po_status_commitments — fires on purchase_orders.status ──────
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_po_status_recompute_commitments()
        RETURNS trigger AS $$
        DECLARE
            r record;
        BEGIN
            IF NEW.status IS DISTINCT FROM OLD.status THEN
                FOR r IN
                    SELECT DISTINCT budget_line_id
                      FROM purchase_order_lines
                     WHERE purchase_order_id = NEW.id
                LOOP
                    PERFORM fn_budget_line_recompute_commitments(r.budget_line_id);
                END LOOP;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        DROP TRIGGER IF EXISTS trg_po_status_commitments ON purchase_orders;
        CREATE TRIGGER trg_po_status_commitments
        AFTER UPDATE OF status ON purchase_orders
        FOR EACH ROW
        EXECUTE FUNCTION fn_po_status_recompute_commitments();
    """)

    # ─── 5. trg_pol_commitments_on_change — fires on po line CUD ────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_pol_recompute_commitments_on_line_change()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                PERFORM fn_budget_line_recompute_commitments(NEW.budget_line_id);
            ELSIF TG_OP = 'UPDATE' THEN
                PERFORM fn_budget_line_recompute_commitments(NEW.budget_line_id);
                IF OLD.budget_line_id IS DISTINCT FROM NEW.budget_line_id THEN
                    PERFORM fn_budget_line_recompute_commitments(OLD.budget_line_id);
                END IF;
            ELSIF TG_OP = 'DELETE' THEN
                PERFORM fn_budget_line_recompute_commitments(OLD.budget_line_id);
            END IF;
            RETURN NULL;  -- AFTER trigger
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        DROP TRIGGER IF EXISTS trg_pol_commitments_on_change ON purchase_order_lines;
        CREATE TRIGGER trg_pol_commitments_on_change
        AFTER INSERT OR UPDATE OR DELETE ON purchase_order_lines
        FOR EACH ROW
        EXECUTE FUNCTION fn_pol_recompute_commitments_on_line_change();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_pol_commitments_on_change ON purchase_order_lines")
    op.execute("DROP FUNCTION IF EXISTS fn_pol_recompute_commitments_on_line_change()")
    op.execute("DROP TRIGGER IF EXISTS trg_po_status_commitments ON purchase_orders")
    op.execute("DROP FUNCTION IF EXISTS fn_po_status_recompute_commitments()")
    op.execute("DROP FUNCTION IF EXISTS fn_budget_line_recompute_commitments(uuid)")
    op.drop_index("ux_poa_one_open_per_po", table_name="purchase_order_approvals")
    op.drop_index("ix_poa_po_id", table_name="purchase_order_approvals")
    op.drop_table("purchase_order_approvals")
    ENUM(name="po_approval_resolution").drop(op.get_bind(), checkfirst=True)
