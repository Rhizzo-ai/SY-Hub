"""0012 cost code sections seed (9 rows)

Revision ID: 0012_cost_code_sections_seed
Revises: 0011_cost_codes

Bulk seed migration; emits a single audit summary row instead of
per-section audit (Prompt 1.6 §I).

Patch #3 update: emits `action='Seed_Run'` (was 'Create'). The enum
value is added idempotently at the top of this migration via
`ALTER TYPE ... ADD VALUE IF NOT EXISTS` inside an autocommit block, so
a fresh DB chain (0012 before 0017) still succeeds. Existing DBs are
unaffected — this migration already ran and won't re-execute.
"""
import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0012_cost_code_sections_seed"
down_revision = "0011_cost_codes"
branch_labels = None
depends_on = None


# Stable namespace UUID for "migration" audit summary rows. Derived once;
# never change. Alembic revisions become deterministic UUIDs via uuid5.
MIGRATION_AUDIT_NAMESPACE = uuid.UUID("3a14a3e0-1f2c-4f8a-9c5d-bb1f6f3e0001")


SECTIONS = [
    # (code, name, display_order, is_direct_cost, default_p_and_l_category)
    ("acquisition", "Acquisition", 1, True, "COS"),
    ("planning", "Planning & Statutory Approvals", 2, True, "COS"),
    ("design", "Design & Professional Fees", 3, True, "COS"),
    ("construction", "Construction", 4, True, "COS"),
    ("sales_marketing", "Sales, Marketing & Disposal", 5, True, "COS"),
    ("finance", "Finance Costs", 6, False, "Finance"),
    ("company_overheads", "Company Overheads", 7, False, "Overhead"),
    ("accounting", "Accounting & Financial Services", 8, False, "Tax"),
    ("contingency", "Contingency, Risk & Miscellaneous", 9, True, "COS"),
]


def upgrade() -> None:
    # Patch #3: make `Seed_Run` available to this migration on fresh
    # DBs (it's officially added in 0017; IF NOT EXISTS makes re-run
    # safe). Must be in an autocommit block — Postgres forbids using a
    # newly-added enum value in the same transaction that added it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'Seed_Run'")

    bind = op.get_bind()
    inserted = 0
    for code, name, order, direct, p_and_l in SECTIONS:
        bind.execute(sa.text("""
            INSERT INTO cost_code_sections
                (id, code, name, display_order, is_direct_cost,
                 default_p_and_l_category)
            VALUES (gen_random_uuid(), :code, :name, :order, :direct, :p_and_l)
            ON CONFLICT (code) DO NOTHING
        """), {"code": code, "name": name, "order": order,
               "direct": direct, "p_and_l": p_and_l})
        inserted += 1

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
            "kind": "seed_run", "revision": revision,
            "target": "cost_code_sections", "rows_seeded": inserted,
        }),
        "now": datetime.now(timezone.utc),
    })


def downgrade() -> None:
    op.execute("DELETE FROM cost_code_sections WHERE code IN ("
               + ", ".join(repr(s[0]) for s in SECTIONS) + ")")
