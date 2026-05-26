"""0027 — Backfill 4 default budget_line_items for zero-item budget_lines.

Revision ID: 0027_default_line_items_backfill
Revises: 0026_ai_capture_costs_perm

Companion to Chat 23 Build Pack A R1.2: every NEW BudgetLine now ships
with 4 default BudgetLineItems (Materials, Labour, Equipment,
Subcontractor) at display_order 0..3 with amount=0.00. This migration
backfills the SAME 4 defaults onto any pre-existing line that has zero
items so the grid invariant ("every line renders 4+ rows") holds across
the whole database, not just lines created after R1.2 landed.

Idempotent:
  - Lines that already have items are skipped wholesale.
  - Re-running the migration is a no-op (zero-item lines are gone after
    the first run).

Audit:
  - A single `Schema_Change` audit_log row is emitted with the count of
    backfilled lines (`rows_backfilled`) and the count of items inserted
    (`items_inserted` = rows_backfilled * 4).

Greenfield databases (no pre-existing budget_lines) — this is a no-op.

Downgrade:
  - DELIBERATELY NON-REVERSIBLE (P1.R5 Option 1). Raises
    NotImplementedError. See `downgrade()` body for the why; in short,
    the heuristic used to identify "backfilled defaults" also matches
    user-edited £0 line items, so an automated downgrade would destroy
    real operator data. Forward-fix only — never run `alembic downgrade`
    below 0027 in prod.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0027_default_line_items_backfill"
down_revision = "0026_ai_capture_costs_perm"
branch_labels = None
depends_on = None


MIGRATION_AUDIT_NAMESPACE = uuid.UUID("3a14a3e0-1f2c-4f8a-9c5d-bb1f6f3e0027")

# Must mirror app.services.budget_lines.DEFAULT_LINE_ITEMS exactly.
DEFAULT_LINE_ITEMS = (
    "Materials",
    "Labour",
    "Equipment",
    "Subcontractor",
)


def upgrade() -> None:
    bind = op.get_bind()

    # Find all lines with zero items. We hold them in memory because the
    # set is bounded (one row per affected line) and the inserts below
    # iterate per-line for predictable audit accounting.
    zero_item_lines = bind.execute(sa.text("""
        SELECT bl.id
        FROM budget_lines bl
        LEFT JOIN budget_line_items bli ON bli.budget_line_id = bl.id
        WHERE bli.id IS NULL
    """)).scalars().all()

    rows_backfilled = 0
    items_inserted = 0

    for line_id in zero_item_lines:
        for idx, label in enumerate(DEFAULT_LINE_ITEMS):
            bind.execute(sa.text("""
                INSERT INTO budget_line_items (
                    id, budget_line_id, description, amount, display_order
                ) VALUES (
                    gen_random_uuid(), :line_id, :description,
                    0, :display_order
                )
            """), {
                "line_id": line_id,
                "description": label,
                "display_order": idx,
            })
            items_inserted += 1
        rows_backfilled += 1

    # Single audit row for the whole migration run. We use the
    # `Seed_Run` action (same as 0026) because `Schema_Change` is not in
    # the audit_action enum and this is functionally a one-off data seed.
    rev_uuid = uuid.uuid5(MIGRATION_AUDIT_NAMESPACE, revision)
    bind.execute(sa.text("""
        INSERT INTO audit_log
            (id, action, resource_type, resource_id, field_changes,
             metadata_json, created_at)
        VALUES (gen_random_uuid(), 'Seed_Run', 'migration', :rid,
                CAST('[]' AS jsonb), CAST(:meta AS jsonb), :now)
    """), {
        "rid": str(rev_uuid),
        "meta": json.dumps({
            "kind": "data_backfill",
            "revision": revision,
            "target": "budget_line_items",
            "rows_backfilled": rows_backfilled,
            "items_inserted": items_inserted,
            "default_labels": list(DEFAULT_LINE_ITEMS),
        }),
        "now": datetime.now(timezone.utc).isoformat(),
    })


def downgrade() -> None:
    # P1.R5 Option 1 (operator decision, 2026-02-13) — DELIBERATELY
    # non-reversible. The prior implementation used a content heuristic
    # (`amount=0 AND display_order BETWEEN 0 AND 3 AND description IN
    # ('Materials','Labour','Equipment','Subcontractor')`) which would
    # also destroy user-edited £0 line items that happen to match the
    # shape (e.g. a real "Labour" allocation awaiting a supplier quote).
    # Audit hard-constraint #5: a downgrade must not delete user data.
    # Forward-fix only — never run `alembic downgrade` below 0027 in
    # prod. See `/app/docs/SY_Homes_Future_Tasks.md` §24 for the runbook
    # note and tracking entry.
    raise NotImplementedError(
        "0027 is a backfill — downgrade would destroy user-edited "
        "budget_line_items (hard-constraint #5). Forward-fix instead."
    )
