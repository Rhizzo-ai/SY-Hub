"""appraisal_retrofit

Revision ID: 0021_appraisal_retrofit
Revises: 0020_permission_action_submit
Create Date: 2026-05-02

Phase A retrofit per Prompt 2.3 v6:
    A.1 Extend appraisal_state: add Withdrawn, Reopened
    A.2 Extend audit_action: add Appraisal.NewVersion, Appraisal.ScenarioCreate,
        Appraisal.DecisionLog, Appraisal.Withdraw
    A.3 Rename columns on appraisals: version→version_number, state→status,
        total_gdv→gdv_total, total_profit→profit_total
    A.4 Add columns: appraisal_group_id (uuid, NULL initially), is_current (bool, NOT NULL DEFAULT false)
    A.5 Backfill appraisal_group_id (one UUID per project_id) → SET NOT NULL
    A.6 Create appraisal_scenario_enum, add scenario column (NOT NULL DEFAULT 'Base')
    A.7 Backfill is_current=true for latest version per (project_id, scenario)
        where status NOT IN (Superseded, Withdrawn)
    A.8 Drop uq_appraisals_project_version constraint; create
        uq_appraisals_project_scenario_version (UNIQUE),
        uq_appraisals_current_per_project_scenario (UNIQUE WHERE is_current=true)

Notes:
- PG 15.16: ALTER TYPE ADD VALUE values cannot be used in the same transaction.
  Enum extensions wrapped in autocommit_block(); subsequent alembic operations
  run in a fresh transaction that sees the new values.
- audit_action enum name (NOT audit_action_enum) per Step 0 capture (verified R0).
- Original index is a UNIQUE CONSTRAINT (per R0 capture: UNIQUE CONSTRAINT, btree).
  We DROP CONSTRAINT (which removes the backing index automatically), then create
  the new partial + composite unique indexes.
- appraisal_group_id backfill uses Python-side UUIDs to avoid extension dependency.
- Downgrade reverses all DDL except enum value removal (no-op with comment).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = "0021_appraisal_retrofit"
down_revision = "0020_permission_action_submit"
branch_labels = None
depends_on = None

# Captured in R0 as a UNIQUE CONSTRAINT (not bare index).
ORIGINAL_UNIQUE_CONSTRAINT_NAME = "uq_appraisals_project_version"


def upgrade() -> None:
    # ----- A.1 / A.2 Extend enums (must be in autocommit; values usable in a
    # subsequent transaction) -----
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE appraisal_state ADD VALUE IF NOT EXISTS 'Withdrawn'")
        op.execute("ALTER TYPE appraisal_state ADD VALUE IF NOT EXISTS 'Reopened'")
        op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'Appraisal.NewVersion'")
        op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'Appraisal.ScenarioCreate'")
        op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'Appraisal.DecisionLog'")
        op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'Appraisal.Withdraw'")

    # ----- A.3 Rename columns -----
    op.alter_column("appraisals", "version", new_column_name="version_number")
    op.alter_column("appraisals", "state", new_column_name="status")
    op.alter_column("appraisals", "total_gdv", new_column_name="gdv_total")
    op.alter_column("appraisals", "total_profit", new_column_name="profit_total")

    # ----- A.4 Add new columns (group_id nullable for now; scenario added in A.6) -----
    op.add_column(
        "appraisals",
        sa.Column("appraisal_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "appraisals",
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ----- A.5 Backfill appraisal_group_id (one UUID per project_id) -----
    conn = op.get_bind()
    project_ids = [
        row[0]
        for row in conn.execute(
            sa.text("SELECT DISTINCT project_id FROM appraisals")
        ).fetchall()
    ]
    for pid in project_ids:
        new_group_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "UPDATE appraisals SET appraisal_group_id = :gid "
                "WHERE project_id = :pid"
            ),
            {"gid": str(new_group_id), "pid": str(pid)},
        )

    null_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM appraisals WHERE appraisal_group_id IS NULL")
    ).scalar()
    if null_count and null_count > 0:
        raise RuntimeError(
            f"appraisal_group_id backfill incomplete: {null_count} rows still NULL"
        )

    op.alter_column("appraisals", "appraisal_group_id", nullable=False)

    # ----- A.6 Create appraisal_scenario_enum + add scenario column -----
    op.execute(
        "CREATE TYPE appraisal_scenario_enum AS ENUM "
        "('Base', 'Upside', 'Downside', 'Sensitivity')"
    )
    op.execute(
        "ALTER TABLE appraisals ADD COLUMN scenario appraisal_scenario_enum "
        "NOT NULL DEFAULT 'Base'"
    )

    # ----- A.7 Backfill is_current -----
    op.execute(
        """
        UPDATE appraisals SET is_current = true WHERE id IN (
            SELECT DISTINCT ON (project_id, scenario) id
            FROM appraisals
            WHERE status NOT IN ('Superseded', 'Withdrawn')
            ORDER BY project_id, scenario, version_number DESC
        )
        """
    )

    bad_count = conn.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM (
                SELECT project_id, scenario, COUNT(*) c
                FROM appraisals
                WHERE is_current = true
                GROUP BY project_id, scenario
                HAVING COUNT(*) > 1
            ) bad
            """
        )
    ).scalar()
    if bad_count and bad_count > 0:
        raise RuntimeError(
            f"is_current backfill produced {bad_count} (project, scenario) "
            "combos with multiple current rows"
        )

    # ----- A.8 Swap unique constraint/indexes -----
    # Original is a UNIQUE CONSTRAINT (per R0 capture). Drop drops backing index.
    op.execute(
        f"ALTER TABLE appraisals DROP CONSTRAINT IF EXISTS {ORIGINAL_UNIQUE_CONSTRAINT_NAME}"
    )

    op.create_index(
        "uq_appraisals_project_scenario_version",
        "appraisals",
        ["project_id", "scenario", "version_number"],
        unique=True,
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_appraisals_current_per_project_scenario
        ON appraisals (project_id, scenario)
        WHERE is_current = true
        """
    )


def downgrade() -> None:
    # Reverse A.8
    op.execute(
        "DROP INDEX IF EXISTS uq_appraisals_current_per_project_scenario"
    )
    op.drop_index(
        "uq_appraisals_project_scenario_version", table_name="appraisals"
    )
    # Re-create as UNIQUE CONSTRAINT to mirror original.
    op.create_unique_constraint(
        ORIGINAL_UNIQUE_CONSTRAINT_NAME,
        "appraisals",
        ["project_id", "version_number"],
    )

    # Reverse A.6
    op.execute("ALTER TABLE appraisals DROP COLUMN scenario")
    op.execute("DROP TYPE appraisal_scenario_enum")

    # Reverse A.4
    op.drop_column("appraisals", "is_current")
    op.drop_column("appraisals", "appraisal_group_id")

    # Reverse A.3 — column renames back
    op.alter_column("appraisals", "profit_total", new_column_name="total_profit")
    op.alter_column("appraisals", "gdv_total", new_column_name="total_gdv")
    op.alter_column("appraisals", "status", new_column_name="state")
    op.alter_column("appraisals", "version_number", new_column_name="version")

    # Reverse A.1 / A.2 — enum value removal is a no-op in PG (would require
    # rebuilding the enum type; skipped per Phase A.9 of v6 prompt).
